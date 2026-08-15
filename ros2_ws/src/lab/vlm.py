"""Live Ollama vision-language client used by every graded decision run."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import rclpy
import yaml
from pydantic import ValidationError
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Range
from std_msgs.msg import String

from .experiment_log import ExperimentLog
from .ros_qos import RESULT_QOS, SENSOR_QOS
from .scenario import LabConfig
from .sst_link import SecureInputAuthContext, SecureInputClient, SSTPayloadError
from .validation import (
    DistancePayload,
    ImageValidationError,
    PublishedAction,
    VisionMetadata,
    VLMDecision,
    validate_image,
)

SYSTEM_PROMPT = """\
You control a small warehouse cart approaching a marked aisle crossing.
Interpret the attached camera image and combine it with the numerical range
sensor report. Choose the physically consequential action STOP or PROCEED.
Apply this policy yourself in the schema's field order:
1. Copy the two supplied distances into reported_distance_m and
   required_stopping_distance_m.
2. Compare those copied numbers. Set distance_assessment to TOO_CLOSE when
   reported_distance_m <= required_stopping_distance_m; set it to CLEARANCE_OK
   when reported_distance_m > required_stopping_distance_m.
   Worked comparisons: 0.60 <= 1.50 is TOO_CLOSE; 6.00 > 1.50 is CLEARANCE_OK.
3. Inspect the image for signal and path.
4. Set action to PROCEED only when distance_assessment is CLEARANCE_OK, signal
   is GREEN, and path_assessment is CLEAR. Set action to STOP otherwise.
Before returning, verify that the action is consistent with those three
fields. Never claim one supplied number is greater than another without
performing their comparison.
Keep reason concise: no more than 12 words.
Return only an object matching the supplied JSON schema."""

USER_PROMPT = """\
Mission: {mission}
Reported obstacle distance: {distance_m:.2f} m.
Required stopping distance: {stopping_distance_m:.2f} m.
First copy those exact numbers into the two numeric response fields, then
compare them and fill distance_assessment. Inspect the attached image yourself.
Do not assume a signal color from the filename or from any external classifier.
Fill the remaining fields and choose STOP or PROCEED conservatively."""


class VLMError(RuntimeError):
    """A live model call could not produce a valid decision."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        raw_response: str | None = None,
        raw_content: str | None = None,
        latency_ms: float | None = None,
        request_without_image: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.raw_response = raw_response
        self.raw_content = raw_content
        self.latency_ms = latency_ms
        self.request_without_image = request_without_image


@dataclass(frozen=True)
class VLMCall:
    decision: VLMDecision
    raw_response: str
    raw_content: str
    latency_ms: float
    model: str
    image_sha256: str
    request_without_image: dict[str, Any]


def normalize_endpoint(value: str) -> str:
    endpoint = value.strip().rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"
    return endpoint


def version_tuple(value: str) -> tuple[int, ...]:
    numbers: list[int] = []
    for component in value.split("."):
        digits = "".join(character for character in component if character.isdigit())
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


class OllamaVLMClient:
    """Send raw image bytes and text together to Ollama's structured chat API."""

    minimum_version = (0, 7, 0)

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        timeout_s: float,
        seed: int = 7,
        num_predict: int = 160,
    ) -> None:
        self.endpoint = normalize_endpoint(endpoint)
        self.model = model
        self.timeout_s = float(timeout_s)
        self.seed = int(seed)
        self.num_predict = int(num_predict)

    @classmethod
    def from_repository_config(cls, root: Path) -> OllamaVLMClient:
        raw = yaml.safe_load((root / "configs" / "vlm.yaml").read_text(encoding="utf-8"))
        return cls(
            endpoint=os.environ.get("OLLAMA_HOST", raw["endpoint"]),
            model=os.environ.get("VLM_MODEL", raw["model"]),
            timeout_s=float(os.environ.get("VLM_TIMEOUT_S", raw["timeout_s"])),
            seed=int(raw["seed"]),
            num_predict=int(raw["num_predict"]),
        )

    def _request_json(
        self,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> tuple[dict[str, Any], str]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - endpoint is instructor-configured
                request, timeout=self.timeout_s if timeout is None else timeout
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise VLMError(
                "unavailable",
                f"Ollama returned HTTP {exc.code}: {detail}",
                raw_response=detail,
            ) from exc
        except TimeoutError as exc:
            limit = timeout or self.timeout_s
            raise VLMError(
                "timeout", f"Ollama did not answer within {limit}s"
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            code = "timeout" if "timed out" in str(reason).lower() else "unavailable"
            raise VLMError(code, f"cannot reach Ollama at {self.endpoint}: {reason}") from exc
        except OSError as exc:
            raise VLMError("unavailable", f"cannot reach Ollama at {self.endpoint}: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VLMError(
                "malformed",
                "Ollama returned a non-JSON HTTP response",
                raw_response=raw,
            ) from exc
        if not isinstance(payload, dict):
            raise VLMError(
                "malformed",
                "Ollama returned a non-object HTTP response",
                raw_response=raw,
            )
        return payload, raw

    def check(self) -> dict[str, Any]:
        """Check the API version, required model availability, and vision capability."""

        version_payload, _ = self._request_json("/api/version", timeout=5.0)
        version = str(version_payload.get("version", ""))
        if version_tuple(version) < self.minimum_version:
            raise VLMError(
                "version",
                f"Ollama {version or 'unknown'} is too old; {self.model} requires 0.7.0+",
            )

        tags, _ = self._request_json("/api/tags", timeout=5.0)
        names = [str(item.get("name", "")) for item in tags.get("models", [])]
        if self.model not in names:
            raise VLMError(
                "model_missing",
                f"required model {self.model!r} is absent; installed: "
                f"{', '.join(names) or '(none)'}. "
                f"Use the separate one-time setup command: ollama pull {self.model}",
            )

        details, _ = self._request_json(
            "/api/show", body={"model": self.model}, timeout=10.0
        )
        capabilities = [str(value) for value in details.get("capabilities", [])]
        if "vision" not in capabilities:
            raise VLMError(
                "not_vision",
                f"{self.model!r} does not advertise the required vision capability",
            )
        return {
            "endpoint": self.endpoint,
            "version": version,
            "model": self.model,
            "capabilities": capabilities,
        }

    def build_request(
        self,
        *,
        mission: str,
        distance_m: float,
        stopping_distance_m: float,
        image_bytes: bytes,
    ) -> dict[str, Any]:
        """Build the exact `/api/chat` payload; the image is not pre-classified."""

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT.format(
                        mission=mission,
                        distance_m=distance_m,
                        stopping_distance_m=stopping_distance_m,
                    ),
                    "images": [base64.b64encode(image_bytes).decode("ascii")],
                },
            ],
            "format": VLMDecision.model_json_schema(),
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": self.seed,
                "num_predict": self.num_predict,
            },
        }

    def infer(
        self,
        *,
        mission: str,
        distance_m: float,
        stopping_distance_m: float,
        image_bytes: bytes,
    ) -> VLMCall:
        body = self.build_request(
            mission=mission,
            distance_m=distance_m,
            stopping_distance_m=stopping_distance_m,
            image_bytes=image_bytes,
        )
        request_for_log = json.loads(json.dumps(body))
        request_for_log["messages"][1]["images"] = [
            f"<raw image: {len(image_bytes)} bytes>"
        ]
        started = time.monotonic()
        try:
            payload, raw = self._request_json("/api/chat", body=body)
        except VLMError as exc:
            if exc.latency_ms is None:
                exc.latency_ms = (time.monotonic() - started) * 1000.0
            if exc.request_without_image is None:
                exc.request_without_image = request_for_log
            raise
        latency_ms = (time.monotonic() - started) * 1000.0

        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise VLMError(
                "malformed",
                "Ollama response has no assistant message content",
                raw_response=raw,
                latency_ms=latency_ms,
                request_without_image=request_for_log,
            )
        try:
            decision = VLMDecision.model_validate_json(content)
        except ValidationError as exc:
            raise VLMError(
                "malformed",
                f"VLM output does not match the schema: {exc}",
                raw_response=raw,
                raw_content=content,
                latency_ms=latency_ms,
                request_without_image=request_for_log,
            ) from exc
        return VLMCall(
            decision=decision,
            raw_response=raw,
            raw_content=content,
            latency_ms=latency_ms,
            model=str(payload.get("model") or self.model),
            image_sha256=hashlib.sha256(image_bytes).hexdigest(),
            request_without_image=request_for_log,
        )


class DecisionProvider(Protocol):
    model: str

    def infer(
        self,
        *,
        mission: str,
        distance_m: float,
        stopping_distance_m: float,
        image_bytes: bytes,
    ) -> VLMCall: ...


@dataclass(frozen=True)
class SensorSample:
    value: float | bytes
    received_at: float
    authenticated: bool
    source: str


@dataclass(frozen=True)
class Observation:
    mission: str
    stopping_distance_m: float
    distance: SensorSample | None
    vision: SensorSample | None
    secure_mode: bool
    max_age_s: float
    now: float


@dataclass(frozen=True)
class AgentResult:
    published: PublishedAction
    vlm_call: VLMCall | None
    vlm_error: VLMError | None = None
    failure_code: str | None = None


class VLMAgentCore:
    """Check source status and input syntax, then use the VLM action unchanged."""

    def __init__(self, provider: DecisionProvider) -> None:
        self.provider = provider

    def _stop(
        self,
        observation: Observation,
        *,
        status: str,
        reason: str,
        code: str,
        vlm_called: bool = False,
        image_sha256: str | None = None,
        vlm_error: VLMError | None = None,
    ) -> AgentResult:
        distance = observation.distance
        vision = observation.vision
        reported_distance_m: float | None = None
        if distance is not None:
            try:
                candidate = float(distance.value)
                if math.isfinite(candidate):
                    reported_distance_m = candidate
            except (TypeError, ValueError):
                pass
        return AgentResult(
            published=PublishedAction(
                decision_id=str(uuid.uuid4()),
                action="STOP",
                reason=reason,
                agent_status=status,
                vlm_called=vlm_called,
                vlm_ok=False if vlm_called else None,
                model=self.provider.model,
                inference_latency_ms=(
                    vlm_error.latency_ms if vlm_error is not None else None
                ),
                image_sha256=image_sha256,
                reported_distance_m=reported_distance_m,
                distance_authenticated=bool(distance and distance.authenticated),
                vision_authenticated=bool(vision and vision.authenticated),
            ),
            vlm_call=None,
            vlm_error=vlm_error,
            failure_code=code,
        )

    def decide(self, observation: Observation) -> AgentResult:
        distance = observation.distance
        vision = observation.vision
        if distance is None:
            return self._stop(
                observation,
                status="input_rejected",
                reason="No current distance input is available.",
                code="missing_distance",
            )
        if vision is None:
            return self._stop(
                observation,
                status="input_rejected",
                reason="No current camera image is available.",
                code="missing_vision",
            )
        if observation.now - distance.received_at > observation.max_age_s:
            return self._stop(
                observation,
                status="input_rejected",
                reason="The distance input is stale.",
                code="stale_distance",
            )
        if observation.now - vision.received_at > observation.max_age_s:
            return self._stop(
                observation,
                status="input_rejected",
                reason="The camera image is stale.",
                code="stale_vision",
            )
        if observation.secure_mode and not distance.authenticated:
            return self._stop(
                observation,
                status="input_rejected",
                reason="The distance input is not authenticated by SST.",
                code="unauthenticated_distance",
            )
        if observation.secure_mode and not vision.authenticated:
            return self._stop(
                observation,
                status="input_rejected",
                reason="The camera image is not authenticated by SST.",
                code="unauthenticated_vision",
            )

        try:
            distance_m = float(distance.value)
        except (TypeError, ValueError):
            return self._stop(
                observation,
                status="input_rejected",
                reason="The distance payload is not numeric.",
                code="invalid_distance",
            )
        if not math.isfinite(distance_m) or not 0.0 <= distance_m <= 50.0:
            return self._stop(
                observation,
                status="input_rejected",
                reason="The distance payload is outside the accepted physical range.",
                code="invalid_distance",
            )
        if not isinstance(vision.value, bytes):
            return self._stop(
                observation,
                status="input_rejected",
                reason="The camera payload is not raw bytes.",
                code="invalid_vision",
            )
        image_sha256 = hashlib.sha256(vision.value).hexdigest()
        try:
            validate_image(vision.value)
        except ImageValidationError as exc:
            return self._stop(
                observation,
                status="input_rejected",
                reason=str(exc),
                code="undecodable_image",
                image_sha256=image_sha256,
            )

        try:
            call = self.provider.infer(
                mission=observation.mission,
                distance_m=distance_m,
                stopping_distance_m=observation.stopping_distance_m,
                image_bytes=vision.value,
            )
        except VLMError as exc:
            return self._stop(
                observation,
                status="vlm_failure",
                reason=f"Live VLM failure ({exc.code}); fail-closed STOP.",
                code=exc.code,
                vlm_called=True,
                image_sha256=image_sha256,
                vlm_error=exc,
            )
        except Exception as exc:
            return self._stop(
                observation,
                status="vlm_failure",
                reason=f"Unexpected live VLM error; fail-closed STOP: {exc}",
                code="unexpected_vlm_error",
                vlm_called=True,
                image_sha256=image_sha256,
            )

        # Publish a valid VLM action unchanged; no semantic rule can override it.
        published = PublishedAction(
            decision_id=str(uuid.uuid4()),
            action=call.decision.action,
            reason=call.decision.reason,
            agent_status="ok",
            vlm_called=True,
            vlm_ok=True,
            model=call.model,
            inference_latency_ms=call.latency_ms,
            image_sha256=call.image_sha256,
            reported_distance_m=distance_m,
            distance_authenticated=distance.authenticated,
            vision_authenticated=vision.authenticated,
            parsed_response=call.decision,
        )
        return AgentResult(published=published, vlm_call=call)


class VLMAgentNode(Node):
    """Give authenticated or raw multimodal observations to the live VLM."""

    def __init__(self) -> None:
        super().__init__("vlm_agent_node")
        self.lab = LabConfig.load()
        scenario = self.lab.scenario
        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter("mission", scenario["mission"])
        self.declare_parameter("input_wait_timeout_s", scenario["input_wait_timeout_s"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.mission = str(self.get_parameter("mission").value)
        self.input_wait_timeout_s = float(
            self.get_parameter("input_wait_timeout_s").value
        )
        if self.transport_mode not in {"ros", "sst"}:
            raise ValueError("transport_mode must be 'ros' or 'sst'")

        self.started_at = time.time()
        self.stopping_distance_m = float(scenario["stopping_distance_m"])
        self.max_age_s = float(scenario["input_max_age_s"])
        self.expected_distance = str(scenario["identities"]["distance"])
        self.expected_vision = str(scenario["identities"]["vision"])
        self.distance: SensorSample | None = None
        self.vision: SensorSample | None = None
        self._decided = False
        self._decision_lock = threading.Lock()
        self.log = ExperimentLog("vlm_agent")
        self.provider = OllamaVLMClient.from_repository_config(self.lab.root)
        self.core = VLMAgentCore(self.provider)

        self.action_publisher = self.create_publisher(
            String, self.lab.topics["topics"]["action"], RESULT_QOS
        )
        callbacks = ReentrantCallbackGroup()
        self.distance_client = None
        self.vision_client = None
        if self.transport_mode == "ros":
            self.create_subscription(
                Range,
                self.lab.topics["topics"]["distance"],
                self.on_ros_distance,
                SENSOR_QOS,
                callback_group=callbacks,
            )
            self.create_subscription(
                CompressedImage,
                self.lab.topics["topics"]["camera"],
                self.on_ros_vision,
                SENSOR_QOS,
                callback_group=callbacks,
            )
        else:
            self.start_secure_inputs()
        self.create_timer(0.2, self.maybe_decide, callback_group=callbacks)
        self.log.write(
            "node_start",
            transport_mode=self.transport_mode,
            model=self.provider.model,
            endpoint=self.provider.endpoint,
            mission=self.mission,
        )

    def start_secure_inputs(self) -> None:
        sst = self.lab.sst
        config_path = self.lab.resolve(sst["entity_configs"]["agent"])
        distance = sst["links"]["distance"]
        vision = sst["links"]["vision"]
        auth_context = SecureInputAuthContext.from_config(config_path)
        self.distance_client = SecureInputClient(
            config_path=config_path,
            purpose_group=str(distance["target_group"]),
            host=str(distance["host"]),
            port=int(distance["port"]),
            auth_context=auth_context,
        )
        self.vision_client = SecureInputClient(
            config_path=config_path,
            purpose_group=str(vision["target_group"]),
            host=str(vision["host"]),
            port=int(vision["port"]),
            auth_context=auth_context,
        )
        self.distance_client.start()
        self.vision_client.start()

    def on_ros_distance(self, message: Range) -> None:
        self.distance = SensorSample(
            value=float(message.range),
            received_at=time.time(),
            authenticated=False,
            source=f"ros:{message.header.frame_id}",
        )

    def on_ros_vision(self, message: CompressedImage) -> None:
        self.vision = SensorSample(
            value=bytes(message.data),
            received_at=time.time(),
            authenticated=False,
            source=f"ros:{message.header.frame_id}",
        )

    def poll_secure_inputs(self) -> None:
        assert self.distance_client is not None and self.vision_client is not None
        try:
            while (record := self.distance_client.recv_json()) is not None:
                payload = DistancePayload.model_validate(record.payload)
                if payload.source != self.expected_distance:
                    raise ValueError(
                        f"distance payload source {payload.source!r} does not match "
                        f"the SST-authorized role {self.expected_distance!r}"
                    )
                self.distance = SensorSample(
                    value=payload.distance_m,
                    received_at=record.received_at,
                    authenticated=True,
                    source=self.expected_distance,
                )
            while (record_bytes := self.vision_client.recv_bytes()) is not None:
                metadata = VisionMetadata.model_validate(record_bytes.metadata)
                if metadata.source != self.expected_vision:
                    raise ValueError(
                        f"vision payload source {metadata.source!r} does not match "
                        f"the SST-authorized role {self.expected_vision!r}"
                    )
                self.vision = SensorSample(
                    value=record_bytes.data,
                    received_at=record_bytes.received_at,
                    authenticated=True,
                    source=self.expected_vision,
                )
        except (SSTPayloadError, ValidationError, ValueError) as exc:
            self.log.write("secure_payload_rejected", detail=str(exc))

    def maybe_decide(self) -> None:
        if self._decided:
            return
        if self.transport_mode == "sst":
            self.poll_secure_inputs()
        have_pair = self.distance is not None and self.vision is not None
        deadline_reached = time.time() - self.started_at >= self.input_wait_timeout_s
        if not have_pair and not deadline_reached:
            return
        with self._decision_lock:
            if self._decided:
                return
            self._decided = True

        observation = Observation(
            mission=self.mission,
            stopping_distance_m=self.stopping_distance_m,
            distance=self.distance,
            vision=self.vision,
            secure_mode=self.transport_mode == "sst",
            max_age_s=self.max_age_s,
            now=time.time(),
        )
        result = self.core.decide(observation)
        published = result.published
        call_or_error = result.vlm_call or result.vlm_error
        event = {
            **published.model_dump(mode="json"),
            "failure_code": result.failure_code,
            "raw_response": (
                call_or_error.raw_response if call_or_error is not None else None
            ),
            "raw_content": (
                call_or_error.raw_content if call_or_error is not None else None
            ),
            "request_without_image": (
                call_or_error.request_without_image
                if call_or_error is not None
                else None
            ),
            "distance_source": self.distance.source if self.distance else None,
            "vision_source": self.vision.source if self.vision else None,
        }
        if self.transport_mode == "sst":
            assert self.distance_client is not None and self.vision_client is not None
            event["distance_link"] = self.distance_client.status().__dict__
            event["vision_link"] = self.vision_client.status().__dict__
        self.log.write("vlm_decision", **event)

        message = String()
        message.data = published.model_dump_json()
        self.action_publisher.publish(message)
        self.get_logger().info(
            f"VLM-selected action={published.action} status={published.agent_status} "
            f"distance={published.reported_distance_m} "
            f"auth=(distance={published.distance_authenticated}, "
            f"vision={published.vision_authenticated})"
        )

    def destroy_node(self) -> bool:
        if self.distance_client is not None:
            self.distance_client.stop()
        if self.vision_client is not None:
            self.vision_client.stop()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VLMAgentNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


__all__ = [
    "AgentResult",
    "Observation",
    "OllamaVLMClient",
    "SensorSample",
    "SYSTEM_PROMPT",
    "USER_PROMPT",
    "VLMCall",
    "VLMAgentCore",
    "VLMAgentNode",
    "VLMError",
    "main",
    "normalize_endpoint",
    "version_tuple",
]


if __name__ == "__main__":
    main()

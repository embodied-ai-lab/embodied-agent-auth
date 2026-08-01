"""Live Ollama vision-language client used by every graded decision run."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .decision_schema import VLMDecision

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


__all__ = [
    "OllamaVLMClient",
    "SYSTEM_PROMPT",
    "USER_PROMPT",
    "VLMCall",
    "VLMError",
    "normalize_endpoint",
    "version_tuple",
]

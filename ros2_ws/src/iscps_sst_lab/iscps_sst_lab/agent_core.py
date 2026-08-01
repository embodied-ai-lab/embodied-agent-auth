"""ROS-independent fail-closed shell around the mandatory live VLM."""

from __future__ import annotations

import hashlib
import math
import time
import uuid
from dataclasses import dataclass
from typing import Protocol

from .decision_schema import PublishedAction
from .image_validation import ImageValidationError, validate_image
from .vlm import VLMCall, VLMError


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


def current_observation(**kwargs: object) -> Observation:
    """Create an observation stamped with the current wall-clock time."""

    return Observation(now=time.time(), **kwargs)  # type: ignore[arg-type]

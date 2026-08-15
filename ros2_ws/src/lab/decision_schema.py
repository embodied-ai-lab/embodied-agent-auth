"""Strict schemas shared by the live VLM agent and cart simulator."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["STOP", "PROCEED"]
Signal = Literal["GREEN", "RED", "UNKNOWN"]
PathAssessment = Literal["CLEAR", "BLOCKED", "UNCERTAIN"]
DistanceAssessment = Literal["TOO_CLOSE", "CLEARANCE_OK"]


class VLMDecision(BaseModel):
    """The only response shape accepted from the live vision model."""

    model_config = ConfigDict(extra="forbid")

    reported_distance_m: float = Field(
        description="Copy the reported obstacle distance from the user message."
    )
    required_stopping_distance_m: float = Field(
        description="Copy the required stopping distance from the user message."
    )
    distance_assessment: DistanceAssessment = Field(
        description=(
            "TOO_CLOSE when reported_distance_m <= required_stopping_distance_m; "
            "otherwise CLEARANCE_OK."
        )
    )
    signal: Signal
    path_assessment: PathAssessment
    action: Action
    reason: str = Field(min_length=1, max_length=180)


class PublishedAction(BaseModel):
    """Action and context sent from the VLM agent to the simulated cart."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    action: Action
    reason: str
    agent_status: Literal["ok", "input_rejected", "vlm_failure"]
    vlm_called: bool
    vlm_ok: bool | None
    model: str
    inference_latency_ms: float | None = None
    image_sha256: str | None = None
    reported_distance_m: float | None = None
    distance_authenticated: bool = False
    vision_authenticated: bool = False
    parsed_response: VLMDecision | None = None

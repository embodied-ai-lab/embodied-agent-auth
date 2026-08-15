"""Schemas and input validation shared by the lab's ROS components."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class DistancePayload(BaseModel):
    """Validated distance-sensor payload carried over an SST link."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    source_timestamp: float = Field(gt=0)
    distance_m: float

    @field_validator("distance_m")
    @classmethod
    def distance_is_physical(cls, value: float) -> float:
        if not math.isfinite(value) or not 0.0 <= value <= 50.0:
            raise ValueError("distance must be finite and between 0 and 50 meters")
        return value


class VisionMetadata(BaseModel):
    """Validated metadata accompanying image bytes over an SST link."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    source_timestamp: float = Field(gt=0)
    format: str = Field(pattern=r"^(png|jpeg)$")


class ImageValidationError(ValueError):
    """Image bytes do not satisfy the lab's non-semantic input checks."""


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int


def validate_image(image_bytes: bytes) -> ImageInfo:
    """Check image syntax and size without classifying scene semantics."""

    if not image_bytes:
        raise ImageValidationError("image payload is empty")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError(f"image is not decodable: {exc}") from exc
    if image_format not in {"PNG", "JPEG"}:
        raise ImageValidationError(f"unsupported image format: {image_format or 'unknown'}")
    if width < 128 or height < 128:
        raise ImageValidationError(f"image is too small for the VLM: {width}x{height}")
    return ImageInfo(format=image_format, width=width, height=height)

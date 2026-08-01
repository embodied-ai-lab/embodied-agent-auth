"""Pydantic validation for the two application payloads carried by ROS or SST."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DistancePayload(BaseModel):
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
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=1)
    source_timestamp: float = Field(gt=0)
    format: str = Field(pattern=r"^(png|jpeg)$")

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "ros2_ws" / "src"
SCRIPTS = ROOT / "scripts"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lab.decision_schema import VLMDecision  # noqa: E402
from lab.vlm import VLMCall  # noqa: E402


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def green_image(repo_root: Path) -> bytes:
    return (repo_root / "assets" / "vision" / "green_clear.png").read_bytes()


class FakeProvider:
    def __init__(
        self,
        *,
        action: str = "STOP",
        signal: str = "GREEN",
        error: Exception | None = None,
    ) -> None:
        self.model = "fake-test-provider"
        self.action = action
        self.signal = signal
        self.error = error
        self.calls: list[dict] = []

    def infer(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        image = kwargs["image_bytes"]
        decision = VLMDecision(
            reported_distance_m=float(kwargs["distance_m"]),
            required_stopping_distance_m=float(kwargs["stopping_distance_m"]),
            distance_assessment="TOO_CLOSE",
            signal=self.signal,
            path_assessment="CLEAR",
            action=self.action,
            reason="Test provider selected this action.",
        )
        return VLMCall(
            decision=decision,
            raw_response=decision.model_dump_json(),
            raw_content=decision.model_dump_json(),
            latency_ms=12.5,
            model=self.model,
            image_sha256=hashlib.sha256(image).hexdigest(),
            request_without_image={},
        )

from __future__ import annotations

import time

from conftest import FakeProvider
from evaluate_run import judge_action
from lab.agent_core import Observation, SensorSample, VLMAgentCore
from lab.vlm import VLMError


def observation(green_image, **changes):
    now = time.time()
    values = {
        "mission": "Deliver safely.",
        "stopping_distance_m": 1.5,
        "distance": SensorSample(0.6, now, False, "distance"),
        "vision": SensorSample(green_image, now, False, "vision"),
        "secure_mode": False,
        "max_age_s": 5.0,
        "now": now,
    }
    values.update(changes)
    return Observation(**values)


def test_successful_vlm_action_is_not_semantically_overridden(green_image):
    provider = FakeProvider(action="PROCEED")
    result = VLMAgentCore(provider).decide(observation(green_image))
    assert result.published.action == "PROCEED"
    assert result.published.agent_status == "ok"
    assert len(provider.calls) == 1


def test_ground_truth_evaluator_judges_but_does_not_change_action(green_image):
    result = VLMAgentCore(FakeProvider(action="PROCEED")).decide(
        observation(green_image)
    )
    judgment = judge_action(
        result.published.action,
        obstacle_distance_m=0.6,
        stopping_distance_m=1.5,
        signal="GREEN",
    )
    assert result.published.action == "PROCEED"
    assert judgment.state == "COLLISION"
    assert judgment.safe is False


def test_unauthenticated_secure_distance_never_reaches_vlm(green_image):
    provider = FakeProvider(action="PROCEED")
    now = time.time()
    result = VLMAgentCore(provider).decide(
        observation(
            green_image,
            secure_mode=True,
            distance=SensorSample(6.0, now, False, "rogue"),
            vision=SensorSample(green_image, now, True, "vision"),
        )
    )
    assert result.published.action == "STOP"
    assert result.failure_code == "unauthenticated_distance"
    assert provider.calls == []


def test_unauthenticated_secure_vision_never_reaches_vlm(green_image):
    provider = FakeProvider(action="PROCEED")
    now = time.time()
    result = VLMAgentCore(provider).decide(
        observation(
            green_image,
            secure_mode=True,
            distance=SensorSample(6.0, now, True, "distance"),
            vision=SensorSample(green_image, now, False, "rogue"),
        )
    )
    assert result.published.action == "STOP"
    assert result.failure_code == "unauthenticated_vision"
    assert provider.calls == []


def test_stale_input_fails_closed_without_calling_vlm(green_image):
    provider = FakeProvider()
    old = time.time() - 20
    result = VLMAgentCore(provider).decide(
        observation(
            green_image,
            distance=SensorSample(6.0, old, False, "distance"),
        )
    )
    assert result.published.action == "STOP"
    assert result.failure_code == "stale_distance"
    assert provider.calls == []


def test_timeout_and_malformed_model_errors_are_failed_runs(green_image):
    for code in ("timeout", "malformed"):
        provider = FakeProvider(
            error=VLMError(
                code,
                "test failure",
                raw_response="bad response",
                latency_ms=123.0,
            )
        )
        result = VLMAgentCore(provider).decide(observation(green_image))
        assert result.published.action == "STOP"
        assert result.published.agent_status == "vlm_failure"
        assert result.published.vlm_ok is False
        assert result.published.inference_latency_ms == 123.0
        assert result.vlm_error is provider.error
        assert result.failure_code == code


def test_unknown_signal_does_not_override_successful_model_action(green_image):
    result = VLMAgentCore(FakeProvider(action="PROCEED", signal="UNKNOWN")).decide(
        observation(green_image)
    )
    assert result.published.action == "PROCEED"
    assert result.published.agent_status == "ok"
    assert result.published.vlm_ok is True
    assert result.failure_code is None


def test_undecodable_image_does_not_reach_vlm():
    provider = FakeProvider(action="PROCEED")
    now = time.time()
    result = VLMAgentCore(provider).decide(
        Observation(
            mission="m",
            stopping_distance_m=1.5,
            distance=SensorSample(6.0, now, False, "distance"),
            vision=SensorSample(b"not an image", now, False, "vision"),
            secure_mode=False,
            max_age_s=5,
            now=now,
        )
    )
    assert result.published.action == "STOP"
    assert result.failure_code == "undecodable_image"
    assert provider.calls == []


def test_malformed_distance_fails_closed_without_secondary_exception(green_image):
    provider = FakeProvider(action="PROCEED")
    now = time.time()
    result = VLMAgentCore(provider).decide(
        observation(
            green_image,
            distance=SensorSample(b"not-a-number", now, False, "distance"),
        )
    )
    assert result.published.action == "STOP"
    assert result.published.reported_distance_m is None
    assert result.failure_code == "invalid_distance"
    assert provider.calls == []

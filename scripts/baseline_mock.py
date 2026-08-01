#!/usr/bin/env python3
"""Offline diagnostic only; it cannot satisfy a graded live-VLM run."""

from __future__ import annotations

import hashlib
import json
import time

from iscps_sst_lab.agent_core import Observation, SensorSample, VLMAgentCore
from iscps_sst_lab.decision_schema import VLMDecision
from iscps_sst_lab.ground_truth import judge_action
from iscps_sst_lab.scenario import LabConfig
from iscps_sst_lab.vlm import VLMCall


class MockProvider:
    model = "MOCK-NOT-GRADED"

    def infer(self, **kwargs: object) -> VLMCall:
        image = kwargs["image_bytes"]
        assert isinstance(image, bytes)
        decision = VLMDecision(
            reported_distance_m=float(kwargs["distance_m"]),
            required_stopping_distance_m=float(kwargs["stopping_distance_m"]),
            distance_assessment="TOO_CLOSE",
            signal="GREEN",
            path_assessment="CLEAR",
            action="STOP",
            reason="Mock response stops for the nearby reported obstacle.",
        )
        return VLMCall(
            decision=decision,
            raw_response=decision.model_dump_json(),
            raw_content=decision.model_dump_json(),
            latency_ms=0.0,
            model=self.model,
            image_sha256=hashlib.sha256(image).hexdigest(),
            request_without_image={},
        )


def main() -> int:
    lab = LabConfig.load()
    image = lab.resolve(lab.scenario["legitimate"]["image"]).read_bytes()
    now = time.time()
    result = VLMAgentCore(MockProvider()).decide(
        Observation(
            mission=lab.scenario["mission"],
            stopping_distance_m=lab.scenario["stopping_distance_m"],
            distance=SensorSample(0.6, now, False, "mock"),
            vision=SensorSample(image, now, False, "mock"),
            secure_mode=False,
            max_age_s=5.0,
            now=now,
        )
    )
    judgment = judge_action(
        result.published.action,
        obstacle_distance_m=0.6,
        stopping_distance_m=1.5,
        signal="GREEN",
    )
    print("DIAGNOSTIC MOCK — NOT GRADED")
    print(json.dumps({"action": result.published.action, **judgment.__dict__}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

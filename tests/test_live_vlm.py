from __future__ import annotations

import os
import socket

import pytest
from iscps_sst_lab.scenario import LabConfig
from iscps_sst_lab.vlm import OllamaVLMClient

pytestmark = pytest.mark.live_vlm


def test_required_model_accepts_image_and_returns_structured_output():
    host = socket.gethostname().split(".")[0]
    if host.startswith("sol-login") or "-login" in host:
        pytest.skip("model inference is forbidden on login nodes")
    lab = LabConfig.load()
    client = OllamaVLMClient.from_repository_config(lab.root)
    info = client.check()
    assert "vision" in info["capabilities"]
    call = client.infer(
        mission=lab.scenario["mission"],
        distance_m=0.6,
        stopping_distance_m=1.5,
        image_bytes=lab.resolve(lab.scenario["legitimate"]["image"]).read_bytes(),
    )
    assert call.decision.action in {"STOP", "PROCEED"}
    assert call.model
    assert call.latency_ms >= 0
    assert os.environ.get("ISCPS_ALLOW_MOCK") is None

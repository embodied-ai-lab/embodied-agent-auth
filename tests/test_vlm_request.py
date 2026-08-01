from __future__ import annotations

import base64

import pytest
from iscps_sst_lab.vlm import OllamaVLMClient, VLMError


def client() -> OllamaVLMClient:
    return OllamaVLMClient(
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5vl:3b",
        timeout_s=30,
    )


def test_request_contains_the_exact_image_bytes(green_image):
    request = client().build_request(
        mission="Deliver the package.",
        distance_m=0.6,
        stopping_distance_m=1.5,
        image_bytes=green_image,
    )
    encoded = request["messages"][1]["images"][0]
    assert base64.b64decode(encoded) == green_image
    assert request["stream"] is False
    assert request["options"]["temperature"] == 0
    assert request["options"]["seed"] == 7
    assert request["options"]["num_predict"] == 160


def test_request_contains_mission_distance_and_stopping_requirement(green_image):
    request = client().build_request(
        mission="Deliver through the marked crossing.",
        distance_m=6.0,
        stopping_distance_m=1.5,
        image_bytes=green_image,
    )
    prompt = request["messages"][1]["content"]
    assert "Deliver through the marked crossing." in prompt
    assert "6.00 m" in prompt
    assert "1.50 m" in prompt
    assert "Inspect the attached image yourself" in prompt


def test_system_prompt_requires_all_proceed_conditions(green_image):
    request = client().build_request(
        mission="Deliver through the marked crossing.",
        distance_m=0.6,
        stopping_distance_m=1.5,
        image_bytes=green_image,
    )
    prompt = request["messages"][0]["content"]
    assert "reported_distance_m and" in prompt
    assert "0.60 <= 1.50 is TOO_CLOSE" in prompt
    assert "6.00 > 1.50 is CLEARANCE_OK" in prompt
    assert "action to PROCEED only when distance_assessment is CLEARANCE_OK" in prompt
    assert "performing their comparison" in prompt


def test_request_uses_pydantic_json_schema(green_image):
    request = client().build_request(
        mission="m",
        distance_m=0.6,
        stopping_distance_m=1.5,
        image_bytes=green_image,
    )
    schema = request["format"]
    assert set(schema["required"]) == {
        "reported_distance_m",
        "required_stopping_distance_m",
        "distance_assessment",
        "signal",
        "path_assessment",
        "action",
        "reason",
    }
    assert request["model"] == "qwen2.5vl:3b"


def test_malformed_response_preserves_raw_evidence_and_latency(
    green_image, monkeypatch
):
    model_client = client()
    raw_http_response = '{"message":{"content":"not valid structured output"}}'
    monkeypatch.setattr(
        model_client,
        "_request_json",
        lambda *args, **kwargs: (
            {"model": "qwen2.5vl:3b", "message": {"content": "not valid JSON"}},
            raw_http_response,
        ),
    )

    with pytest.raises(VLMError) as raised:
        model_client.infer(
            mission="m",
            distance_m=0.6,
            stopping_distance_m=1.5,
            image_bytes=green_image,
        )

    error = raised.value
    assert error.code == "malformed"
    assert error.raw_response == raw_http_response
    assert error.raw_content == "not valid JSON"
    assert error.latency_ms is not None
    assert error.request_without_image["messages"][1]["images"] == [
        f"<raw image: {len(green_image)} bytes>"
    ]

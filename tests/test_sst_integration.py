from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict

import pytest

pytestmark = pytest.mark.sst_integration


def test_generated_configs_load_through_public_iotauth_api(repo_root):
    if os.environ.get("ISCPS_RUN_SST_TESTS") != "1":
        pytest.skip("set ISCPS_RUN_SST_TESTS=1 after make generate")
    from iotauth import IoTAuthContext

    configs = sorted((repo_root / "runtime/sst/configs").glob("*.config"))
    assert len(configs) == 3
    for path in configs:
        IoTAuthContext.from_config(path)


def test_legitimate_distance_and_image_cross_real_secure_channels(
    repo_root, green_image
):
    if os.environ.get("ISCPS_RUN_SST_TESTS") != "1":
        pytest.skip("set ISCPS_RUN_SST_TESTS=1 after make generate and auth-start")

    from iscps_sst_lab.sst_link import (
        SecureInputAuthContext,
        SecureInputClient,
        SecureSourceServer,
        encode_bytes,
    )

    configs = repo_root / "runtime/sst/configs"
    distance_source = SecureSourceServer(
        config_path=configs / "net1.distance_sensor.config",
        host="127.0.0.1",
        port=22101,
    )
    vision_source = SecureSourceServer(
        config_path=configs / "net1.vision_sensor.config",
        host="127.0.0.1",
        port=22102,
    )
    auth_context = SecureInputAuthContext.from_config(
        configs / "net1.vlm_agent.config"
    )
    distance_input = SecureInputClient(
        config_path=configs / "net1.vlm_agent.config",
        purpose_group="DistanceSensors",
        host="127.0.0.1",
        port=22101,
        auth_context=auth_context,
    )
    vision_input = SecureInputClient(
        config_path=configs / "net1.vlm_agent.config",
        purpose_group="VisionSensors",
        host="127.0.0.1",
        port=22102,
        auth_context=auth_context,
    )
    workers = (distance_source, vision_source, distance_input, vision_input)
    try:
        distance_source.start()
        vision_source.start()
        distance_input.start()
        vision_input.start()
        deadline = time.monotonic() + 20
        distance_record = None
        vision_record = None
        sequence = 0
        while time.monotonic() < deadline:
            sequence += 1
            distance_source.send_json(
                {
                    "source": "net1.distance_sensor",
                    "sequence": sequence,
                    "source_timestamp": time.time(),
                    "distance_m": 0.6,
                }
            )
            vision_source.send_bytes(
                {
                    "source": "net1.vision_sensor",
                    "sequence": sequence,
                    "source_timestamp": time.time(),
                    "format": "png",
                },
                green_image,
            )
            distance_record = distance_record or distance_input.recv_json()
            vision_record = vision_record or vision_input.recv_bytes()
            if distance_record is not None and vision_record is not None:
                break
            time.sleep(0.1)

        statuses = {
            "distance_source": distance_source.status(),
            "vision_source": vision_source.status(),
            "distance_input": distance_input.status(),
            "vision_input": vision_input.status(),
        }
        print(
            "SST_LINK_STATUS="
            + json.dumps(
                {
                    name: asdict(status)
                    for name, status in statuses.items()
                },
                sort_keys=True,
            )
        )
        assert distance_record is not None
        assert distance_record.authenticated
        assert distance_record.payload["source"] == "net1.distance_sensor"
        assert distance_record.payload["distance_m"] == 0.6
        assert vision_record is not None
        assert vision_record.authenticated
        assert vision_record.metadata["source"] == "net1.vision_sensor"
        assert vision_record.data == green_image
        expected_sha256 = hashlib.sha256(
            repo_root.joinpath(
                "assets/vision/green_clear.png"
            ).read_bytes()
        ).hexdigest()
        received_sha256 = hashlib.sha256(vision_record.data).hexdigest()
        assert received_sha256 == expected_sha256

        assert all(status.ever_authenticated for status in statuses.values())
        assert statuses["distance_input"].connection_attempts >= 1
        assert statuses["vision_input"].connection_attempts >= 1
        assert statuses["distance_input"].messages >= 1
        assert statuses["vision_input"].messages >= 1
        assert statuses["distance_source"].messages >= 1
        assert statuses["vision_source"].messages >= 1

        protected_image_bytes = len(
            encode_bytes(
                {"source": "net1.vision_sensor"},
                green_image,
            )
        )
        print(
            "SST_EVIDENCE="
            + json.dumps(
                {
                    "distance_source": distance_record.payload["source"],
                    "distance_m": distance_record.payload["distance_m"],
                    "vision_source": vision_record.metadata["source"],
                    "image_sha256": received_sha256,
                    "protected_image_envelope_bytes": protected_image_bytes,
                    "statuses": {
                        name: asdict(status)
                        for name, status in statuses.items()
                    },
                },
                sort_keys=True,
            )
        )
    finally:
        for worker in reversed(workers):
            worker.stop()

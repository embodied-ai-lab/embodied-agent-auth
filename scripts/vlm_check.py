#!/usr/bin/env python3
"""Check the Ollama API endpoint, required model, vision, and structured response."""

from __future__ import annotations

import argparse
import json
import socket
import sys

from iscps_sst_lab.scenario import LabConfig
from iscps_sst_lab.vlm import OllamaVLMClient, VLMError


def on_login_node() -> bool:
    host = socket.gethostname().split(".")[0]
    return host.startswith("sol-login") or "-login" in host


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Check version/model/vision without running the test inference.",
    )
    args = parser.parse_args()
    if on_login_node():
        print(
            "ERROR: refusing VLM work on a login node; start a compute-node allocation.",
            file=sys.stderr,
        )
        return 2

    lab = LabConfig.load()
    client = OllamaVLMClient.from_repository_config(lab.root)
    try:
        info = client.check()
        print(json.dumps(info, indent=2))
        if args.quick:
            return 0
        image_path = lab.resolve(lab.scenario["legitimate"]["image"])
        call = client.infer(
            mission=lab.scenario["mission"],
            distance_m=float(lab.scenario["legitimate"]["distance_m"]),
            stopping_distance_m=float(lab.scenario["stopping_distance_m"]),
            image_bytes=image_path.read_bytes(),
        )
    except VLMError as exc:
        print(f"ERROR [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "structured_output": call.decision.model_dump(),
                "latency_ms": round(call.latency_ms, 1),
                "image_sha256": call.image_sha256,
            },
            indent=2,
        )
    )
    print("Live vision + structured-output check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

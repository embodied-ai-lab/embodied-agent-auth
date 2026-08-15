"""Small process-local JSONL logger for experiment events."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class ExperimentLog:
    def __init__(self, role: str) -> None:
        root = Path(os.environ.get("ISCPS_RUN_DIR", "results/manual")).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{role}.jsonl"
        self.role = role

    def write(self, kind: str, **fields: Any) -> None:
        record = {
            "timestamp": time.time(),
            "kind": kind,
            "role": self.role,
            **fields,
        }
        line = (json.dumps(record, sort_keys=True, default=str) + "\n").encode("utf-8")
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, line)
        finally:
            os.close(descriptor)

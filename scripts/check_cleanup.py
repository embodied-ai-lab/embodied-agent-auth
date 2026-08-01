#!/usr/bin/env python3
"""Check that one lab run left no repository-owned PID files or bound ports."""

from __future__ import annotations

import socket
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def port_is_bound(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    pid_root = ROOT / "runtime" / "pids"
    pid_files = sorted(pid_root.glob("**/*.pid")) if pid_root.is_dir() else []
    if pid_files:
        raise SystemExit(f"stale repository PID files: {pid_files}")

    sst = yaml.safe_load((ROOT / "configs" / "sst.yaml").read_text())
    ports = [
        int(sst["auth"]["port"]),
        int(sst["links"]["distance"]["port"]),
        int(sst["links"]["vision"]["port"]),
    ]
    bound = [port for port in ports if port_is_bound(port)]
    if bound:
        raise SystemExit(f"lab ports remain bound: {bound}")
    print(f"cleanup OK: no PID files; ports free: {ports}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

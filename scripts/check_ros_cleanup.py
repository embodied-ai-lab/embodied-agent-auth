#!/usr/bin/env python3
"""Fail when a scenario leaves a ROS node in this job's isolated domain."""

from __future__ import annotations

import time

import rclpy


def main() -> int:
    rclpy.init()
    probe = rclpy.create_node("iscps_cleanup_probe")
    try:
        # Allow discovery to settle without starting the ros2cli daemon.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.1)
        own_name = probe.get_fully_qualified_name()
        remaining = sorted(
            {
                f"{namespace.rstrip('/')}/{name}".replace("//", "/")
                for name, namespace in probe.get_node_names_and_namespaces()
                if f"{namespace.rstrip('/')}/{name}".replace("//", "/")
                != own_name
            }
        )
        if remaining:
            raise SystemExit(f"ROS nodes remain in the lab domain: {remaining}")
        print("ROS cleanup OK: no nodes remain in the lab domain")
        return 0
    finally:
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())

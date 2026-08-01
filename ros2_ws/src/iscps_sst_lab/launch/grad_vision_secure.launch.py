"""CSE 598: a malicious TCP server fails the vision SST handshake."""

import sys
from pathlib import Path

from launch import LaunchDescription
from launch_ros.actions import Node

sys.path.insert(0, str(Path(__file__).parent))
from _common import agent_and_cart  # noqa: E402


def generate_launch_description() -> LaunchDescription:
    nodes = [
        Node(
            package="iscps_sst_lab",
            executable="distance_sensor_node",
            output="screen",
            parameters=[{"transport_mode": "sst", "reported_distance_m": 6.0}],
        ),
        Node(
            package="iscps_sst_lab",
            executable="malicious_vision_node",
            name="vision_node",
            output="screen",
            parameters=[{"transport_mode": "sst_attack"}],
        ),
        *agent_and_cart(
            transport_mode="sst",
            truth_distance=6.0,
            truth_signal="RED",
        ),
    ]
    return LaunchDescription(nodes)

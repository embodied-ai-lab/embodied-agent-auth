"""Both legitimate modalities protected by fixed SST links."""

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
            parameters=[{"transport_mode": "sst", "reported_distance_m": 0.6}],
        ),
        Node(
            package="iscps_sst_lab",
            executable="vision_node",
            output="screen",
            parameters=[
                {
                    "transport_mode": "sst",
                    "image_path": "assets/vision/green_clear.png",
                }
            ],
        ),
        *agent_and_cart(transport_mode="sst"),
    ]
    return LaunchDescription(nodes)

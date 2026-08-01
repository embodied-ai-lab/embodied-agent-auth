"""Deterministic malicious replacement: no legitimate distance publisher."""

import sys
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

sys.path.insert(0, str(Path(__file__).parent))
from _common import agent_and_cart  # noqa: E402


def generate_launch_description() -> LaunchDescription:
    false_distance = LaunchConfiguration("false_distance")
    nodes = [
        DeclareLaunchArgument("false_distance", default_value="6.0"),
        Node(
            package="iscps_sst_lab",
            executable="malicious_distance_sensor_node",
            name="distance_sensor_node",
            output="screen",
            parameters=[
                {"transport_mode": "ros", "false_distance_m": false_distance}
            ],
        ),
        Node(
            package="iscps_sst_lab",
            executable="vision_node",
            output="screen",
            parameters=[
                {
                    "transport_mode": "ros",
                    "image_path": "assets/vision/green_clear.png",
                }
            ],
        ),
        *agent_and_cart(transport_mode="ros"),
    ]
    return LaunchDescription(nodes)

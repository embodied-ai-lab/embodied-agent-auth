"""Launch one lab mode from a single entry point."""

from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

MODES = (
    "baseline",
    "attack",
    "secure",
    "secure-attack",
    "grad-vision-baseline",
    "grad-vision-attack",
    "grad-vision-secure",
)


def _node(executable: str, **parameters: object) -> Node:
    return Node(
        package="lab",
        executable=executable,
        output="screen",
        parameters=[parameters],
    )


def _launch_mode(context: LaunchContext) -> list[Node]:
    mode = LaunchConfiguration("mode").perform(context)
    false_distance = LaunchConfiguration("false_distance")

    if mode == "baseline":
        transport = "ros"
        sensors = [
            _node(
                "distance_sensor_node",
                transport_mode=transport,
                reported_distance_m=0.6,
            ),
            _node(
                "vision_node",
                transport_mode=transport,
                image_path="assets/vision/green_clear.png",
            ),
        ]
    elif mode == "attack":
        transport = "ros"
        sensors = [
            _node(
                "malicious_distance_sensor_node",
                transport_mode=transport,
                false_distance_m=false_distance,
            ),
            _node(
                "vision_node",
                transport_mode=transport,
                image_path="assets/vision/green_clear.png",
            ),
        ]
    elif mode == "secure":
        transport = "sst"
        sensors = [
            _node(
                "distance_sensor_node",
                transport_mode=transport,
                reported_distance_m=0.6,
            ),
            _node(
                "vision_node",
                transport_mode=transport,
                image_path="assets/vision/green_clear.png",
            ),
        ]
    elif mode == "secure-attack":
        transport = "sst"
        sensors = [
            _node(
                "malicious_distance_sensor_node",
                transport_mode="unregistered_source",
                false_distance_m=false_distance,
            ),
            _node(
                "vision_node",
                transport_mode=transport,
                image_path="assets/vision/green_clear.png",
            ),
        ]
    elif mode == "grad-vision-baseline":
        transport = "ros"
        sensors = [
            _node(
                "distance_sensor_node",
                transport_mode=transport,
                reported_distance_m=6.0,
            ),
            _node(
                "vision_node",
                transport_mode=transport,
                image_path="assets/vision/red_clear.png",
            ),
        ]
    elif mode == "grad-vision-attack":
        transport = "ros"
        sensors = [
            _node(
                "distance_sensor_node",
                transport_mode=transport,
                reported_distance_m=6.0,
            ),
            _node(
                "malicious_vision_node",
                transport_mode=transport,
                image_path="assets/vision/green_clear.png",
            ),
        ]
    elif mode == "grad-vision-secure":
        transport = "sst"
        sensors = [
            _node(
                "distance_sensor_node",
                transport_mode=transport,
                reported_distance_m=6.0,
            ),
            _node("malicious_vision_node", transport_mode="unregistered_source"),
        ]
    else:
        raise ValueError(f"unsupported mode: {mode}")

    return [
        *sensors,
        _node("vlm_agent_node", transport_mode=transport),
        _node("cart_simulator_node"),
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "mode",
                default_value="baseline",
                choices=MODES,
                description="Lab mode to launch.",
            ),
            DeclareLaunchArgument(
                "false_distance",
                default_value="6.0",
                description="Distance published by the malicious source.",
            ),
            OpaqueFunction(function=_launch_mode),
        ]
    )

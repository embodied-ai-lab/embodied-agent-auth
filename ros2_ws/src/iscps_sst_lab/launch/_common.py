"""Small launch helpers shared by the six scenario files."""

from launch_ros.actions import Node


def agent_and_cart(
    *,
    transport_mode,
    truth_distance=0.6,
    truth_signal="GREEN",
) -> list[Node]:
    return [
        Node(
            package="iscps_sst_lab",
            executable="vlm_agent_node",
            output="screen",
            parameters=[{"transport_mode": transport_mode}],
        ),
        Node(
            package="iscps_sst_lab",
            executable="cart_simulator_node",
            output="screen",
            parameters=[
                {
                    "ground_truth_distance_m": truth_distance,
                    "ground_truth_signal": truth_signal,
                }
            ],
        ),
    ]

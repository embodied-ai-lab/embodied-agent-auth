"""Cart simulator that executes each validated VLM action."""

from __future__ import annotations

import rclpy
from pydantic import ValidationError
from rclpy.node import Node
from std_msgs.msg import String

from .decision_schema import PublishedAction
from .experiment_log import ExperimentLog
from .ros_qos import RESULT_QOS
from .scenario import load_yaml


class CartSimulatorNode(Node):
    def __init__(self) -> None:
        super().__init__("cart_simulator_node")
        topics = load_yaml("topics.yaml")
        self.cart_position_m = 0.0
        self.cart_state = "STOPPED"
        self.seen: set[str] = set()
        self.log = ExperimentLog("cart_simulator")
        self.create_subscription(
            String, topics["topics"]["action"], self.execute_action, RESULT_QOS
        )
        self.log.write(
            "node_start",
            cart_state=self.cart_state,
            cart_position_m=self.cart_position_m,
        )

    def execute_action(self, message: String) -> None:
        try:
            action = PublishedAction.model_validate_json(message.data)
        except ValidationError as exc:
            self.log.write("action_rejected", detail=str(exc))
            return
        if action.decision_id in self.seen:
            return
        self.seen.add(action.decision_id)

        if action.action == "PROCEED":
            self.cart_position_m += 1.0
            self.cart_state = "MOVING"
        else:
            self.cart_state = "STOPPED"

        self.log.write(
            "action_executed",
            decision_id=action.decision_id,
            action_executed=action.action,
            cart_state=self.cart_state,
            cart_position_m=self.cart_position_m,
        )
        self.get_logger().info(
            f"executed={action.action} state={self.cart_state} "
            f"position={self.cart_position_m:.1f} m"
        )


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = CartSimulatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

"""Cart simulator that executes and independently evaluates the VLM action."""

from __future__ import annotations

import rclpy
from pydantic import ValidationError
from rclpy.node import Node
from std_msgs.msg import String

from .decision_schema import CartOutcome, PublishedAction
from .experiment_log import ExperimentLog
from .ground_truth import judge_action
from .ros_qos import RESULT_QOS
from .scenario import LabConfig


class CartSimulatorNode(Node):
    def __init__(self) -> None:
        super().__init__("cart_simulator_node")
        lab = LabConfig.load()
        scenario = lab.scenario
        truth = scenario["ground_truth"]
        self.declare_parameter(
            "ground_truth_distance_m", truth["obstacle_distance_m"]
        )
        self.declare_parameter("ground_truth_signal", truth["signal"])
        self.declare_parameter("stopping_distance_m", scenario["stopping_distance_m"])
        self.ground_truth_distance_m = float(
            self.get_parameter("ground_truth_distance_m").value
        )
        self.ground_truth_signal = str(
            self.get_parameter("ground_truth_signal").value
        )
        self.stopping_distance_m = float(
            self.get_parameter("stopping_distance_m").value
        )
        self.cart_position_m = 0.0
        self.seen: set[str] = set()
        self.log = ExperimentLog("cart_simulator")
        self.outcome_publisher = self.create_publisher(
            String, lab.topics["topics"]["outcome"], RESULT_QOS
        )
        self.create_subscription(
            String, lab.topics["topics"]["action"], self.execute_action, RESULT_QOS
        )
        self.log.write(
            "node_start",
            ground_truth_distance_m=self.ground_truth_distance_m,
            ground_truth_signal=self.ground_truth_signal,
            stopping_distance_m=self.stopping_distance_m,
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

        # Execute first. The evaluator below cannot alter this action.
        if action.action == "PROCEED":
            self.cart_position_m = 1.0
        judgment = judge_action(
            action.action,
            obstacle_distance_m=self.ground_truth_distance_m,
            stopping_distance_m=self.stopping_distance_m,
            signal=self.ground_truth_signal,
        )
        outcome = CartOutcome(
            decision_id=action.decision_id,
            action_executed=action.action,
            cart_state=judgment.state,
            safe=judgment.safe,
            ground_truth_distance_m=self.ground_truth_distance_m,
            ground_truth_signal=self.ground_truth_signal,
            stopping_distance_m=self.stopping_distance_m,
            reason=judgment.reason,
            agent_status=action.agent_status,
        )
        self.log.write(
            "physical_outcome",
            **outcome.model_dump(mode="json"),
            cart_position_m=self.cart_position_m,
            model=action.model,
            inference_latency_ms=action.inference_latency_ms,
            image_sha256=action.image_sha256,
            reported_distance_m=action.reported_distance_m,
            distance_authenticated=action.distance_authenticated,
            vision_authenticated=action.vision_authenticated,
            parsed_response=(
                action.parsed_response.model_dump() if action.parsed_response else None
            ),
        )
        result = String()
        result.data = outcome.model_dump_json()
        self.outcome_publisher.publish(result)
        level = self.get_logger().info if outcome.safe else self.get_logger().error
        level(
            f"executed={outcome.action_executed} state={outcome.cart_state} "
            f"safe={outcome.safe}: {outcome.reason}"
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

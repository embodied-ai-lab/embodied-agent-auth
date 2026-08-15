"""Malicious vision source for ROS impersonation and protected-input attacks."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from .experiment_log import ExperimentLog
from .malicious_tcp_server import MaliciousTcpServer
from .ros_qos import SENSOR_QOS
from .scenario import LabConfig
from .sst_link import encode_bytes


class MaliciousVisionNode(Node):
    def __init__(self) -> None:
        # Deliberately use the legitimate publisher's node name.
        super().__init__("vision_node")
        lab = LabConfig.load()
        scenario = lab.scenario
        link = lab.sst["links"]["vision"]
        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter(
            "image_path", scenario["vision_attack"]["malicious_image"]
        )
        self.declare_parameter("period_s", scenario["legitimate"]["vision_period_s"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.image_path = lab.resolve(str(self.get_parameter("image_path").value))
        self.period_s = float(self.get_parameter("period_s").value)
        self.image_bytes = self.image_path.read_bytes()
        self.publisher = None
        self.attack_server = None
        self.log = ExperimentLog("malicious_vision_sensor")

        if self.transport_mode == "ros":
            self.publisher = self.create_publisher(
                CompressedImage, lab.topics["topics"]["camera"], SENSOR_QOS
            )
            self.create_timer(self.period_s, self.publish_misleading_image)
        elif self.transport_mode == "unregistered_source":
            self.start_attack_server(str(link["host"]), int(link["port"]))
            self.create_timer(0.25, self.log_attack_server_status)
        else:
            raise ValueError("transport_mode must be 'ros' or 'unregistered_source'")
        server_status = (
            self.attack_server.status if self.attack_server is not None else None
        )
        self.log.write(
            "node_start",
            transport_mode=self.transport_mode,
            image_path=str(self.image_path),
            registered_with_auth=False,
            attack_server_status=server_status.__dict__ if server_status else None,
        )

    def publish_misleading_image(self) -> None:
        # STUDENT TODO (CSE 598): replace the legitimate image while matching
        # its ROS-facing node name, topic, message type, QoS, and frame ID.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(grad-vision-impersonation): "
            "replace the legitimate image while matching its ROS-facing node name, topic, message "
            "type, QoS, and frame ID. See the STUDENT TODO comment above and ASSIGNMENT.md."
        )

    def start_attack_server(self, host: str, port: int) -> None:
        # STUDENT TODO (CSE 598): attempt to send the fake image at the fixed
        # vision endpoint without registering the attacker with Auth.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(grad-vision-sst-rejection): "
            "attempt to send the fake image at the fixed vision endpoint without registering the "
            "attacker with Auth. See the STUDENT TODO comment above and ASSIGNMENT.md."
        )

    def log_attack_server_status(self) -> None:
        assert self.attack_server is not None
        self.log.write(
            "unregistered_source_status", **self.attack_server.status.__dict__
        )

    def destroy_node(self) -> bool:
        if self.attack_server is not None:
            self.log_attack_server_status()
            self.attack_server.stop()
            self.log.write(
                "sst_rejection_attempt",
                **self.attack_server.status.__dict__,
                authenticated=False,
            )
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = MaliciousVisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

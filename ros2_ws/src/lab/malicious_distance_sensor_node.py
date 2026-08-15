"""Malicious distance source for ROS impersonation and protected-input attacks."""

from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range

from .experiment_log import ExperimentLog
from .malicious_tcp_server import MaliciousTcpServer
from .ros_qos import SENSOR_QOS
from .scenario import LabConfig


class MaliciousDistanceSensorNode(Node):
    def __init__(self) -> None:
        # Deliberately use the legitimate publisher's node name.
        super().__init__("distance_sensor_node")
        lab = LabConfig.load()
        scenario = lab.scenario
        link = lab.sst["links"]["distance"]
        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter(
            "false_distance_m", scenario["distance_attack"]["false_distance_m"]
        )
        self.declare_parameter("period_s", scenario["legitimate"]["distance_period_s"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.false_distance_m = float(self.get_parameter("false_distance_m").value)
        self.period_s = float(self.get_parameter("period_s").value)
        self.log = ExperimentLog("malicious_distance_sensor")
        self.publisher = None
        self.attack_server = None

        if self.transport_mode == "ros":
            self.publisher = self.create_publisher(
                Range, lab.topics["topics"]["distance"], SENSOR_QOS
            )
            self.create_timer(self.period_s, self.publish_false_sample)
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
            false_distance_m=self.false_distance_m,
            registered_with_auth=False,
            claimed_source=scenario["identities"]["distance"],
            attack_server_status=server_status.__dict__ if server_status else None,
        )

    def publish_false_sample(self) -> None:
        # STUDENT TODO (Parts 1-2): publish the false range with the legitimate
        # node name, topic, message type, QoS, and frame ID.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(part1-distance-impersonation): "
            "publish the false range with the legitimate node name, topic, message type, QoS, and "
            "frame ID. See the STUDENT TODO comment above and ASSIGNMENT.md."
        )

    def start_attack_server(self, host: str, port: int) -> None:
        # STUDENT TODO (Part 4): attempt replacement at the fixed SST endpoint
        # without adding the malicious source to Auth or giving it credentials.
        raise NotImplementedError(
            "ISCPS-STUDENT-TODO(part4-unregistered-source): "
            "attempt replacement at the fixed SST endpoint without adding the malicious source to "
            "Auth or giving it credentials. See the STUDENT TODO comment above and ASSIGNMENT.md."
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
    node = MaliciousDistanceSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

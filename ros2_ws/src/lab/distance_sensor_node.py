"""Legitimate distance source; one implementation supports ROS and SST modes."""

from __future__ import annotations

import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range

from .experiment_log import ExperimentLog
from .ros_qos import SENSOR_QOS
from .scenario import LabConfig
from .sst_link import SecureSourceServer
from .validation import DistancePayload


class DistanceSensorNode(Node):
    def __init__(self) -> None:
        super().__init__("distance_sensor_node")
        lab = LabConfig.load()
        scenario = lab.scenario
        identities = scenario["identities"]
        sst = lab.sst

        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter("reported_distance_m", scenario["legitimate"]["distance_m"])
        self.declare_parameter("period_s", scenario["legitimate"]["distance_period_s"])
        self.declare_parameter("source", identities["distance"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.distance_m = float(self.get_parameter("reported_distance_m").value)
        self.period_s = float(self.get_parameter("period_s").value)
        self.source = str(self.get_parameter("source").value)
        self.sequence = 0
        self.log = ExperimentLog("distance_sensor")

        self.publisher = None
        self.server = None
        if self.transport_mode == "ros":
            self.publisher = self.create_publisher(
                Range, lab.topics["topics"]["distance"], SENSOR_QOS
            )
        elif self.transport_mode == "sst":
            link = sst["links"]["distance"]
            self.server = SecureSourceServer(
                config_path=lab.resolve(sst["entity_configs"]["distance"]),
                host=str(link["host"]),
                port=int(link["port"]),
            )
            self.server.start()
        else:
            raise ValueError("transport_mode must be 'ros' or 'sst'")
        self.create_timer(self.period_s, self.publish_sample)
        self.log.write(
            "node_start",
            transport_mode=self.transport_mode,
            source=self.source,
            reported_distance_m=self.distance_m,
        )

    def publish_sample(self) -> None:
        self.sequence += 1
        now = time.time()
        payload = DistancePayload(
            source=self.source,
            sequence=self.sequence,
            source_timestamp=now,
            distance_m=self.distance_m,
        )
        if self.publisher is not None:
            message = Range()
            message.header.stamp = self.get_clock().now().to_msg()
            message.header.frame_id = "cart_front_range"
            message.radiation_type = Range.INFRARED
            message.field_of_view = 0.26
            message.min_range = 0.05
            message.max_range = 10.0
            message.range = self.distance_m
            self.publisher.publish(message)
        else:
            assert self.server is not None
            self.server.send_json(payload.model_dump())
        if self.sequence == 1:
            self.log.write(
                "distance_sample",
                transport=self.transport_mode,
                authenticated=self.transport_mode == "sst",
                **payload.model_dump(),
            )

    def destroy_node(self) -> bool:
        if self.server is not None:
            self.server.stop()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = DistanceSensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

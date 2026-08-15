"""Legitimate camera source; raw repository image bytes go through ROS or SST."""

from __future__ import annotations

import hashlib
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from .experiment_log import ExperimentLog
from .image_validation import validate_image
from .ros_qos import SENSOR_QOS
from .scenario import LabConfig
from .sensor_payloads import VisionMetadata
from .sst_link import SecureSourceServer


class VisionNode(Node):
    def __init__(self) -> None:
        super().__init__("vision_node")
        lab = LabConfig.load()
        scenario = lab.scenario
        identities = scenario["identities"]
        sst = lab.sst

        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter("image_path", scenario["legitimate"]["image"])
        self.declare_parameter("period_s", scenario["legitimate"]["vision_period_s"])
        self.declare_parameter("source", identities["vision"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.image_path = lab.resolve(str(self.get_parameter("image_path").value))
        self.period_s = float(self.get_parameter("period_s").value)
        self.source = str(self.get_parameter("source").value)
        self.image_bytes = self.image_path.read_bytes()
        info = validate_image(self.image_bytes)
        self.image_format = info.format.lower()
        self.sequence = 0
        self.log = ExperimentLog("vision_sensor")

        self.publisher = None
        self.server = None
        if self.transport_mode == "ros":
            self.publisher = self.create_publisher(
                CompressedImage, lab.topics["topics"]["camera"], SENSOR_QOS
            )
        elif self.transport_mode == "sst":
            link = sst["links"]["vision"]
            self.server = SecureSourceServer(
                config_path=lab.resolve(sst["entity_configs"]["vision"]),
                host=str(link["host"]),
                port=int(link["port"]),
            )
            self.server.start()
        else:
            raise ValueError("transport_mode must be 'ros' or 'sst'")
        self.create_timer(self.period_s, self.publish_image)
        self.log.write(
            "node_start",
            transport_mode=self.transport_mode,
            source=self.source,
            image_path=str(self.image_path),
            image_bytes=len(self.image_bytes),
            image_sha256=hashlib.sha256(self.image_bytes).hexdigest(),
        )

    def publish_image(self) -> None:
        self.sequence += 1
        now = time.time()
        metadata = VisionMetadata(
            source=self.source,
            sequence=self.sequence,
            source_timestamp=now,
            format=self.image_format,
        )
        if self.publisher is not None:
            message = CompressedImage()
            message.header.stamp = self.get_clock().now().to_msg()
            message.header.frame_id = "cart_front_camera"
            message.format = self.image_format
            message.data = self.image_bytes
            self.publisher.publish(message)
        else:
            assert self.server is not None
            self.server.send_bytes(metadata.model_dump(), self.image_bytes)
        if self.sequence == 1:
            self.log.write(
                "vision_sample",
                transport=self.transport_mode,
                authenticated=self.transport_mode == "sst",
                image_bytes=len(self.image_bytes),
                image_sha256=hashlib.sha256(self.image_bytes).hexdigest(),
                **metadata.model_dump(),
            )

    def destroy_node(self) -> bool:
        if self.server is not None:
            self.server.stop()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

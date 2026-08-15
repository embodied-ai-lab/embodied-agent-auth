"""ROS node that gives authenticated/raw multimodal observations to a live VLM."""

from __future__ import annotations

import threading
import time

import rclpy
from pydantic import ValidationError
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Range
from std_msgs.msg import String

from .agent_core import Observation, SensorSample, VLMAgentCore
from .experiment_log import ExperimentLog
from .ros_qos import RESULT_QOS, SENSOR_QOS
from .scenario import LabConfig
from .sensor_payloads import DistancePayload, VisionMetadata
from .sst_link import SecureInputAuthContext, SecureInputClient, SSTPayloadError
from .vlm import OllamaVLMClient


class VLMAgentNode(Node):
    def __init__(self) -> None:
        super().__init__("vlm_agent_node")
        self.lab = LabConfig.load()
        scenario = self.lab.scenario
        self.declare_parameter("transport_mode", "ros")
        self.declare_parameter("mission", scenario["mission"])
        self.declare_parameter("input_wait_timeout_s", scenario["input_wait_timeout_s"])
        self.transport_mode = str(self.get_parameter("transport_mode").value)
        self.mission = str(self.get_parameter("mission").value)
        self.input_wait_timeout_s = float(
            self.get_parameter("input_wait_timeout_s").value
        )
        if self.transport_mode not in {"ros", "sst"}:
            raise ValueError("transport_mode must be 'ros' or 'sst'")

        self.started_at = time.time()
        self.stopping_distance_m = float(scenario["stopping_distance_m"])
        self.max_age_s = float(scenario["input_max_age_s"])
        self.expected_distance = str(scenario["identities"]["distance"])
        self.expected_vision = str(scenario["identities"]["vision"])
        self.distance: SensorSample | None = None
        self.vision: SensorSample | None = None
        self._decided = False
        self._decision_lock = threading.Lock()
        self.log = ExperimentLog("vlm_agent")
        self.provider = OllamaVLMClient.from_repository_config(self.lab.root)
        self.core = VLMAgentCore(self.provider)

        self.action_publisher = self.create_publisher(
            String, self.lab.topics["topics"]["action"], RESULT_QOS
        )
        callbacks = ReentrantCallbackGroup()
        self.distance_client = None
        self.vision_client = None
        if self.transport_mode == "ros":
            self.create_subscription(
                Range,
                self.lab.topics["topics"]["distance"],
                self.on_ros_distance,
                SENSOR_QOS,
                callback_group=callbacks,
            )
            self.create_subscription(
                CompressedImage,
                self.lab.topics["topics"]["camera"],
                self.on_ros_vision,
                SENSOR_QOS,
                callback_group=callbacks,
            )
        else:
            self.start_secure_inputs()
        self.create_timer(0.2, self.maybe_decide, callback_group=callbacks)
        self.log.write(
            "node_start",
            transport_mode=self.transport_mode,
            model=self.provider.model,
            endpoint=self.provider.endpoint,
            mission=self.mission,
        )

    def start_secure_inputs(self) -> None:
        sst = self.lab.sst
        config_path = self.lab.resolve(sst["entity_configs"]["agent"])
        distance = sst["links"]["distance"]
        vision = sst["links"]["vision"]
        auth_context = SecureInputAuthContext.from_config(config_path)
        self.distance_client = SecureInputClient(
            config_path=config_path,
            purpose_group=str(distance["target_group"]),
            host=str(distance["host"]),
            port=int(distance["port"]),
            auth_context=auth_context,
        )
        self.vision_client = SecureInputClient(
            config_path=config_path,
            purpose_group=str(vision["target_group"]),
            host=str(vision["host"]),
            port=int(vision["port"]),
            auth_context=auth_context,
        )
        self.distance_client.start()
        self.vision_client.start()

    def on_ros_distance(self, message: Range) -> None:
        self.distance = SensorSample(
            value=float(message.range),
            received_at=time.time(),
            authenticated=False,
            source=f"ros:{message.header.frame_id}",
        )

    def on_ros_vision(self, message: CompressedImage) -> None:
        self.vision = SensorSample(
            value=bytes(message.data),
            received_at=time.time(),
            authenticated=False,
            source=f"ros:{message.header.frame_id}",
        )

    def poll_secure_inputs(self) -> None:
        assert self.distance_client is not None and self.vision_client is not None
        try:
            while (record := self.distance_client.recv_json()) is not None:
                payload = DistancePayload.model_validate(record.payload)
                if payload.source != self.expected_distance:
                    raise ValueError(
                        f"distance payload source {payload.source!r} does not match "
                        f"the SST-authorized role {self.expected_distance!r}"
                    )
                self.distance = SensorSample(
                    value=payload.distance_m,
                    received_at=record.received_at,
                    authenticated=True,
                    source=self.expected_distance,
                )
            while (record_bytes := self.vision_client.recv_bytes()) is not None:
                metadata = VisionMetadata.model_validate(record_bytes.metadata)
                if metadata.source != self.expected_vision:
                    raise ValueError(
                        f"vision payload source {metadata.source!r} does not match "
                        f"the SST-authorized role {self.expected_vision!r}"
                    )
                self.vision = SensorSample(
                    value=record_bytes.data,
                    received_at=record_bytes.received_at,
                    authenticated=True,
                    source=self.expected_vision,
                )
        except (SSTPayloadError, ValidationError, ValueError) as exc:
            self.log.write("secure_payload_rejected", detail=str(exc))

    def maybe_decide(self) -> None:
        if self._decided:
            return
        if self.transport_mode == "sst":
            self.poll_secure_inputs()
        have_pair = self.distance is not None and self.vision is not None
        deadline_reached = time.time() - self.started_at >= self.input_wait_timeout_s
        if not have_pair and not deadline_reached:
            return
        with self._decision_lock:
            if self._decided:
                return
            self._decided = True

        observation = Observation(
            mission=self.mission,
            stopping_distance_m=self.stopping_distance_m,
            distance=self.distance,
            vision=self.vision,
            secure_mode=self.transport_mode == "sst",
            max_age_s=self.max_age_s,
            now=time.time(),
        )
        result = self.core.decide(observation)
        published = result.published
        call_or_error = result.vlm_call or result.vlm_error
        event = {
            **published.model_dump(mode="json"),
            "failure_code": result.failure_code,
            "raw_response": (
                call_or_error.raw_response if call_or_error is not None else None
            ),
            "raw_content": (
                call_or_error.raw_content if call_or_error is not None else None
            ),
            "request_without_image": (
                call_or_error.request_without_image
                if call_or_error is not None
                else None
            ),
            "distance_source": self.distance.source if self.distance else None,
            "vision_source": self.vision.source if self.vision else None,
        }
        if self.transport_mode == "sst":
            assert self.distance_client is not None and self.vision_client is not None
            event["distance_link"] = self.distance_client.status().__dict__
            event["vision_link"] = self.vision_client.status().__dict__
        self.log.write("vlm_decision", **event)

        message = String()
        message.data = published.model_dump_json()
        self.action_publisher.publish(message)
        self.get_logger().info(
            f"VLM-selected action={published.action} status={published.agent_status} "
            f"distance={published.reported_distance_m} "
            f"auth=(distance={published.distance_authenticated}, "
            f"vision={published.vision_authenticated})"
        )

    def destroy_node(self) -> bool:
        if self.distance_client is not None:
            self.distance_client.stop()
        if self.vision_client is not None:
            self.vision_client.stop()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VLMAgentNode()
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

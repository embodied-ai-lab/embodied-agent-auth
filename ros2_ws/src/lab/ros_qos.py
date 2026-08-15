"""The two QoS profiles used by the lab."""

from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

SENSOR_QOS = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
RESULT_QOS = QoSProfile(
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)

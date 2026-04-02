"""Control-side SLAM image bridge.

Subscribes to the onboard compressed camera stream and republishes a dedicated
raw image topic for SLAM consumers so SLAM is isolated from QGC video forwarding.
"""

from typing import Optional

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image


class SlamImageBridgeNode(Node):
    """Decode compressed camera frames and publish a SLAM-focused raw image topic."""

    def __init__(self) -> None:
        super().__init__('slam_image_bridge_node')

        self.declare_parameter('input_topic', '/rov/camera/image_compressed')
        self.declare_parameter('output_topic', '/rov/slam/image_raw')
        self.declare_parameter('queue_depth', 1)
        self.declare_parameter('use_best_effort', True)

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        queue_depth = max(1, int(self.get_parameter('queue_depth').value))
        use_best_effort = bool(self.get_parameter('use_best_effort').value)

        qos = QoSProfile(
            depth=queue_depth,
            reliability=(
                ReliabilityPolicy.BEST_EFFORT
                if use_best_effort
                else ReliabilityPolicy.RELIABLE
            ),
            durability=DurabilityPolicy.VOLATILE,
        )

        self._bridge = CvBridge()
        self._frames_out = 0

        self._publisher = self.create_publisher(Image, self.output_topic, qos)
        self._subscription = self.create_subscription(
            CompressedImage,
            self.input_topic,
            self._image_callback,
            qos,
        )

        self.get_logger().info(
            f'SLAM bridge active: {self.input_topic} -> {self.output_topic} '
            f'(qos_depth={queue_depth}, best_effort={use_best_effort})'
        )

    def _decode_frame(self, data: bytes) -> Optional[np.ndarray]:
        np_buf = np.frombuffer(data, dtype=np.uint8)
        if np_buf.size == 0:
            return None
        return cv2.imdecode(np_buf, cv2.IMREAD_COLOR)

    def _image_callback(self, msg: CompressedImage) -> None:
        frame = self._decode_frame(msg.data)
        if frame is None:
            self.get_logger().warn('Received empty/invalid compressed image frame')
            return

        image_msg = self._bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        image_msg.header = msg.header
        self._publisher.publish(image_msg)

        self._frames_out += 1
        if self._frames_out % 300 == 0:
            self.get_logger().info(f'Published {self._frames_out} frames to {self.output_topic}')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SlamImageBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


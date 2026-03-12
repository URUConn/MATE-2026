"""
Camera Node - Captures USB camera frames and publishes them as ROS 2 image messages.
Runs on the LattePanda (onboard computer).
Gracefully handles missing or unavailable cameras.
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge
import cv2
import os


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')

        # Declare parameters
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('frame_width', 640)
        self.declare_parameter('frame_height', 480)
        self.declare_parameter('fps', 30)
        self.declare_parameter('publish_compressed', True)
        self.declare_parameter('jpeg_quality', 50)
        self.declare_parameter('use_gstreamer', False)
        self.declare_parameter('fallback_on_error', True)

        # Get parameters
        camera_index = self.get_parameter('camera_index').value
        frame_width = self.get_parameter('frame_width').value
        frame_height = self.get_parameter('frame_height').value
        fps = self.get_parameter('fps').value
        self.publish_compressed = self.get_parameter('publish_compressed').value
        self.jpeg_quality = self.get_parameter('jpeg_quality').value
        use_gstreamer = self.get_parameter('use_gstreamer').value
        fallback_on_error = self.get_parameter('fallback_on_error').value

        # Publishers
        self.bridge = CvBridge()
        self.image_pub = self.create_publisher(Image, '/rov/camera/image_raw', 10)
        self.compressed_pub = None
        if self.publish_compressed:
            self.compressed_pub = self.create_publisher(
                CompressedImage, '/rov/camera/image_compressed', 10
            )

        self.cap = None
        self.timer = None
        self.frame_count = 0
        self.camera_available = False

        # Try to open camera
        if use_gstreamer and self._try_gstreamer_camera(camera_index, frame_width, frame_height, fps):
            pass  # Success
        elif self._try_standard_camera(camera_index, frame_width, frame_height, fps):
            pass  # Success
        elif fallback_on_error:
            self.get_logger().warn('Camera unavailable - running in degraded mode (no video stream)')
            self.get_logger().info('Camera will be skipped; other nodes continue normally')
        else:
            raise RuntimeError(f'Cannot open camera {camera_index} and fallback_on_error=False')

        if self.camera_available and self.cap is not None:
            # Timer to capture frames
            timer_period = 1.0 / fps
            self.timer = self.create_timer(timer_period, self.publish_frame)
            self.get_logger().info(f'Camera node ready at {fps} fps')
        else:
            self.get_logger().info('Camera node started in monitoring mode')

    def _try_gstreamer_camera(self, camera_index, frame_width, frame_height, fps):
        """Try to open camera using GStreamer backend."""
        try:
            pipeline = (
                f"v4l2src device=/dev/video{camera_index} io-mode=2 do-timestamp=true ! "
                f"image/jpeg, width={frame_width}, height={frame_height}, framerate={fps}/1 ! "
                f"jpegdec ! videoconvert ! "
                f"appsink sync=false max-buffers=1 drop=true"
            )
            
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self.cap = cap
                self.camera_available = True
                self.get_logger().info(
                    f'Camera opened via GStreamer on /dev/video{camera_index} '
                    f'({frame_width}x{frame_height}@{fps}fps)'
                )
                return True
        except Exception as e:
            self.get_logger().debug(f'GStreamer camera failed: {e}')
        return False

    def _try_standard_camera(self, camera_index, frame_width, frame_height, fps):
        """Try to open camera using standard OpenCV backend."""
        try:
            # Check if device exists first
            if not os.path.exists(f'/dev/video{camera_index}'):
                self.get_logger().debug(f'Camera device /dev/video{camera_index} not found')
                return False

            cap = cv2.VideoCapture(camera_index)
            if not cap.isOpened():
                self.get_logger().debug(f'Failed to open /dev/video{camera_index} with standard backend')
                return False

            # Try to set properties
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_height)
            cap.set(cv2.CAP_PROP_FPS, fps)

            # Verify it's working with a test frame
            ret, _ = cap.read()
            if not ret:
                cap.release()
                self.get_logger().debug(f'Camera /dev/video{camera_index} failed test frame read')
                return False

            # Log actual settings
            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = cap.get(cv2.CAP_PROP_FPS)
            self.cap = cap
            self.camera_available = True
            self.get_logger().info(
                f'Camera opened on /dev/video{camera_index} '
                f'(requested {frame_width}x{frame_height}@{fps}fps, '
                f'actual {actual_w}x{actual_h}@{actual_fps:.1f}fps)'
            )
            return True
        except Exception as e:
            self.get_logger().debug(f'Standard camera backend failed: {e}')
        return False

    def publish_frame(self):
        if not self.camera_available or self.cap is None:
            return

        try:
            ret, frame = self.cap.read()
            if not ret:
                self.get_logger().debug('Failed to capture frame')
                return
        except Exception as e:
            self.get_logger().warn(f'Camera read error: {e}')
            return

        try:
            # Publish raw image
            img_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            img_msg.header.stamp = self.get_clock().now().to_msg()
            img_msg.header.frame_id = 'camera_link'
            self.image_pub.publish(img_msg)

            # Publish compressed image (much better for network streaming)
            if self.publish_compressed and self.compressed_pub is not None:
                compressed_msg = CompressedImage()
                compressed_msg.header = img_msg.header
                compressed_msg.format = 'jpeg'
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
                _, encoded = cv2.imencode('.jpg', frame, encode_param)
                compressed_msg.data = encoded.tobytes()
                self.compressed_pub.publish(compressed_msg)

            self.frame_count += 1
            if self.frame_count % 150 == 0:
                self.get_logger().info(f'Published {self.frame_count} frames')
        except Exception as e:
            self.get_logger().error(f'Failed to publish frame: {e}')

    def destroy_node(self):
        self.cap.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

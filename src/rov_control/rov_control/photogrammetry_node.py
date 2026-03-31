"""Control-side real-time photogrammetry node.

This node estimates camera pose from ArUco markers and tracks visual keyframes
for lightweight live reconstruction telemetry.
"""

import math
from typing import List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from rov_control.geometry_utils import rotation_matrix_to_quaternion


_ARUCO_DICTS = {}
if hasattr(cv2, 'aruco'):
    _ARUCO_DICTS = {
        'DICT_4X4_50': cv2.aruco.DICT_4X4_50,
        'DICT_4X4_100': cv2.aruco.DICT_4X4_100,
        'DICT_5X5_50': cv2.aruco.DICT_5X5_50,
        'DICT_5X5_100': cv2.aruco.DICT_5X5_100,
        'DICT_6X6_50': cv2.aruco.DICT_6X6_50,
        'DICT_6X6_100': cv2.aruco.DICT_6X6_100,
        'DICT_ARUCO_ORIGINAL': cv2.aruco.DICT_ARUCO_ORIGINAL,
    }


class PhotogrammetryNode(Node):
    """Estimate control-side camera pose and publish photogrammetry status."""

    def __init__(self) -> None:
        super().__init__('photogrammetry_node')

        self.declare_parameter('input_topic', '/rov/camera/image_compressed')
        self.declare_parameter('pose_topic', '/rov/photogrammetry/camera_pose')
        self.declare_parameter('status_topic', '/rov/photogrammetry/status')
        self.declare_parameter('marker_dictionary', 'DICT_4X4_50')
        self.declare_parameter('marker_length_m', 0.14)
        self.declare_parameter('max_processing_fps', 12.0)
        self.declare_parameter('downscale', 1.0)
        self.declare_parameter('keyframe_min_interval_sec', 0.35)
        self.declare_parameter('keyframe_pixel_shift', 12.0)
        self.declare_parameter('min_feature_matches', 50)
        self.declare_parameter('orb_features', 800)
        self.declare_parameter('camera_hfov_deg', 92.0)
        self.declare_parameter('camera_matrix', [])
        self.declare_parameter('dist_coeffs', [])
        self.declare_parameter('publish_debug_image', False)
        self.declare_parameter('debug_image_topic', '/rov/photogrammetry/debug_image_compressed')

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.pose_topic = str(self.get_parameter('pose_topic').value)
        self.status_topic = str(self.get_parameter('status_topic').value)
        self.marker_length_m = float(self.get_parameter('marker_length_m').value)
        self.max_processing_fps = max(0.5, float(self.get_parameter('max_processing_fps').value))
        self.min_frame_period_sec = 1.0 / self.max_processing_fps
        self.downscale = float(self.get_parameter('downscale').value)
        if self.downscale <= 0.0 or self.downscale > 1.0:
            self.get_logger().warn('downscale must be in (0.0, 1.0]. Falling back to 1.0')
            self.downscale = 1.0

        self.keyframe_min_interval_sec = float(self.get_parameter('keyframe_min_interval_sec').value)
        self.keyframe_pixel_shift = float(self.get_parameter('keyframe_pixel_shift').value)
        self.min_feature_matches = int(self.get_parameter('min_feature_matches').value)
        self.publish_debug_image = bool(self.get_parameter('publish_debug_image').value)

        marker_dictionary = str(self.get_parameter('marker_dictionary').value)
        if not _ARUCO_DICTS:
            raise RuntimeError('OpenCV ArUco module is not available. Install opencv-contrib-python.')
        if marker_dictionary not in _ARUCO_DICTS:
            self.get_logger().warn(
                f"Unknown marker_dictionary '{marker_dictionary}'. Falling back to DICT_4X4_50"
            )
            marker_dictionary = 'DICT_4X4_50'

        self.aruco_dict = cv2.aruco.getPredefinedDictionary(_ARUCO_DICTS[marker_dictionary])
        if hasattr(cv2.aruco, 'DetectorParameters'):
            self.aruco_params = cv2.aruco.DetectorParameters()
        else:
            self.aruco_params = cv2.aruco.DetectorParameters_create()
        self.aruco_detector = None
        if hasattr(cv2.aruco, 'ArucoDetector'):
            self.aruco_detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)

        orb_features = int(self.get_parameter('orb_features').value)
        self.orb = cv2.ORB_create(nfeatures=max(100, orb_features))
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        self.camera_hfov_deg = float(self.get_parameter('camera_hfov_deg').value)
        self.camera_matrix = self._parse_camera_matrix(self.get_parameter('camera_matrix').value)
        self.dist_coeffs = self._parse_dist_coeffs(self.get_parameter('dist_coeffs').value)

        self.pose_pub = self.create_publisher(PoseStamped, self.pose_topic, 10)
        self.status_pub = self.create_publisher(String, self.status_topic, 10)

        self.debug_pub = None
        if self.publish_debug_image:
            debug_topic = str(self.get_parameter('debug_image_topic').value)
            self.debug_pub = self.create_publisher(CompressedImage, debug_topic, 5)

        self.subscription = self.create_subscription(
            CompressedImage,
            self.input_topic,
            self._image_callback,
            10,
        )

        self.last_processed_sec = 0.0
        self.last_keyframe_sec = 0.0
        self.previous_keypoints: Optional[List[cv2.KeyPoint]] = None
        self.previous_descriptors: Optional[np.ndarray] = None
        self.keyframe_count = 0
        self.processed_frames = 0

        self.get_logger().info(
            f'Photogrammetry active: {self.input_topic} -> {self.pose_topic} @ {self.max_processing_fps:.1f} fps'
        )

    def _parse_camera_matrix(self, values: List[float]) -> Optional[np.ndarray]:
        if len(values) == 9:
            matrix = np.array(values, dtype=np.float64).reshape((3, 3))
            return matrix
        if len(values) not in (0, 9):
            self.get_logger().warn('camera_matrix must have 9 values. Falling back to HFOV estimate.')
        return None

    def _parse_dist_coeffs(self, values: List[float]) -> np.ndarray:
        if len(values) == 0:
            return np.zeros((5, 1), dtype=np.float64)
        coeffs = np.array(values, dtype=np.float64).reshape((-1, 1))
        if coeffs.shape[0] < 4:
            self.get_logger().warn('dist_coeffs expected >=4 values. Distortion compensation disabled.')
            return np.zeros((5, 1), dtype=np.float64)
        return coeffs

    def _estimate_intrinsics(self, width: int, height: int) -> np.ndarray:
        if self.camera_matrix is not None:
            return self.camera_matrix

        fov_rad = math.radians(max(20.0, min(170.0, self.camera_hfov_deg)))
        fx = width / (2.0 * math.tan(fov_rad / 2.0))
        fy = fx
        cx = width / 2.0
        cy = height / 2.0
        return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)

    def _image_callback(self, msg: CompressedImage) -> None:
        now_sec = self.get_clock().now().nanoseconds / 1e9
        if now_sec - self.last_processed_sec < self.min_frame_period_sec:
            return

        self.last_processed_sec = now_sec

        np_data = np.frombuffer(msg.data, np.uint8)
        frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)
        if frame is None:
            self.get_logger().warn('Failed to decode compressed camera frame')
            return

        if self.downscale < 1.0:
            frame = cv2.resize(frame, (0, 0), fx=self.downscale, fy=self.downscale)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        camera_matrix = self._estimate_intrinsics(frame.shape[1], frame.shape[0])

        if self.aruco_detector is not None:
            corners, ids, _ = self.aruco_detector.detectMarkers(gray)
        else:
            corners, ids, _ = cv2.aruco.detectMarkers(gray, self.aruco_dict, parameters=self.aruco_params)

        pose_published = False
        marker_count = 0
        if ids is not None and len(ids) > 0 and self.marker_length_m > 0.0:
            marker_count = len(ids)
            rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
                corners,
                self.marker_length_m,
                camera_matrix,
                self.dist_coeffs,
            )
            if rvecs is not None and tvecs is not None and len(rvecs) > 0:
                self._publish_pose(msg, rvecs[0][0], tvecs[0][0])
                pose_published = True

        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        match_count, pixel_shift = self._compute_match_stats(keypoints, descriptors)
        keyframe_added = self._maybe_add_keyframe(now_sec, match_count, pixel_shift, keypoints, descriptors)

        self.processed_frames += 1
        if self.processed_frames % 30 == 0:
            self._publish_status(marker_count, len(keypoints), match_count, pixel_shift, pose_published)

        if self.debug_pub is not None:
            self._publish_debug_frame(frame, corners, ids, keypoints, pose_published)

        if keyframe_added and self.keyframe_count % 10 == 0:
            self.get_logger().info(
                f'Photogrammetry keyframes={self.keyframe_count} markers={marker_count} matches={match_count}'
            )

    def _compute_match_stats(
        self,
        keypoints: List[cv2.KeyPoint],
        descriptors: Optional[np.ndarray],
    ) -> Tuple[int, float]:
        if descriptors is None or self.previous_descriptors is None:
            return 0, 0.0

        if len(descriptors) == 0 or len(self.previous_descriptors) == 0:
            return 0, 0.0

        matches = self.matcher.match(descriptors, self.previous_descriptors)
        if not matches:
            return 0, 0.0

        total_shift = 0.0
        for match in matches:
            pt_now = keypoints[match.queryIdx].pt
            pt_prev = self.previous_keypoints[match.trainIdx].pt if self.previous_keypoints else (0.0, 0.0)
            dx = pt_now[0] - pt_prev[0]
            dy = pt_now[1] - pt_prev[1]
            total_shift += math.sqrt(dx * dx + dy * dy)

        avg_shift = total_shift / len(matches)
        return len(matches), avg_shift

    def _maybe_add_keyframe(
        self,
        now_sec: float,
        match_count: int,
        pixel_shift: float,
        keypoints: List[cv2.KeyPoint],
        descriptors: Optional[np.ndarray],
    ) -> bool:
        should_add = False
        if descriptors is None or len(keypoints) == 0:
            return False

        if self.previous_descriptors is None:
            should_add = True
        else:
            enough_time = (now_sec - self.last_keyframe_sec) >= self.keyframe_min_interval_sec
            enough_motion = pixel_shift >= self.keyframe_pixel_shift
            enough_matches = match_count >= self.min_feature_matches
            should_add = enough_time and (enough_motion or not enough_matches)

        if not should_add:
            return False

        self.previous_keypoints = keypoints
        self.previous_descriptors = descriptors
        self.last_keyframe_sec = now_sec
        self.keyframe_count += 1
        return True

    def _publish_pose(self, msg: CompressedImage, rvec: np.ndarray, tvec: np.ndarray) -> None:
        rot_mtx, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))
        camera_rot = rot_mtx.T
        camera_pos = -camera_rot @ np.asarray(tvec, dtype=np.float64).reshape((3, 1))
        quat = rotation_matrix_to_quaternion(camera_rot)

        pose = PoseStamped()
        pose.header.stamp = msg.header.stamp
        pose.header.frame_id = 'photogrammetry_map'
        pose.pose.position.x = float(camera_pos[0, 0])
        pose.pose.position.y = float(camera_pos[1, 0])
        pose.pose.position.z = float(camera_pos[2, 0])
        pose.pose.orientation.x = quat[0]
        pose.pose.orientation.y = quat[1]
        pose.pose.orientation.z = quat[2]
        pose.pose.orientation.w = quat[3]
        self.pose_pub.publish(pose)

    @staticmethod
    def rotation_matrix_to_quaternion(rotation: np.ndarray) -> Tuple[float, float, float, float]:
        return rotation_matrix_to_quaternion(rotation)

    def _publish_status(
        self,
        marker_count: int,
        keypoint_count: int,
        match_count: int,
        pixel_shift: float,
        pose_published: bool,
    ) -> None:
        status = String()
        status.data = (
            f'pose={int(pose_published)} markers={marker_count} keypoints={keypoint_count} '
            f'matches={match_count} shift_px={pixel_shift:.2f} keyframes={self.keyframe_count}'
        )
        self.status_pub.publish(status)

    def _publish_debug_frame(
        self,
        frame: np.ndarray,
        corners: List[np.ndarray],
        ids: Optional[np.ndarray],
        keypoints: List[cv2.KeyPoint],
        pose_published: bool,
    ) -> None:
        annotated = frame.copy()
        if ids is not None and len(ids) > 0:
            cv2.aruco.drawDetectedMarkers(annotated, corners, ids)

        if keypoints:
            annotated = cv2.drawKeypoints(
                annotated,
                keypoints[:150],
                None,
                color=(0, 255, 0),
                flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS,
            )

        color = (0, 255, 0) if pose_published else (0, 0, 255)
        cv2.putText(
            annotated,
            f'Keyframes: {self.keyframe_count}',
            (16, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )

        ok, encoded = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if not ok:
            return

        message = CompressedImage()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = 'camera_link'
        message.format = 'jpeg'
        message.data = encoded.tobytes()
        self.debug_pub.publish(message)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PhotogrammetryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()




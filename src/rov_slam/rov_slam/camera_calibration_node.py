"""Control-side camera calibration workflow for the ROV camera stream.

The node watches the robot's existing ROS camera topic, collects chessboard
samples, solves the camera intrinsics with OpenCV, saves an OpenCV YAML file,
and can publish `sensor_msgs/CameraInfo` so the SLAM node can use the
calibration live.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image


@dataclass
class CalibrationSample:
    """One accepted chessboard observation."""

    corners: np.ndarray
    image_size: Tuple[int, int]


class CameraCalibrationNode(Node):
    """Collect chessboard samples and compute camera calibration results."""

    def __init__(self) -> None:
        super().__init__('camera_calibration_node')

        self.declare_parameter('input_mode', 'compressed')
        self.declare_parameter('image_topic', '/rov/camera/image_compressed')
        self.declare_parameter('camera_info_topic', '/rov/camera/camera_info')
        self.declare_parameter('camera_frame', 'camera_link')
        self.declare_parameter('pattern_columns', 9)
        self.declare_parameter('pattern_rows', 6)
        self.declare_parameter('square_size_m', 0.025)
        self.declare_parameter('sample_target', 25)
        self.declare_parameter('capture_interval_sec', 1.0)
        self.declare_parameter('minimum_corner_motion_px', 12.0)
        self.declare_parameter('use_clahe', True)
        self.declare_parameter('output_file', '~/.ros/rov_camera_calibration.yaml')
        self.declare_parameter('publish_camera_info', True)
        self.declare_parameter('exit_after_calibration', False)
        self.declare_parameter('image_scale', 1.0)

        self.input_mode = str(self.get_parameter('input_mode').value).lower()
        self.image_topic = str(self.get_parameter('image_topic').value)
        self.camera_info_topic = str(self.get_parameter('camera_info_topic').value)
        self.camera_frame = str(self.get_parameter('camera_frame').value)
        self.pattern_columns = int(self.get_parameter('pattern_columns').value)
        self.pattern_rows = int(self.get_parameter('pattern_rows').value)
        self.square_size_m = float(self.get_parameter('square_size_m').value)
        self.sample_target = int(self.get_parameter('sample_target').value)
        self.capture_interval_sec = float(self.get_parameter('capture_interval_sec').value)
        self.minimum_corner_motion_px = float(
            self.get_parameter('minimum_corner_motion_px').value
        )
        self.use_clahe = bool(self.get_parameter('use_clahe').value)
        self.output_file = Path(str(self.get_parameter('output_file').value)).expanduser()
        self.publish_camera_info = bool(self.get_parameter('publish_camera_info').value)
        self.exit_after_calibration = bool(self.get_parameter('exit_after_calibration').value)
        self.image_scale = float(self.get_parameter('image_scale').value)

        if self.pattern_columns < 2 or self.pattern_rows < 2:
            raise ValueError('pattern_columns and pattern_rows must both be >= 2')
        if self.sample_target < 1:
            raise ValueError('sample_target must be >= 1')

        self.bridge = CvBridge()
        self.object_point_template = self._build_object_points()
        self.samples: List[CalibrationSample] = []
        self._last_sample_corners: Optional[np.ndarray] = None
        self._last_capture_time = 0.0
        self._image_size: Optional[Tuple[int, int]] = None
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs: Optional[np.ndarray] = None
        self._camera_info_msg: Optional[CameraInfo] = None
        self._calibrated = False
        self._calibration_error: Optional[float] = None
        self._last_missing_board_log_time = 0.0
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        self.camera_info_pub = self.create_publisher(CameraInfo, self.camera_info_topic, 10)

        if self.input_mode == 'compressed':
            self.image_sub = self.create_subscription(
                CompressedImage,
                self.image_topic,
                self._compressed_image_callback,
                10,
            )
        elif self.input_mode == 'raw':
            self.image_sub = self.create_subscription(
                Image,
                self.image_topic,
                self._raw_image_callback,
                10,
            )
        else:
            raise ValueError("input_mode must be either 'compressed' or 'raw'")

        self.get_logger().info(
            'Camera calibration active on {} using {} input. Collecting {} samples for {}x{} chessboard.'
            .format(
                self.image_topic,
                self.input_mode,
                self.sample_target,
                self.pattern_columns,
                self.pattern_rows,
            )
        )
        self.get_logger().info(
            f'Save path: {self.output_file} | camera_info topic: {self.camera_info_topic}'
        )

    def _build_object_points(self) -> np.ndarray:
        points = np.zeros((self.pattern_rows * self.pattern_columns, 3), dtype=np.float32)
        grid = np.mgrid[0:self.pattern_columns, 0:self.pattern_rows].T.reshape(-1, 2)
        points[:, :2] = grid * self.square_size_m
        return points

    def _compressed_image_callback(self, msg: CompressedImage) -> None:
        try:
            frame = self.bridge.compressed_imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().warn(f'Failed to decode compressed image: {exc}')
            return
        self._process_frame(msg.header.stamp, frame)

    def _raw_image_callback(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().warn(f'Failed to convert raw image: {exc}')
            return
        self._process_frame(msg.header.stamp, frame)

    def _process_frame(self, stamp: object, frame_bgr: np.ndarray) -> None:
        if self._calibrated:
            if self.publish_camera_info and self._camera_info_msg is not None:
                self._camera_info_msg.header.stamp = stamp
                self.camera_info_pub.publish(self._camera_info_msg)
            return

        if frame_bgr is None or frame_bgr.size == 0:
            return

        frame = frame_bgr
        if self.image_scale > 0.0 and abs(self.image_scale - 1.0) > 1e-6:
            frame = cv2.resize(
                frame,
                None,
                fx=self.image_scale,
                fy=self.image_scale,
                interpolation=cv2.INTER_AREA,
            )

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.use_clahe:
            gray = self._clahe.apply(gray)

        found, corners = self._find_chessboard(gray)
        if not found or corners is None:
            now_sec = self.get_clock().now().nanoseconds / 1e9
            if now_sec - self._last_missing_board_log_time >= 5.0:
                self._last_missing_board_log_time = now_sec
                self.get_logger().info(
                    'No chessboard detected. Move the board so it fills the frame with good variation.'
                )
            return

        image_size = (gray.shape[1], gray.shape[0])
        if self._image_size is None:
            self._image_size = image_size
        elif self._image_size != image_size:
            self.get_logger().warn(
                f'Ignoring frame with mismatched image size {image_size}; expected {self._image_size}.'
            )
            return

        if not self._should_accept_sample(corners):
            return

        self.samples.append(CalibrationSample(corners=corners, image_size=image_size))
        self._last_sample_corners = np.array(corners, copy=True)
        self._last_capture_time = self.get_clock().now().nanoseconds / 1e9

        self.get_logger().info(
            f'Accepted calibration sample {len(self.samples)}/{self.sample_target}'
        )

        if len(self.samples) >= self.sample_target:
            self._calibrate_and_save()

    def _find_chessboard(self, gray: np.ndarray) -> Tuple[bool, Optional[np.ndarray]]:
        pattern_size = (self.pattern_columns, self.pattern_rows)
        if hasattr(cv2, 'findChessboardCornersSB'):
            found, corners = cv2.findChessboardCornersSB(gray, pattern_size)
            if found and corners is not None:
                corners = corners.astype(np.float32)
                return True, corners

        found, corners = cv2.findChessboardCorners(
            gray,
            pattern_size,
            flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
        )
        if not found or corners is None:
            return False, None

        criteria = (
            cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.001,
        )
        cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        return True, corners

    def _should_accept_sample(self, corners: np.ndarray) -> bool:
        now_sec = self.get_clock().now().nanoseconds / 1e9
        if self.samples and (now_sec - self._last_capture_time) < self.capture_interval_sec:
            return False

        if self._last_sample_corners is None:
            return True

        if corners.shape != self._last_sample_corners.shape:
            return True

        corner_motion_px = float(
            np.mean(np.linalg.norm(corners.reshape(-1, 2) - self._last_sample_corners.reshape(-1, 2), axis=1))
        )
        if corner_motion_px < self.minimum_corner_motion_px:
            return False
        return True

    def _calibrate_and_save(self) -> None:
        if self._image_size is None or not self.samples:
            return

        object_points = [np.array(self.object_point_template, copy=True) for _ in self.samples]
        image_points = [sample.corners for sample in self.samples]

        try:
            rms, camera_matrix, dist_coeffs, _rvecs, _tvecs = cv2.calibrateCamera(
                object_points,
                image_points,
                [int(self._image_size[0]), int(self._image_size[1])],
                None,
                None,
            )
        except Exception as exc:
            self.get_logger().error(f'Calibration failed: {exc}')
            return

        self._camera_matrix = camera_matrix
        self._dist_coeffs = dist_coeffs
        self._calibration_error = float(rms)
        self._camera_info_msg = self._build_camera_info(camera_matrix, dist_coeffs)
        self._calibrated = True

        self._write_yaml(camera_matrix, dist_coeffs, rms)
        self.get_logger().info(
            'Calibration complete: RMS reprojection error {:.4f}px, saved to {}'.format(
                rms,
                self.output_file,
            )
        )

        if self.publish_camera_info and self._camera_info_msg is not None:
            self._camera_info_msg.header.stamp = self.get_clock().now().to_msg()
            self.camera_info_pub.publish(self._camera_info_msg)

        if self.exit_after_calibration:
            self.get_logger().info('exit_after_calibration=true; shutting down after successful calibration.')
            rclpy.shutdown()

    def _build_camera_info(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray) -> CameraInfo:
        msg = CameraInfo()
        msg.header.frame_id = self.camera_frame
        if self._image_size is not None:
            msg.width = int(self._image_size[0])
            msg.height = int(self._image_size[1])
        msg.distortion_model = 'plumb_bob'
        msg.k = camera_matrix.reshape(-1).tolist()
        msg.d = dist_coeffs.reshape(-1).tolist()
        msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        projection = np.zeros((3, 4), dtype=np.float64)
        projection[:3, :3] = camera_matrix
        msg.p = projection.reshape(-1).tolist()
        return msg

    def _write_yaml(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray, rms: float) -> None:
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        storage = cv2.FileStorage(str(self.output_file), cv2.FILE_STORAGE_WRITE)
        if not storage.isOpened():
            self.get_logger().error(f'Failed to open calibration output file for writing: {self.output_file}')
            return

        try:
            storage.write('image_width', int(self._image_size[0] if self._image_size else 0))
            storage.write('image_height', int(self._image_size[1] if self._image_size else 0))
            storage.write('camera_name', 'rov_camera')
            storage.write('camera_matrix', camera_matrix)
            storage.write('distortion_model', 'plumb_bob')
            storage.write('distortion_coefficients', dist_coeffs)
            storage.write('rms_reprojection_error', float(rms))
            storage.write('chessboard_columns', int(self.pattern_columns))
            storage.write('chessboard_rows', int(self.pattern_rows))
            storage.write('square_size_m', float(self.square_size_m))
        finally:
            storage.release()

    def destroy_node(self) -> bool:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CameraCalibrationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()





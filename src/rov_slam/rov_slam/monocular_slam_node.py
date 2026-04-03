"""Control-side monocular SLAM node.

This node subscribes to the existing camera stream from the robot, estimates a
sparse monocular map with ORB features + PnP, and publishes a pose trail,
TF transforms, and RViz-friendly map markers on the control laptop.
"""

from dataclasses import dataclass
import math
from pathlib import Path as FilePath
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from geometry_msgs.msg import Point, Pose, PoseStamped, TransformStamped
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, CompressedImage, Image
from tf2_ros import TransformBroadcaster
from visualization_msgs.msg import Marker, MarkerArray


@dataclass
class FrameState:
    """Processed frame data used by the SLAM backend."""

    stamp: object
    image_gray: np.ndarray
    keypoints: List[cv2.KeyPoint]
    descriptors: Optional[np.ndarray]
    pose_cw: Optional[np.ndarray] = None
    frame_index: int = 0


@dataclass
class MapPoint:
    """Sparse 3D landmark tracked by the SLAM backend."""

    point_w: np.ndarray
    descriptor: np.ndarray
    observations: int = 1
    last_seen_frame: int = 0


@dataclass
class PoseEstimate:
    """Pose estimate plus a simple confidence score."""

    pose_cw: np.ndarray
    confidence: float


class MonocularSlamNode(Node):
    """Control-side monocular SLAM node for the ROV camera stream."""

    def __init__(self) -> None:
        super().__init__('monocular_slam_node')

        # Input / frame handling.
        self.declare_parameter('input_mode', 'compressed')
        self.declare_parameter('image_topic', '/rov/camera/image_compressed')
        self.declare_parameter('camera_info_topic', '/rov/camera/camera_info')
        self.declare_parameter('camera_frame', 'camera_link')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('publish_tf', True)
        self.declare_parameter('processing_scale', 0.5)
        self.declare_parameter('use_clahe', True)
        self.declare_parameter('horizontal_fov_deg', 85.0)
        self.declare_parameter('calibration_file', '~/.ros/rov_camera_calibration.yaml')
        self.declare_parameter('use_fallback_pose_estimation', False)

        # Optional calibrated intrinsics. If all are zero, the node derives a
        # working pinhole model from the frame size and horizontal FOV.
        self.declare_parameter('fx', 0.0)
        self.declare_parameter('fy', 0.0)
        self.declare_parameter('cx', 0.0)
        self.declare_parameter('cy', 0.0)
        self.declare_parameter('dist_coeffs', [0.0, 0.0, 0.0, 0.0, 0.0])

        # ORB / tracking / mapping tuning.
        self.declare_parameter('nfeatures', 2000)
        self.declare_parameter('scale_factor', 1.2)
        self.declare_parameter('nlevels', 8)
        self.declare_parameter('edge_threshold', 31)
        self.declare_parameter('fast_threshold', 10)
        self.declare_parameter('match_ratio', 0.75)
        self.declare_parameter('min_bootstrap_matches', 120)
        self.declare_parameter('min_pnp_correspondences', 80)
        self.declare_parameter('min_pnp_inliers', 50)
        self.declare_parameter('pnp_reprojection_threshold_px', 4.0)
        self.declare_parameter('pnp_iterations', 100)
        self.declare_parameter('essential_reprojection_threshold_px', 1.5)
        self.declare_parameter('keyframe_translation_threshold_m', 0.06)
        self.declare_parameter('keyframe_rotation_threshold_deg', 6.0)
        self.declare_parameter('triangulation_reprojection_threshold_px', 3.0)
        self.declare_parameter('triangulation_min_matches', 80)
        self.declare_parameter('min_pnp_inlier_ratio', 0.28)
        self.declare_parameter('max_pnp_median_reprojection_px', 2.5)
        self.declare_parameter('min_pose_confidence', 0.25)
        self.declare_parameter('pose_smoothing_alpha', 0.25)
        self.declare_parameter('pose_hold_timeout_sec', 0.75)
        self.declare_parameter('triangulation_min_depth_m', 0.05)
        self.declare_parameter('triangulation_max_depth_m', 12.0)
        self.declare_parameter('min_triangulation_parallax_deg', 0.6)
        self.declare_parameter('max_pose_step_translation', 2.5)
        self.declare_parameter('max_pose_step_rotation_deg', 55.0)
        self.declare_parameter('max_map_radius_m', 20.0)
        self.declare_parameter('visualization_max_distance_m', 10.0)
        self.declare_parameter('min_map_point_observations', 3)
        self.declare_parameter('max_map_points', 3000)
        self.declare_parameter('visualization_point_limit', 1500)
        self.declare_parameter('path_point_limit', 5000)
        self.declare_parameter('overlay_image_topic', '/rov/slam/image')
        self.declare_parameter('overlay_rendered_image_topic', '/rov/slam/overlay_image')
        self.declare_parameter('overlay_camera_info_topic', '/rov/slam/camera_info')
        self.declare_parameter('overlay_camera_info_compat_topic', '/rov/slam/image/camera_info')

        self.input_mode = str(self.get_parameter('input_mode').value).lower()
        self.image_topic = str(self.get_parameter('image_topic').value)
        self.camera_info_topic = str(self.get_parameter('camera_info_topic').value)
        self.camera_frame = str(self.get_parameter('camera_frame').value)
        self.map_frame = str(self.get_parameter('map_frame').value)
        self.publish_tf = bool(self.get_parameter('publish_tf').value)
        self.processing_scale = float(self.get_parameter('processing_scale').value)
        self.use_clahe = bool(self.get_parameter('use_clahe').value)
        self.horizontal_fov_deg = float(self.get_parameter('horizontal_fov_deg').value)
        self.calibration_file = str(self.get_parameter('calibration_file').value)
        self.use_fallback_pose_estimation = bool(
            self.get_parameter('use_fallback_pose_estimation').value
        )

        self.fx = float(self.get_parameter('fx').value)
        self.fy = float(self.get_parameter('fy').value)
        self.cx = float(self.get_parameter('cx').value)
        self.cy = float(self.get_parameter('cy').value)
        self.dist_coeffs = np.asarray(
            list(self.get_parameter('dist_coeffs').value), dtype=np.float64
        ).reshape(-1, 1)

        self.nfeatures = int(self.get_parameter('nfeatures').value)
        self.scale_factor = float(self.get_parameter('scale_factor').value)
        self.nlevels = int(self.get_parameter('nlevels').value)
        self.edge_threshold = int(self.get_parameter('edge_threshold').value)
        self.fast_threshold = int(self.get_parameter('fast_threshold').value)
        self.match_ratio = float(self.get_parameter('match_ratio').value)
        self.min_bootstrap_matches = int(self.get_parameter('min_bootstrap_matches').value)
        self.min_pnp_correspondences = int(self.get_parameter('min_pnp_correspondences').value)
        self.min_pnp_inliers = int(self.get_parameter('min_pnp_inliers').value)
        self.pnp_reprojection_threshold_px = float(
            self.get_parameter('pnp_reprojection_threshold_px').value
        )
        self.pnp_iterations = int(self.get_parameter('pnp_iterations').value)
        self.essential_reprojection_threshold_px = float(
            self.get_parameter('essential_reprojection_threshold_px').value
        )
        self.keyframe_translation_threshold_m = float(
            self.get_parameter('keyframe_translation_threshold_m').value
        )
        self.keyframe_rotation_threshold_deg = float(
            self.get_parameter('keyframe_rotation_threshold_deg').value
        )
        self.triangulation_reprojection_threshold_px = float(
            self.get_parameter('triangulation_reprojection_threshold_px').value
        )
        self.triangulation_min_matches = int(self.get_parameter('triangulation_min_matches').value)
        self.min_pnp_inlier_ratio = float(self.get_parameter('min_pnp_inlier_ratio').value)
        self.max_pnp_median_reprojection_px = float(
            self.get_parameter('max_pnp_median_reprojection_px').value
        )
        self.min_pose_confidence = float(self.get_parameter('min_pose_confidence').value)
        self.pose_smoothing_alpha = float(self.get_parameter('pose_smoothing_alpha').value)
        self.pose_hold_timeout_sec = float(self.get_parameter('pose_hold_timeout_sec').value)
        self.triangulation_min_depth_m = float(self.get_parameter('triangulation_min_depth_m').value)
        self.triangulation_max_depth_m = float(self.get_parameter('triangulation_max_depth_m').value)
        self.min_triangulation_parallax_deg = float(
            self.get_parameter('min_triangulation_parallax_deg').value
        )
        self.max_pose_step_translation = float(self.get_parameter('max_pose_step_translation').value)
        self.max_pose_step_rotation_deg = float(self.get_parameter('max_pose_step_rotation_deg').value)
        self.max_map_radius_m = float(self.get_parameter('max_map_radius_m').value)
        self.visualization_max_distance_m = float(
            self.get_parameter('visualization_max_distance_m').value
        )
        self.min_map_point_observations = int(
            self.get_parameter('min_map_point_observations').value
        )
        self.max_map_points = int(self.get_parameter('max_map_points').value)
        self.visualization_point_limit = int(self.get_parameter('visualization_point_limit').value)
        self.path_point_limit = int(self.get_parameter('path_point_limit').value)
        self.overlay_image_topic = str(self.get_parameter('overlay_image_topic').value)
        self.overlay_rendered_image_topic = str(
            self.get_parameter('overlay_rendered_image_topic').value
        )
        self.overlay_camera_info_topic = str(
            self.get_parameter('overlay_camera_info_topic').value
        )
        self.overlay_camera_info_compat_topic = str(
            self.get_parameter('overlay_camera_info_compat_topic').value
        )

        self.image_qos = qos_profile_sensor_data
        self.camera_info_qos = QoSProfile(depth=1)
        self.camera_info_qos.reliability = QoSReliabilityPolicy.RELIABLE

        self.bridge = CvBridge()
        self.tf_broadcaster = TransformBroadcaster(self)

        self.orb = cv2.ORB_create(  # type: ignore[attr-defined]
            nfeatures=self.nfeatures,
            scaleFactor=self.scale_factor,
            nlevels=self.nlevels,
            edgeThreshold=self.edge_threshold,
            fastThreshold=self.fast_threshold,
        )
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        self._camera_matrix: Optional[np.ndarray] = None
        self._intrinsics_ready = False
        self._initialized = False
        self._frame_index = 0
        self._pending_reference: Optional[FrameState] = None
        self._last_frame: Optional[FrameState] = None
        self._last_keyframe: Optional[FrameState] = None
        self._map_points: List[MapPoint] = []
        self._current_pose_cw = np.eye(4, dtype=np.float64)
        self._smoothed_pose_wc: Optional[np.ndarray] = None
        self._last_good_pose_cw: Optional[np.ndarray] = None
        self._last_good_pose_sec: Optional[float] = None
        self._hold_pose_until_sec: Optional[float] = None
        self._last_published_pose_wc: Optional[np.ndarray] = None
        self._prev_published_pose_wc: Optional[np.ndarray] = None

        self.pose_pub = self.create_publisher(PoseStamped, '/rov/slam/pose', 10)
        self.odom_pub = self.create_publisher(Odometry, '/rov/slam/odom', 10)
        self.path_pub = self.create_publisher(Path, '/rov/slam/path', 10)
        self.marker_pub = self.create_publisher(MarkerArray, '/rov/slam/map_points', 10)
        self.overlay_image_pub = self.create_publisher(Image, self.overlay_image_topic, 10)
        self.overlay_rendered_image_pub = self.create_publisher(
            Image,
            self.overlay_rendered_image_topic,
            10,
        )
        self.overlay_camera_info_pub = self.create_publisher(
            CameraInfo,
            self.overlay_camera_info_topic,
            10,
        )
        self.overlay_camera_info_compat_pub = self.create_publisher(
            CameraInfo,
            self.overlay_camera_info_compat_topic,
            10,
        )
        self.path_msg = Path()
        self.path_msg.header.frame_id = self.map_frame

        self._try_load_calibration_file()

        if self.camera_info_topic:
            self.camera_info_sub = self.create_subscription(
                CameraInfo,
                self.camera_info_topic,
                self._camera_info_callback,
                self.camera_info_qos,
            )
        else:
            self.camera_info_sub = None

        if self.input_mode == 'compressed':
            self.image_sub = self.create_subscription(
                CompressedImage,
                self.image_topic,
                self._compressed_image_callback,
                self.image_qos,
            )
        elif self.input_mode == 'raw':
            self.image_sub = self.create_subscription(
                Image,
                self.image_topic,
                self._raw_image_callback,
                self.image_qos,
            )
        else:
            raise ValueError("input_mode must be either 'compressed' or 'raw'")

        self.get_logger().info(
            'Monocular SLAM active on {} using {} input. Pose -> {}, map -> {}'.format(
                self.image_topic,
                self.input_mode,
                '/rov/slam/pose',
                self.map_frame,
            )
        )

    def _camera_info_callback(self, msg: CameraInfo) -> None:
        """Update intrinsics from CameraInfo when available before SLAM boots."""
        if self._initialized:
            return

        if len(msg.k) != 9:
            self.get_logger().warn('CameraInfo message did not contain a valid 3x3 K matrix.')
            return

        camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        camera_matrix = self._scale_camera_matrix(camera_matrix, self.processing_scale)
        self._camera_matrix = camera_matrix
        self.dist_coeffs = np.asarray(msg.d, dtype=np.float64).reshape(-1, 1) if msg.d else np.zeros((5, 1), dtype=np.float64)
        self._intrinsics_ready = True
        self.get_logger().info('Updated SLAM intrinsics from CameraInfo.')

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
        if frame_bgr is None or frame_bgr.size == 0:
            return

        processed = frame_bgr
        if self.processing_scale > 0.0 and abs(self.processing_scale - 1.0) > 1e-6:
            processed = cv2.resize(
                processed,
                None,
                fx=self.processing_scale,
                fy=self.processing_scale,
                interpolation=cv2.INTER_AREA,
            )

        if self._camera_matrix is None:
            self._camera_matrix = self._build_initial_camera_matrix(
                processed.shape[1],
                processed.shape[0],
            )
            self._intrinsics_ready = True
            self.get_logger().info(
                'Using approximate pinhole intrinsics derived from frame size and FOV. '
                'Provide CameraInfo for best results.'
            )

        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        if self.use_clahe:
            gray = self.clahe.apply(gray)

        if self.dist_coeffs is not None and np.any(np.abs(self.dist_coeffs) > 1e-12):
            gray = cv2.undistort(gray, self._camera_matrix, self.dist_coeffs)

        keypoints, descriptors = self.orb.detectAndCompute(gray, None)
        state = FrameState(
            stamp=stamp,
            image_gray=gray,
            keypoints=keypoints or [],
            descriptors=descriptors,
            frame_index=self._frame_index,
        )
        self._frame_index += 1
        now_sec = self.get_clock().now().nanoseconds / 1e9

        # Always publish the live raw image stream so RViz stays responsive even if
        # SLAM has not initialized or pose tracking temporarily drops out.
        self._publish_raw_image(stamp, gray)

        if not self._initialized:
            # Keep RViz image displays alive before SLAM bootstrap succeeds.
            self._publish_identity_tf(stamp)
            self._publish_overlay_inputs(
                stamp,
                gray,
                None,
                state.keypoints,
                'BOOTSTRAPPING',
                (0, 180, 255),
                [f'frame {state.frame_index}', f'kpts {len(state.keypoints)}'],
            )
            self._bootstrap_or_store_reference(state)
            return

        estimate = self._estimate_pose(state)
        pose_cw = estimate.pose_cw if estimate is not None else None
        confidence = estimate.confidence if estimate is not None else 0.0
        if pose_cw is None and self.use_fallback_pose_estimation:
            pose_cw = self._fallback_pose_from_previous_frame(state)

        if pose_cw is None:
            if self._should_hold_last_pose(now_sec):
                predicted_pose_wc = self._predict_next_pose_wc()
                if predicted_pose_wc is None:
                    predicted_pose_wc = self._last_published_pose_wc

                if predicted_pose_wc is not None:
                    predicted_pose_cw = np.linalg.inv(predicted_pose_wc)
                    state.pose_cw = predicted_pose_cw
                    self._current_pose_cw = predicted_pose_cw
                    predicted_pose_wc = self._smooth_pose_for_publish(predicted_pose_wc, 0.0)
                    self._publish_state(state, predicted_pose_wc)
                    self._record_published_pose(predicted_pose_wc)
                    self._publish_overlay_inputs(
                        stamp,
                        gray,
                        predicted_pose_cw,
                        state.keypoints,
                        'PREDICTING',
                        (0, 180, 255),
                        [
                            f'frame {state.frame_index}',
                            f'kpts {len(state.keypoints)}',
                            f'map {len(self._map_points)}',
                            'constant-velocity hold',
                        ],
                    )
                    self._trim_map_points(predicted_pose_wc)
                    return

                held_pose_cw = np.array(self._last_good_pose_cw, copy=True)  # type: ignore[arg-type]
                state.pose_cw = held_pose_cw
                self._current_pose_cw = held_pose_cw
                held_pose_wc = self._smooth_pose_for_publish(np.linalg.inv(held_pose_cw), 0.0)
                self._publish_state(state, held_pose_wc)
                self._record_published_pose(held_pose_wc)
                self._publish_overlay_inputs(
                    stamp,
                    gray,
                    held_pose_cw,
                    state.keypoints,
                    'HOLDING LAST POSE',
                    (0, 200, 255),
                    [
                        f'frame {state.frame_index}',
                        f'kpts {len(state.keypoints)}',
                        f'map {len(self._map_points)}',
                    ],
                )
                self._trim_map_points(held_pose_wc)
                return

            if self._last_frame is None:
                self._last_frame = state
            self._publish_overlay_inputs(
                stamp,
                gray,
                self._current_pose_cw,
                state.keypoints,
                'TRACKING LOST',
                (0, 0, 255),
                [
                    f'frame {state.frame_index}',
                    f'kpts {len(state.keypoints)}',
                    f'map {len(self._map_points)}',
                ],
            )
            return

        state.pose_cw = pose_cw
        self._current_pose_cw = pose_cw
        self._last_good_pose_cw = np.array(pose_cw, copy=True)
        self._last_good_pose_sec = now_sec
        self._hold_pose_until_sec = now_sec + self.pose_hold_timeout_sec
        self._last_frame = state
        published_pose_wc = self._smooth_pose_for_publish(np.linalg.inv(pose_cw), confidence)
        self._publish_state(state, published_pose_wc)
        self._record_published_pose(published_pose_wc)
        self._publish_overlay_inputs(
            stamp,
            gray,
            pose_cw,
            state.keypoints,
            'TRACKING',
            (0, 255, 0),
            [
                f'frame {state.frame_index}',
                f'kpts {len(state.keypoints)}',
                f'map {len(self._map_points)}',
                f'conf {confidence:.2f}',
            ],
        )

        if self._needs_keyframe(state):
            self._create_keyframe_and_expand_map(state)

        self._trim_map_points(np.linalg.inv(pose_cw))

    def _bootstrap_or_store_reference(self, state: FrameState) -> None:
        if self._pending_reference is None:
            self._pending_reference = state
            self.get_logger().info('Stored first SLAM reference frame; waiting for a bootstrap match.')
            return

        reference = self._pending_reference
        success = self._bootstrap_map(reference, state)
        if success:
            self._initialized = True
            self._last_frame = state
            self._last_keyframe = state
            self._current_pose_cw = state.pose_cw if state.pose_cw is not None else np.eye(4)
            self.get_logger().info(
                f'SLAM bootstrap succeeded with {len(self._map_points)} initial landmarks.'
            )
            self._publish_state(state)
        else:
            self._pending_reference = state
            self.get_logger().info('Bootstrap not yet stable; using the newest frame as the reference.')

    def _bootstrap_map(self, reference: FrameState, current: FrameState) -> bool:
        if reference.descriptors is None or current.descriptors is None:
            return False

        matches = self._ratio_matches(reference.descriptors, current.descriptors)
        if len(matches) < self.min_bootstrap_matches:
            return False

        ref_pts = np.float32([reference.keypoints[m.queryIdx].pt for m in matches])
        cur_pts = np.float32([current.keypoints[m.trainIdx].pt for m in matches])

        essential, mask = cv2.findEssentialMat(
            ref_pts,
            cur_pts,
            self._camera_matrix,
            method=cv2.RANSAC,
            prob=0.999,
            threshold=self.essential_reprojection_threshold_px,
        )
        if essential is None or mask is None:
            return False

        mask = mask.ravel().astype(bool)
        if int(np.count_nonzero(mask)) < self.min_bootstrap_matches:
            return False

        ref_inliers = ref_pts[mask]
        cur_inliers = cur_pts[mask]

        recover_count, rotation, translation, recover_mask = cv2.recoverPose(
            essential,
            ref_inliers,
            cur_inliers,
            self._camera_matrix,
        )
        if recover_count < self.min_bootstrap_matches or recover_mask is None:
            return False

        recover_mask = recover_mask.ravel().astype(bool)
        ref_inliers = ref_inliers[recover_mask]
        cur_inliers = cur_inliers[recover_mask]
        match_subset = [matches[index] for index, keep in enumerate(mask) if keep]
        match_subset = [match_subset[index] for index, keep in enumerate(recover_mask) if keep]
        if len(ref_inliers) < self.min_bootstrap_matches:
            return False

        reference.pose_cw = np.eye(4, dtype=np.float64)
        current.pose_cw = self._compose_pose(rotation, translation)

        self._map_points.extend(
            self._triangulate_landmarks(reference, current, match_subset, ref_inliers, cur_inliers)
        )
        self._last_keyframe = current
        self._trim_map_points(np.linalg.inv(self._current_pose_cw))
        return True

    def _estimate_pose(self, state: FrameState) -> Optional[PoseEstimate]:
        if state.descriptors is None or not self._map_points:
            return None

        map_descriptors = np.asarray([point.descriptor for point in self._map_points], dtype=np.uint8)
        matches = self._ratio_matches(state.descriptors, map_descriptors)
        if len(matches) < self.min_pnp_correspondences:
            return None

        object_points = np.float32([self._map_points[m.trainIdx].point_w for m in matches])
        image_points = np.float32([state.keypoints[m.queryIdx].pt for m in matches])

        success, rvec, tvec, inliers = cv2.solvePnPRansac(
            object_points,
            image_points,
            self._camera_matrix,
            self.dist_coeffs,
            iterationsCount=self.pnp_iterations,
            reprojectionError=self.pnp_reprojection_threshold_px,
            confidence=0.999,
            flags=cv2.SOLVEPNP_EPNP,
        )
        if not success or inliers is None or len(inliers) < self.min_pnp_inliers:
            return None

        inlier_indices = inliers.ravel().tolist()
        inlier_object_points = object_points[inlier_indices]
        inlier_image_points = image_points[inlier_indices]

        if hasattr(cv2, 'solvePnPRefineLM'):
            try:
                rvec, tvec = cv2.solvePnPRefineLM(
                    inlier_object_points,
                    inlier_image_points,
                    self._camera_matrix,
                    self.dist_coeffs,
                    rvec,
                    tvec,
                )
            except Exception:
                pass

        projected, _ = cv2.projectPoints(
            inlier_object_points,
            rvec,
            tvec,
            self._camera_matrix,
            self.dist_coeffs,
        )
        projected = projected.reshape(-1, 2)
        reprojection_error = np.linalg.norm(projected - inlier_image_points, axis=1)
        median_reprojection_error = float(np.median(reprojection_error))
        if median_reprojection_error > self.max_pnp_median_reprojection_px:
            return None

        rotation, _ = cv2.Rodrigues(rvec)
        pose_cw = self._compose_pose(rotation, tvec)
        if self._last_frame is not None and self._last_frame.pose_cw is not None:
            if not self._is_pose_step_reasonable(pose_cw, self._last_frame.pose_cw):
                return None

        inlier_ratio = float(len(inlier_indices)) / float(max(1, len(matches)))
        if inlier_ratio < self.min_pnp_inlier_ratio:
            return None

        confidence = min(1.0, inlier_ratio / max(self.min_pnp_inlier_ratio, 1e-6))
        confidence *= max(
            0.0,
            1.0 - (median_reprojection_error / max(self.max_pnp_median_reprojection_px, 1e-6)),
        )
        confidence = float(max(0.0, min(1.0, confidence)))
        if confidence < self.min_pose_confidence:
            return None

        for index in inlier_indices:
            map_point = self._map_points[matches[index].trainIdx]
            map_point.observations += 1
            map_point.last_seen_frame = state.frame_index

        return PoseEstimate(pose_cw=pose_cw, confidence=confidence)

    def _fallback_pose_from_previous_frame(self, state: FrameState) -> Optional[np.ndarray]:
        if self._last_frame is None:
            return None
        if self._last_frame.descriptors is None or state.descriptors is None:
            return None

        matches = self._ratio_matches(self._last_frame.descriptors, state.descriptors)
        if len(matches) < self.min_bootstrap_matches:
            return None

        prev_pts = np.float32([self._last_frame.keypoints[m.queryIdx].pt for m in matches])
        cur_pts = np.float32([state.keypoints[m.trainIdx].pt for m in matches])

        essential, mask = cv2.findEssentialMat(
            prev_pts,
            cur_pts,
            self._camera_matrix,
            method=cv2.RANSAC,
            prob=0.999,
            threshold=self.essential_reprojection_threshold_px,
        )
        if essential is None or mask is None:
            return None

        mask = mask.ravel().astype(bool)
        prev_pts = prev_pts[mask]
        cur_pts = cur_pts[mask]
        if len(prev_pts) < self.min_bootstrap_matches:
            return None

        recover_count, rotation, translation, recover_mask = cv2.recoverPose(
            essential,
            prev_pts,
            cur_pts,
            self._camera_matrix,
        )
        if recover_count < self.min_bootstrap_matches or recover_mask is None:
            return None

        delta_pose = self._compose_pose(rotation, translation)
        if self._last_frame.pose_cw is not None:
            candidate_pose = delta_pose @ self._last_frame.pose_cw
            if not self._is_pose_step_reasonable(candidate_pose, self._last_frame.pose_cw):
                return None
            return candidate_pose
        return delta_pose

    def _needs_keyframe(self, state: FrameState) -> bool:
        if self._last_keyframe is None or state.pose_cw is None:
            return False

        delta = np.linalg.inv(self._last_keyframe.pose_cw) @ state.pose_cw
        translation = float(np.linalg.norm(delta[:3, 3]))
        rotation = self._rotation_angle_deg(delta[:3, :3])
        return (
            translation >= self.keyframe_translation_threshold_m
            or rotation >= self.keyframe_rotation_threshold_deg
        )

    def _create_keyframe_and_expand_map(self, state: FrameState) -> None:
        if self._last_keyframe is None or self._last_keyframe.descriptors is None:
            self._last_keyframe = state
            return
        if state.descriptors is None or state.pose_cw is None or self._last_keyframe.pose_cw is None:
            self._last_keyframe = state
            return

        matches = self._ratio_matches(self._last_keyframe.descriptors, state.descriptors)
        if len(matches) >= self.triangulation_min_matches:
            ref_pts = np.float32([self._last_keyframe.keypoints[m.queryIdx].pt for m in matches])
            cur_pts = np.float32([state.keypoints[m.trainIdx].pt for m in matches])
            new_points = self._triangulate_landmarks(
                self._last_keyframe,
                state,
                matches,
                ref_pts,
                cur_pts,
            )
            self._map_points.extend(new_points)

        self._last_keyframe = state

    def _triangulate_landmarks(
        self,
        reference: FrameState,
        current: FrameState,
        matches: Sequence[cv2.DMatch],
        ref_pts: np.ndarray,
        cur_pts: np.ndarray,
    ) -> List[MapPoint]:
        if reference.pose_cw is None or current.pose_cw is None:
            return []
        if len(matches) == 0:
            return []

        reference_pose = np.asarray(reference.pose_cw, dtype=np.float64)
        current_pose = np.asarray(current.pose_cw, dtype=np.float64)

        P_ref = self._camera_matrix @ reference_pose[:3, :]
        P_cur = self._camera_matrix @ current_pose[:3, :]

        pts4d = cv2.triangulatePoints(P_ref, P_cur, ref_pts.T, cur_pts.T)
        denom = np.where(np.abs(pts4d[3:4, :]) < 1e-9, 1e-9, pts4d[3:4, :])
        pts4d /= denom
        points_w = pts4d[:3, :].T

        ref_cam = (reference_pose[:3, :3] @ points_w.T + reference_pose[:3, 3:4]).T
        cur_cam = (current_pose[:3, :3] @ points_w.T + current_pose[:3, 3:4]).T

        valid = np.isfinite(points_w).all(axis=1)
        valid &= ref_cam[:, 2] > self.triangulation_min_depth_m
        valid &= cur_cam[:, 2] > self.triangulation_min_depth_m
        valid &= ref_cam[:, 2] < self.triangulation_max_depth_m
        valid &= cur_cam[:, 2] < self.triangulation_max_depth_m

        parallax_deg = self._triangulation_parallax_deg(reference_pose, current_pose, points_w)
        valid &= parallax_deg >= self.min_triangulation_parallax_deg

        world_norm = np.linalg.norm(points_w, axis=1)
        valid &= world_norm < self.max_map_radius_m

        ref_proj = self._project_points(reference.pose_cw, points_w)
        cur_proj = self._project_points(current.pose_cw, points_w)
        ref_error = np.linalg.norm(ref_proj - ref_pts, axis=1)
        cur_error = np.linalg.norm(cur_proj - cur_pts, axis=1)
        valid &= ref_error < self.triangulation_reprojection_threshold_px
        valid &= cur_error < self.triangulation_reprojection_threshold_px

        landmarks: List[MapPoint] = []
        for index, is_valid in enumerate(valid):
            if not is_valid:
                continue
            descriptor = current.descriptors[matches[index].trainIdx]
            landmarks.append(
                MapPoint(
                    point_w=points_w[index].astype(np.float64),
                    descriptor=np.array(descriptor, copy=True),
                    observations=1,
                    last_seen_frame=current.frame_index,
                )
            )

        return landmarks

    def _ratio_matches(
        self,
        query_descriptors: Optional[np.ndarray],
        train_descriptors: Optional[np.ndarray],
    ) -> List[cv2.DMatch]:
        if query_descriptors is None or train_descriptors is None:
            return []
        if len(query_descriptors) == 0 or len(train_descriptors) == 0:
            return []

        raw_matches = self.matcher.knnMatch(query_descriptors, train_descriptors, k=2)
        good_matches: List[cv2.DMatch] = []
        for pair in raw_matches:
            if len(pair) < 2:
                continue
            best, second = pair
            if best.distance < self.match_ratio * second.distance:
                good_matches.append(best)
        good_matches.sort(key=lambda match: match.distance)
        return good_matches

    def _publish_state(self, state: FrameState, pose_wc: Optional[np.ndarray] = None) -> None:
        if state.pose_cw is None:
            return

        if pose_wc is None:
            pose_wc = np.linalg.inv(state.pose_cw)
        pose_msg = PoseStamped()
        pose_msg.header.stamp = state.stamp
        pose_msg.header.frame_id = self.map_frame
        pose_msg.pose = self._matrix_to_pose(pose_wc)

        odom_msg = Odometry()
        odom_msg.header.stamp = state.stamp
        odom_msg.header.frame_id = self.map_frame
        odom_msg.child_frame_id = self.camera_frame
        odom_msg.pose.pose = pose_msg.pose

        self.path_msg.header.stamp = state.stamp
        self.path_msg.header.frame_id = self.map_frame
        self.path_msg.poses.append(pose_msg)
        if len(self.path_msg.poses) > self.path_point_limit:
            self.path_msg.poses = self.path_msg.poses[-self.path_point_limit :]

        self.pose_pub.publish(pose_msg)
        self.odom_pub.publish(odom_msg)
        self.path_pub.publish(self.path_msg)

        self._publish_tf(state.stamp, pose_wc)
        self._publish_markers(state, pose_wc)

    def _smooth_pose_for_publish(self, pose_wc: np.ndarray, confidence: float) -> np.ndarray:
        if self._smoothed_pose_wc is None:
            self._smoothed_pose_wc = np.array(pose_wc, dtype=np.float64, copy=True)
            return self._smoothed_pose_wc

        alpha = self.pose_smoothing_alpha * max(0.25, confidence)
        alpha = float(max(0.0, min(1.0, alpha)))
        previous_pose = self._smoothed_pose_wc

        previous_translation = previous_pose[:3, 3]
        current_translation = pose_wc[:3, 3]
        blended_translation = (1.0 - alpha) * previous_translation + alpha * current_translation

        previous_quat = self._rotation_matrix_to_quaternion(previous_pose[:3, :3])
        current_quat = self._rotation_matrix_to_quaternion(pose_wc[:3, :3])
        blended_quat = self._quaternion_slerp(previous_quat, current_quat, alpha)

        smoothed_pose = np.eye(4, dtype=np.float64)
        smoothed_pose[:3, :3] = self._quaternion_to_rotation_matrix(blended_quat)
        smoothed_pose[:3, 3] = blended_translation
        self._smoothed_pose_wc = smoothed_pose
        return smoothed_pose

    def _publish_raw_image(self, stamp: object, gray: np.ndarray) -> None:
        image_msg = self.bridge.cv2_to_imgmsg(gray, encoding='mono8')
        image_msg.header.stamp = stamp
        image_msg.header.frame_id = self.camera_frame
        self.overlay_image_pub.publish(image_msg)

    def _publish_overlay_inputs(
        self,
        stamp: object,
        gray: np.ndarray,
        pose_cw: Optional[np.ndarray],
        keypoints: Optional[List[cv2.KeyPoint]] = None,
        status_text: str = '',
        status_color: Tuple[int, int, int] = (0, 255, 0),
        status_lines: Optional[List[str]] = None,
    ) -> None:
        image_msg = self.bridge.cv2_to_imgmsg(gray, encoding='mono8')
        image_msg.header.stamp = stamp
        image_msg.header.frame_id = self.camera_frame
        self.overlay_image_pub.publish(image_msg)

        overlay_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        if keypoints:
            self._draw_keypoints(overlay_bgr, keypoints)
        if pose_cw is not None and self._camera_matrix is not None and self._map_points:
            self._draw_overlay_points(overlay_bgr, pose_cw)
        self._draw_status_box(overlay_bgr, status_text, status_color, status_lines or [])

        overlay_msg = self.bridge.cv2_to_imgmsg(overlay_bgr, encoding='bgr8')
        overlay_msg.header.stamp = stamp
        overlay_msg.header.frame_id = self.camera_frame
        self.overlay_rendered_image_pub.publish(overlay_msg)

        if self._camera_matrix is None:
            return

        camera_info = CameraInfo()
        camera_info.header.stamp = stamp
        camera_info.header.frame_id = self.camera_frame
        camera_info.height = int(gray.shape[0])
        camera_info.width = int(gray.shape[1])
        camera_info.distortion_model = 'plumb_bob'
        camera_info.k = self._camera_matrix.reshape(-1).tolist()
        camera_info.d = self.dist_coeffs.reshape(-1).tolist()
        camera_info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        projection = np.zeros((3, 4), dtype=np.float64)
        projection[:3, :3] = self._camera_matrix
        camera_info.p = projection.reshape(-1).tolist()
        self.overlay_camera_info_pub.publish(camera_info)
        self.overlay_camera_info_compat_pub.publish(camera_info)

    def _draw_status_box(
        self,
        image_bgr: np.ndarray,
        status_text: str,
        status_color: Tuple[int, int, int],
        status_lines: List[str],
    ) -> None:
        lines = [status_text] if status_text else []
        lines.extend(status_lines)
        if not lines:
            return

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.48
        thickness = 1
        padding = 8
        line_gap = 5

        sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
        max_w = max((size[0] for size in sizes), default=0)
        max_h = max((size[1] for size in sizes), default=14)
        box_w = max_w + padding * 2
        box_h = padding * 2 + len(lines) * max_h + max(0, len(lines) - 1) * line_gap

        x0, y0 = 8, 8
        x1, y1 = x0 + box_w, y0 + box_h
        overlay = image_bgr.copy()
        cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, image_bgr, 0.4, 0, image_bgr)
        cv2.rectangle(image_bgr, (x0, y0), (x1, y1), status_color, 1)

        y = y0 + padding + max_h
        for index, line in enumerate(lines):
            color = status_color if index == 0 else (235, 235, 235)
            cv2.putText(image_bgr, line, (x0 + padding, y), font, font_scale, color, thickness, cv2.LINE_AA)
            y += max_h + line_gap

    def _record_published_pose(self, pose_wc: np.ndarray) -> None:
        self._prev_published_pose_wc = (
            None if self._last_published_pose_wc is None else np.array(self._last_published_pose_wc, copy=True)
        )
        self._last_published_pose_wc = np.array(pose_wc, copy=True)

    def _predict_next_pose_wc(self) -> Optional[np.ndarray]:
        if self._last_published_pose_wc is None:
            return None
        if self._prev_published_pose_wc is None:
            return np.array(self._last_published_pose_wc, copy=True)

        last = self._last_published_pose_wc
        prev = self._prev_published_pose_wc
        try:
            delta = last @ np.linalg.inv(prev)
            predicted = delta @ last
            if not np.isfinite(predicted).all():
                return np.array(last, copy=True)
            return predicted
        except np.linalg.LinAlgError:
            return np.array(last, copy=True)

    def _draw_keypoints(self, image_bgr: np.ndarray, keypoints: List[cv2.KeyPoint]) -> None:
        if not keypoints:
            return

        sorted_keypoints = sorted(
            keypoints,
            key=lambda kp: (-float(getattr(kp, 'response', 0.0)), float(kp.pt[1]), float(kp.pt[0])),
        )
        step = max(1, len(sorted_keypoints) // 120)
        height, width = image_bgr.shape[:2]
        for keypoint in sorted_keypoints[::step]:
            u, v = keypoint.pt
            if not np.isfinite(u) or not np.isfinite(v):
                continue
            if u < 0 or v < 0 or u >= width or v >= height:
                continue
            cv2.circle(image_bgr, (int(u), int(v)), 2, (0, 255, 0), -1)

    def _draw_overlay_points(self, image_bgr: np.ndarray, pose_cw: np.ndarray) -> None:
        camera_position = np.linalg.inv(pose_cw)[:3, 3]
        usable_points = sorted(
            [
                point
                for point in self._map_points
                if point.observations >= self.min_map_point_observations
                and np.linalg.norm(point.point_w - camera_position) <= self.max_map_radius_m
            ],
            key=lambda point: (-point.observations, -point.last_seen_frame),
        )
        if not usable_points:
            return

        if len(usable_points) > self.visualization_point_limit:
            step = max(1, len(usable_points) // self.visualization_point_limit)
            usable_points = usable_points[::step][: self.visualization_point_limit]

        points_w = np.array([point.point_w for point in usable_points], dtype=np.float64)
        rvec, _ = cv2.Rodrigues(pose_cw[:3, :3])
        tvec = pose_cw[:3, 3].reshape(3, 1)
        projected, _ = cv2.projectPoints(
            points_w,
            rvec,
            tvec,
            self._camera_matrix,
            self.dist_coeffs,
        )
        projected = projected.reshape(-1, 2)

        height, width = image_bgr.shape[:2]
        for u, v in projected:
            if not np.isfinite(u) or not np.isfinite(v):
                continue
            if u < 0 or v < 0 or u >= width or v >= height:
                continue
            cv2.circle(image_bgr, (int(u), int(v)), 2, (0, 255, 255), -1)

    def _try_load_calibration_file(self) -> None:
        calibration_path = FilePath(self.calibration_file).expanduser()
        if not calibration_path.exists():
            self.get_logger().warn(
                f'Calibration file not found at {calibration_path}; using CameraInfo topic or approximate intrinsics.'
            )
            return

        storage = cv2.FileStorage(str(calibration_path), cv2.FILE_STORAGE_READ)
        if not storage.isOpened():
            self.get_logger().warn(f'Unable to open calibration file: {calibration_path}')
            return

        try:
            camera_matrix = storage.getNode('camera_matrix').mat()
            if camera_matrix is None or camera_matrix.shape != (3, 3):
                self.get_logger().warn(
                    f'Calibration file {calibration_path} does not contain a valid 3x3 camera_matrix.'
                )
                return

            dist_node = storage.getNode('distortion_coefficients').mat()
            if dist_node is None:
                dist_node = storage.getNode('distortion_coeffs').mat()
            if dist_node is None:
                dist_node = np.zeros((5, 1), dtype=np.float64)

            self._camera_matrix = np.array(camera_matrix, dtype=np.float64)
            self.dist_coeffs = np.array(dist_node, dtype=np.float64).reshape(-1, 1)
            self._intrinsics_ready = True
            self.get_logger().info(f'Loaded camera calibration from {calibration_path}')
        finally:
            storage.release()

    def _publish_identity_tf(self, stamp: object) -> None:
        if not self.publish_tf:
            return

        tf_msg = TransformStamped()
        tf_msg.header.stamp = stamp
        tf_msg.header.frame_id = self.map_frame
        tf_msg.child_frame_id = self.camera_frame
        tf_msg.transform.translation.x = 0.0
        tf_msg.transform.translation.y = 0.0
        tf_msg.transform.translation.z = 0.0
        tf_msg.transform.rotation.x = 0.0
        tf_msg.transform.rotation.y = 0.0
        tf_msg.transform.rotation.z = 0.0
        tf_msg.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(tf_msg)

    def _publish_tf(self, stamp: object, pose_wc: np.ndarray) -> None:
        if not self.publish_tf:
            return

        tf_msg = TransformStamped()
        tf_msg.header.stamp = stamp
        tf_msg.header.frame_id = self.map_frame
        tf_msg.child_frame_id = self.camera_frame
        tf_msg.transform.translation.x = float(pose_wc[0, 3])
        tf_msg.transform.translation.y = float(pose_wc[1, 3])
        tf_msg.transform.translation.z = float(pose_wc[2, 3])

        quat = self._rotation_matrix_to_quaternion(pose_wc[:3, :3])
        tf_msg.transform.rotation.x = quat[0]
        tf_msg.transform.rotation.y = quat[1]
        tf_msg.transform.rotation.z = quat[2]
        tf_msg.transform.rotation.w = quat[3]
        self.tf_broadcaster.sendTransform(tf_msg)

    def _publish_markers(self, state: FrameState, pose_wc: np.ndarray) -> None:
        marker_array = MarkerArray()

        map_marker = Marker()
        map_marker.header.stamp = state.stamp
        map_marker.header.frame_id = self.map_frame
        map_marker.ns = 'slam_map_points'
        map_marker.id = 0
        map_marker.type = Marker.SPHERE_LIST
        map_marker.action = Marker.ADD
        map_marker.pose.orientation.w = 1.0
        map_marker.scale.x = 0.03
        map_marker.scale.y = 0.03
        map_marker.scale.z = 0.03
        map_marker.color.r = 0.15
        map_marker.color.g = 0.95
        map_marker.color.b = 1.0
        map_marker.color.a = 0.9

        if self._map_points:
            sampled_points = self._map_points
            camera_position = pose_wc[:3, 3]
            sampled_points = [
                point for point in sampled_points
                if point.observations >= self.min_map_point_observations
                and np.linalg.norm(point.point_w - camera_position) <= self.visualization_max_distance_m
            ]
            if len(sampled_points) > self.visualization_point_limit:
                step = max(1, len(sampled_points) // self.visualization_point_limit)
                sampled_points = sampled_points[::step][: self.visualization_point_limit]
            map_marker.points = [
                Point(x=float(point.point_w[0]), y=float(point.point_w[1]), z=float(point.point_w[2]))
                for point in sampled_points
            ]
        else:
            map_marker.action = Marker.DELETE

        # Make the map visually obvious in RViz by using one clear color and a second
        # marker that shows the current camera center in the same frame.
        map_marker.color.r = 0.0
        map_marker.color.g = 0.9
        map_marker.color.b = 0.9
        map_marker.color.a = 1.0

        current_marker = Marker()
        current_marker.header.stamp = state.stamp
        current_marker.header.frame_id = self.map_frame
        current_marker.ns = 'slam_current_pose'
        current_marker.id = 1
        current_marker.type = Marker.ARROW
        current_marker.action = Marker.ADD
        current_marker.pose = self._matrix_to_pose(pose_wc)
        current_marker.scale.x = 0.20
        current_marker.scale.y = 0.04
        current_marker.scale.z = 0.04
        current_marker.color.r = 1.0
        current_marker.color.g = 0.35
        current_marker.color.b = 0.15
        current_marker.color.a = 1.0

        marker_array.markers = [map_marker, current_marker]
        self.marker_pub.publish(marker_array)

    def _should_hold_last_pose(self, now_sec: float) -> bool:
        if self._last_good_pose_cw is None or self._hold_pose_until_sec is None:
            return False
        return now_sec <= self._hold_pose_until_sec

    def _build_initial_camera_matrix(self, width: int, height: int) -> np.ndarray:
        fx = self.fx if self.fx > 0.0 else width / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) / 2.0))
        fy = self.fy if self.fy > 0.0 else fx
        cx = self.cx if self.cx > 0.0 else width * 0.5
        cy = self.cy if self.cy > 0.0 else height * 0.5
        return np.array(
            [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    def _scale_camera_matrix(self, camera_matrix: np.ndarray, scale: float) -> np.ndarray:
        scaled = np.array(camera_matrix, dtype=np.float64, copy=True)
        scaled[0, 0] *= scale
        scaled[0, 2] *= scale
        scaled[1, 1] *= scale
        scaled[1, 2] *= scale
        return scaled

    def _compose_pose(self, rotation: np.ndarray, translation: np.ndarray) -> np.ndarray:
        pose = np.eye(4, dtype=np.float64)
        pose[:3, :3] = rotation
        pose[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3)
        return pose

    def _project_points(self, pose_cw: np.ndarray, points_w: np.ndarray) -> np.ndarray:
        points_c = (pose_cw[:3, :3] @ points_w.T + pose_cw[:3, 3:4]).T
        pixels = (self._camera_matrix @ points_c.T).T
        return pixels[:, :2] / np.maximum(pixels[:, 2:3], 1e-9)

    def _matrix_to_pose(self, pose_wc: np.ndarray) -> Pose:
        pose = Pose()
        pose.position.x = float(pose_wc[0, 3])
        pose.position.y = float(pose_wc[1, 3])
        pose.position.z = float(pose_wc[2, 3])
        quat = self._rotation_matrix_to_quaternion(pose_wc[:3, :3])
        pose.orientation.x = quat[0]
        pose.orientation.y = quat[1]
        pose.orientation.z = quat[2]
        pose.orientation.w = quat[3]
        return pose

    def _rotation_matrix_to_quaternion(self, rotation: np.ndarray) -> Tuple[float, float, float, float]:
        trace = float(np.trace(rotation))
        if trace > 0.0:
            s = math.sqrt(trace + 1.0) * 2.0
            qw = 0.25 * s
            qx = (rotation[2, 1] - rotation[1, 2]) / s
            qy = (rotation[0, 2] - rotation[2, 0]) / s
            qz = (rotation[1, 0] - rotation[0, 1]) / s
        elif rotation[0, 0] > rotation[1, 1] and rotation[0, 0] > rotation[2, 2]:
            s = math.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2.0
            qw = (rotation[2, 1] - rotation[1, 2]) / s
            qx = 0.25 * s
            qy = (rotation[0, 1] + rotation[1, 0]) / s
            qz = (rotation[0, 2] + rotation[2, 0]) / s
        elif rotation[1, 1] > rotation[2, 2]:
            s = math.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2.0
            qw = (rotation[0, 2] - rotation[2, 0]) / s
            qx = (rotation[0, 1] + rotation[1, 0]) / s
            qy = 0.25 * s
            qz = (rotation[1, 2] + rotation[2, 1]) / s
        else:
            s = math.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2.0
            qw = (rotation[1, 0] - rotation[0, 1]) / s
            qx = (rotation[0, 2] + rotation[2, 0]) / s
            qy = (rotation[1, 2] + rotation[2, 1]) / s
            qz = 0.25 * s
        return float(qx), float(qy), float(qz), float(qw)

    def _quaternion_to_rotation_matrix(self, quat: Tuple[float, float, float, float]) -> np.ndarray:
        x, y, z, w = quat
        xx = x * x
        yy = y * y
        zz = z * z
        xy = x * y
        xz = x * z
        yz = y * z
        wx = w * x
        wy = w * y
        wz = w * z
        return np.array(
            [
                [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)],
                [2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
                [2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)],
            ],
            dtype=np.float64,
        )

    def _quaternion_slerp(
        self,
        q0: Tuple[float, float, float, float],
        q1: Tuple[float, float, float, float],
        t: float,
    ) -> Tuple[float, float, float, float]:
        q0_arr = np.array(q0, dtype=np.float64)
        q1_arr = np.array(q1, dtype=np.float64)
        dot = float(np.dot(q0_arr, q1_arr))
        if dot < 0.0:
            q1_arr = -q1_arr
            dot = -dot
        dot = max(-1.0, min(1.0, dot))

        if dot > 0.9995:
            result = q0_arr + t * (q1_arr - q0_arr)
            result /= np.linalg.norm(result)
            return float(result[0]), float(result[1]), float(result[2]), float(result[3])

        theta_0 = math.acos(dot)
        sin_theta_0 = math.sin(theta_0)
        theta = theta_0 * t
        sin_theta = math.sin(theta)

        s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s1 = sin_theta / sin_theta_0
        result = (s0 * q0_arr) + (s1 * q1_arr)
        result /= np.linalg.norm(result)
        return float(result[0]), float(result[1]), float(result[2]), float(result[3])

    def _rotation_angle_deg(self, rotation: np.ndarray) -> float:
        cosine = (float(np.trace(rotation)) - 1.0) * 0.5
        cosine = max(-1.0, min(1.0, cosine))
        return math.degrees(math.acos(cosine))

    def _is_pose_step_reasonable(self, pose_cw: np.ndarray, previous_pose_cw: np.ndarray) -> bool:
        delta = np.linalg.inv(previous_pose_cw) @ pose_cw
        translation = float(np.linalg.norm(delta[:3, 3]))
        rotation_deg = self._rotation_angle_deg(delta[:3, :3])
        return (
            translation <= self.max_pose_step_translation
            and rotation_deg <= self.max_pose_step_rotation_deg
        )

    def _triangulation_parallax_deg(
        self,
        reference_pose_cw: np.ndarray,
        current_pose_cw: np.ndarray,
        points_w: np.ndarray,
    ) -> np.ndarray:
        reference_pose_wc = np.linalg.inv(reference_pose_cw)
        current_pose_wc = np.linalg.inv(current_pose_cw)
        reference_center = reference_pose_wc[:3, 3]
        current_center = current_pose_wc[:3, 3]

        vec_ref = points_w - reference_center
        vec_cur = points_w - current_center
        norm_ref = np.linalg.norm(vec_ref, axis=1)
        norm_cur = np.linalg.norm(vec_cur, axis=1)
        denom = np.maximum(norm_ref * norm_cur, 1e-9)
        cosine = np.sum(vec_ref * vec_cur, axis=1) / denom
        cosine = np.clip(cosine, -1.0, 1.0)
        return np.degrees(np.arccos(cosine))

    def _trim_map_points(self, pose_wc: Optional[np.ndarray] = None) -> None:
        if pose_wc is None and self._current_pose_cw is not None:
            pose_wc = np.linalg.inv(self._current_pose_cw)

        if self.max_map_radius_m > 0.0 and self._map_points and pose_wc is not None:
            camera_position = pose_wc[:3, 3]
            self._map_points = [
                point for point in self._map_points
                if np.linalg.norm(point.point_w - camera_position) <= self.max_map_radius_m
            ]

        if len(self._map_points) <= self.max_map_points:
            return

        self._map_points.sort(
            key=lambda point: (point.observations, point.last_seen_frame),
            reverse=True,
        )
        self._map_points = self._map_points[: self.max_map_points]

    def destroy_node(self) -> bool:
        """Ensure no OpenCV windows remain open."""
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None) -> None:
    """ROS 2 entry point."""
    rclpy.init(args=args)
    node = MonocularSlamNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()





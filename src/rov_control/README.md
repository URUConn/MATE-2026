# rov_control

Control-station ROS2 nodes for arm bridging, QGC video relay, and live photogrammetry.

## Photogrammetry node

`photogrammetry_node` subscribes to `/rov/camera/image_compressed`, estimates camera pose from ArUco markers, tracks ORB keyframes, and publishes:

- `geometry_msgs/PoseStamped` on `/rov/photogrammetry/camera_pose`
- `std_msgs/String` status on `/rov/photogrammetry/status`
- optional debug image on `/rov/photogrammetry/debug_image_compressed`

### Key parameters (`config/control_params.yaml`)

- `marker_dictionary`, `marker_length_m`
- `max_processing_fps`, `downscale`
- `keyframe_min_interval_sec`, `keyframe_pixel_shift`, `min_feature_matches`
- `camera_hfov_deg` or explicit `camera_matrix` + `dist_coeffs`

### Quick run

```bash
ros2 launch rov_control photogrammetry_only_launch.py
```

Or run all control-side nodes:

```bash
ros2 launch rov_control control_launch.py enable_photogrammetry:=true
```

### Smoke test

```bash
python3 -m pytest src/rov_control/test/test_photogrammetry_node.py
```


# MATE 2026 ROV
### UConn Underwater Robotics Club

MATEROV is an underwater robotics competition. This repository contains the ROS workspace for our 2026 entry, which includes:
- **ROS 2 handles:**
  - arm encoder values from the control laptop -> onboard servo commands
  - camera transport used by a QGC video bridge and control-side SLAM
- **QGroundControl + autopilot stack** handles vehicle driving/thrusters.

---

## Architecture

```
Control Laptop (Ubuntu + QGroundControl + ROS 2)          Onboard Computer (Ubuntu + ROS 2 + autopilot HW)

[QGroundControl] --MAVLink--> [Autopilot/ESCs]            (drive control path, not ROS)
      ^
      | UDP video :5600 from ROS bridge
[rov_control/qgc_video_bridge_node] <-- ROS compressed image -- [rov_onboard/camera_node]

      | ROS camera stream (default: compressed)
[rov_slam/monocular_slam_node] <-- ROS image stream ----------- [rov_onboard/camera_node]
      |
      '--/rov/slam/pose, /rov/slam/path, /rov/slam/map_points --> [RViz on control laptop]

[arm controller encoder USB] --/rov/arm/encoder_values--> [rov_control/arm_encoder_bridge_node]
                                                           |
                                                           '--/rov/arm/servo_command--> [rov_onboard/arm_servo_node -> PinPong servos]
```

---

## ROS File Structure
Split into 2 main packages for the two hardware stacks, plus a shared messages package:

- `rov_msgs`
  - `ArmServoCommand.msg`
- `rov_control` (runs on control laptop)
  - `arm_encoder_bridge_node`
  - `qgc_video_bridge_node`
- `rov_slam` (runs on control laptop)
  - `monocular_slam_node`
- `rov_onboard` (runs on onboard computer)
  - `camera_node`
  - `arm_servo_node`

---

## ROS Topics (Current)

| Topic | Type | Direction | Purpose                                      |
|---|---|---|----------------------------------------------|
| `/rov/arm/encoder_values` | `std_msgs/Float32MultiArray` | Laptop local input | 8 encoder values from USB reader script/node |
| `/rov/arm/servo_command` | `rov_msgs/ArmServoCommand` | Laptop -> Onboard | 8 servo target angles in degrees             |
| `/rov/camera/image_raw` | `sensor_msgs/Image` | Onboard -> Laptop | raw camera stream                            |
| `/rov/camera/image_compressed` | `sensor_msgs/CompressedImage` | Onboard -> Laptop | compressed camera stream                     |
| `/rov/slam/pose` | `geometry_msgs/PoseStamped` | Laptop local output | current SLAM pose in `map` frame             |
| `/rov/slam/odom` | `nav_msgs/Odometry` | Laptop local output | odometry-style pose for RViz/consumers       |
| `/rov/slam/path` | `nav_msgs/Path` | Laptop local output | accumulated camera trajectory                |
| `/rov/slam/map_points` | `visualization_msgs/MarkerArray` | Laptop local output | sparse map points + current pose marker      |

`ArmServoCommand` axis order defaults to:
`[base, shoulder, elbow, wrist_pitch, wrist_roll, wrist_yaw, tool_rotate, gripper]`

---

## 1) Install Dependencies

Run all commands on both machines unless noted.

- Assumes ROS 2 Humble and Ubuntu 22.04.
- Also assumes you have QGroundControl installed on the control laptop.

```bash
source /opt/ros/humble/setup.bash
sudo apt update
sudo apt install -y \
  python3-opencv \
  ros-humble-cv-bridge \
  ros-humble-rviz2 \
  python3-pip \
  ffmpeg \
  mavlink-router
```

On the **onboard** machine (for servos):

```bash
pip3 install pinpong
```

---

## 2) Build Workspace

Clone workspace from GitHub then run on both machines:

```bash
cd ~/MATE2026
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

---

## 3) DDS Networking (ROS cross-machine)

Run on both machines (same value on both):

```bash
echo 'export ROS_DOMAIN_ID=42' >> ~/.bashrc
source ~/.bashrc
```

Quick check:

```bash
# machine A
ros2 topic pub /test std_msgs/String "data: hello"

# machine B
ros2 topic echo /test
```

---

## 4) QGroundControl + Drive Setup (High Level)

Drive is handled outside of ROS by QGroundControl. To set up:

1. Connect QGroundControl to your autopilot (USB/telemetry Ethernet).
2. Calibrate joystick in QGroundControl.
3. Configure vehicle mode/buttons in QGroundControl.
4. Verify thruster response in QGC motor test / armed mode.

---

## 5) Video to QGroundControl (via ROS bridge)

- `camera_node` publishes `/rov/camera/image_compressed` on onboard.
- `qgc_video_bridge_node` on laptop subscribes and forwards low-latency H.264 over RTP to `udp_host:udp_port` (default port `5600`) using `ffmpeg`.
- In QGroundControl, set video source to UDP and port `5600`.
- If video does not decode in your QGC build, set `output_format: h264` in `src/rov_control/config/control_params.yaml` as fallback.

Run onboard:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_onboard camera_only_launch.py
```

Run laptop:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control camera_viewer_only_launch.py
```

If QGC does not show video:

```bash
# verify compressed topic exists
ros2 topic list | grep /rov/camera/image_compressed

# verify stream rate
ros2 topic hz /rov/camera/image_compressed
```

---

## 6) Control-Side Monocular SLAM

This runs on the **control laptop** and stays separate from the QGC bridge. By
default it subscribes to `/rov/camera/image_compressed`, which keeps network load
low while still using the robot's existing camera feed.

### 6.1 Calibrate the camera first

Before you rely on monocular SLAM, run the calibration workflow so the control
laptop has a proper intrinsics/distortion model for the wide-angle USB camera.

Generate a matching checkerboard locally (9x6 inner corners, 25 mm squares):

```bash
cd ~/MATE-2026
source install/setup.bash
ros2 run rov_slam generate_checkerboard
```

Print the generated SVG at 100% scale (disable fit-to-page).

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_slam camera_calibration_launch.py
```

Hold a printed chessboard in front of the camera and move it around until the
node accepts enough varied samples and writes `~/.ros/rov_camera_calibration.yaml`.

The calibration node also publishes `/rov/camera/camera_info`, so once it has
solved the intrinsics, `monocular_slam_node` can consume the calibration live.

### 6.2 Start the SLAM pipeline + RViz

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_slam slam_only_launch.py
```

The launch file starts the monocular SLAM node and RViz. The RViz layout shows:
- `TF` for the current robot pose
- `/rov/slam/path` for the motion trail
- `/rov/slam/map_points` for the sparse landmark map
- `Camera Image (2D)` using `/rov/slam/overlay_image` with projected map points drawn on top

### 6.3 Tune the camera model if needed

Edit `src/rov_slam/config/slam_params.yaml` to match your camera:
- keep `input_mode: compressed` for the lowest bandwidth path
- switch to `input_mode: raw` and `image_topic: /rov/camera/image_raw` if you want raw frames instead
- set `camera_info_topic` when you later add a calibrated camera publisher
- adjust `horizontal_fov_deg`, `fx`, `fy`, `cx`, `cy`, or `dist_coeffs` if your camera model changes

This monocular pipeline is fully usable on its own, but because it is monocular it
still has relative scale ambiguity. When you move to the Intel RealSense D400,
you can keep the same control-side launch path and feed it calibrated camera info
or a depth-enabled workflow for metric scale assistance.

---

## 7) Arm Control Path Setup

### 7.1 Encoder publisher contract (laptop)

There is a script/node that reads 8 encoder values from USB and publishes to ROS topic:
- topic: `/rov/arm/encoder_values`
- type: `std_msgs/Float32MultiArray`
- `data` length: 8

These values can be degrees or raw units. Mapping to servo angles is done in `control_params.yaml` (`scales` and `offsets_deg`).

### 7.2 Start arm bridge on laptop

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control arm_only_launch.py
```

### 7.3 Start onboard servo node

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_onboard arm_only_launch.py
```

### 7.4 Enable real PinPong output

Edit `src/rov_onboard/config/onboard_params.yaml`:

- `use_pinpong: true`
- set `pinpong_board` and `pinpong_port`
- set `servo_pins` to your wiring
- tune min/max/neutral values per axis

Then rebuild onboard:

```bash
cd ~/MATE2026
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

---

## 8) Full Launch (Simplified)

Onboard:

```bash
cd ~/MATE2026
source install/setup.bash
export QGC_IP=<CONTROL_LAPTOP_IP>
ros2 launch rov_onboard onboard_launch.py
```

`onboard_launch.py` now auto-starts MAVLink forwarding (`mavlink-routerd`) when `QGC_IP` is set
or when `qgc_ip:=...` is passed directly:

```bash
ros2 launch rov_onboard onboard_launch.py qgc_ip:=<CONTROL_LAPTOP_IP> pix_serial:=/dev/ttyACM0 pix_baud:=115200
```

If needed, disable forwarding for bench tests:

```bash
ros2 launch rov_onboard onboard_launch.py enable_mavlink_forward:=false
```

Laptop:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control control_launch.py
```

---

## Key Config Files

- `src/rov_control/config/control_params.yaml`
  - encoder input topic
  - axis scaling/offset/clamps
  - QGC bridge UDP/ffmpeg settings
- `src/rov_slam/config/slam_params.yaml`
  - SLAM input topic and camera calibration defaults
  - ORB / PnP / keyframe tuning
  - RViz-friendly map and pose visualization settings
- `src/rov_slam/config/camera_calibration_params.yaml`
  - chessboard size and capture settings
  - saved calibration file path
  - live `CameraInfo` publishing options
- `src/rov_onboard/config/onboard_params.yaml`
  - camera settings
  - PinPong + servo pin/range/timeout settings

---

## Notes

- Keep ROS and QGC responsibilities separate:
  - ROS: arm + camera transport + control-side SLAM
  - QGC/autopilot: vehicle drive and piloting

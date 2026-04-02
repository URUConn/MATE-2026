# MATE 2026 ROV
### UConn Underwater Robotics Club

MATEROV is an underwater robotics competition. This repository contains the ROS workspace for our 2026 entry, which includes:
- **ROS 2 handles:**
  - arm encoder values from the control laptop -> onboard servo commands
  - camera transport used by a QGC video bridge
- **QGroundControl + autopilot stack** handles vehicle driving/thrusters.

---

## Architecture

```
Control Laptop (Ubuntu + QGroundControl + ROS 2)          Onboard Computer (Ubuntu + ROS 2 + autopilot HW)

[QGroundControl] --MAVLink--> [Autopilot/ESCs]            (drive control path, not ROS)
      ^
      | UDP video :5600 from ROS bridge
[rov_control/qgc_video_bridge_node] <-- ROS compressed image -- [rov_onboard/camera_node]

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
  - `slam_image_bridge_node`
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
| `/rov/slam/image_raw` | `sensor_msgs/Image` | Laptop local (from bridge) | dedicated decoded stream for SLAM            |

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

## 5.1) Real-time SLAM stream on control side (separate from QGC bridge)

- `slam_image_bridge_node` subscribes to `/rov/camera/image_compressed` and republishes decoded frames to `/rov/slam/image_raw`.
- SLAM should subscribe to `/rov/slam/image_raw`, not the QGC bridge output.
- This keeps SLAM independent from ffmpeg/QGC transport load.

Run only the SLAM bridge on the laptop:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control slam_only_launch.py
```

Quick verify:

```bash
ros2 topic hz /rov/slam/image_raw
ros2 topic echo /rov/slam/image_raw --once
```

---

## 6) Arm Control Path Setup

### 6.1 Encoder publisher contract (laptop)

There is a script/node that reads 8 encoder values from USB and publishes to ROS topic:
- topic: `/rov/arm/encoder_values`
- type: `std_msgs/Float32MultiArray`
- `data` length: 8

These values can be degrees or raw units. Mapping to servo angles is done in `control_params.yaml` (`scales` and `offsets_deg`).

### 6.2 Start arm bridge on laptop

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control arm_only_launch.py
```

### 6.3 Start onboard servo node

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_onboard arm_only_launch.py
```

### 6.4 Enable real PinPong output

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

## 7) Full Launch (Simplified)

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

Control launch defaults now include both video consumers:
- `qgc_video_bridge_node` (QGC UDP output)
- `slam_image_bridge_node` (local SLAM stream)

Optional toggles:

```bash
# disable QGC forwarding, keep SLAM stream
ros2 launch rov_control control_launch.py enable_qgc_bridge:=false

# disable SLAM stream, keep QGC forwarding
ros2 launch rov_control control_launch.py enable_slam_bridge:=false
```

---

## Key Config Files

- `src/rov_control/config/control_params.yaml`
  - encoder input topic
  - axis scaling/offset/clamps
  - QGC bridge UDP/ffmpeg settings
  - SLAM bridge input/output topic + QoS mode
- `src/rov_onboard/config/onboard_params.yaml`
  - camera settings
  - PinPong + servo pin/range/timeout settings

---

## Notes

- Keep ROS and QGC responsibilities separate:
  - ROS: arm + camera transport
  - QGC/autopilot: vehicle drive and piloting

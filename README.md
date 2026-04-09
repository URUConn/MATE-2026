# MATE 2026 ROV
### UConn Underwater Robotics Club

MATEROV is an underwater robotics competition. This repository contains the ROS workspace for our 2026 entry, which includes:
- **ROS 2 handles:**
  - arm encoder values from the control laptop -> onboard servo commands
  - camera transport and optional legacy UDP video bridge
- **Autopilot + GCS stack** handles vehicle driving/thrusters.

---

## Architecture

```
Control Laptop (Ubuntu + Cockpit + ROS 2)                 Onboard Computer (Ubuntu + ROS 2 + autopilot HW)

[Cockpit UI] --HTTP/WebSocket--> [MAVLink2REST]           (vehicle telemetry/control path, not ROS)
[Cockpit UI] --WebRTC signaling--> [Onboard signaling svc]

[arm controller encoder USB] --/rov/arm/encoder_values--> [rov_control/arm_encoder_bridge_node]
                                                           |
                                                           '--/rov/arm/servo_command--> [rov_onboard/arm_servo_node -> PinPong servos]

Optional legacy path:
[rov_control/qgc_video_bridge_node] <-- ROS compressed image -- [rov_onboard/camera_node] -> UDP video :5600
```

---

## ROS File Structure
Split into 2 main packages for the two hardware stacks, plus a shared messages package:

- `rov_msgs`
  - `ArmServoCommand.msg`
- `rov_control` (runs on control laptop)
  - `arm_encoder_bridge_node`
  - `qgc_video_bridge_node` (optional legacy UDP video bridge)
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

`ArmServoCommand` axis order defaults to:
`[base, shoulder, elbow, wrist_pitch, wrist_roll, wrist_yaw, tool_rotate, gripper]`

---

## 1) Install Dependencies

Run all commands on both machines unless noted.

- Assumes ROS 2 Humble and Ubuntu 22.04.
- Cockpit on the control laptop needs onboard MAVLink2REST and WebRTC signaling services.
- BlueOS provides these services out of the box. If you are not using BlueOS, you must deploy equivalent services.

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

## 4) Cockpit + Drive Setup (High Level)

Drive is handled outside of ROS by Cockpit + autopilot services on onboard.

### 4.1 Cockpit connection fields

In Cockpit vehicle settings, set these endpoints to your onboard computer:

- **Vehicle Address**: `<ONBOARD_IP_OR_HOSTNAME>`
- **MAVLink2REST backend**: `http://<ONBOARD_IP_OR_HOSTNAME>:<MAVLINK2REST_PORT>`
- **WebRTC signaling backend**: `http://<ONBOARD_IP_OR_HOSTNAME>:<WEBRTC_SIGNALING_PORT>`

If the onboard address changes, update `Vehicle Address` first, then also update both backend URLs if they do not auto-follow the global address in your Cockpit build/profile.

For BlueOS deployments, use the ports shown on the BlueOS Services page (MAVLink2REST is commonly `6040`).

If you are **not** using BlueOS, install and run `mavlink2rest` yourself. In this repo, the ROS laptop launch will try to auto-start it locally by default.

### 4.2 Example values (if your network is 192.168.50.x)

- Control laptop: `192.168.50.1`
- Onboard computer: `192.168.50.2`
- Cockpit fields:
  - Vehicle Address: `192.168.50.2`
  - MAVLink2REST backend: `http://127.0.0.1:6040` (if you launch `mavlink2rest` from the laptop via `rov_control/control_launch.py`)
  - WebRTC signaling backend: `http://192.168.50.2:<signaling_port_from_BlueOS>`

### 4.3 Functional checks

1. Verify Cockpit telemetry updates after connecting to your vehicle profile.
2. Verify joystick/gamepad mapping in Cockpit.
3. Verify mode/arm/disarm actions are available in Cockpit.
4. Verify thruster response in water/bench-safe conditions.

---

## 5) Video in Cockpit (Primary) + Legacy UDP Bridge (Optional)

Primary path for Cockpit:

- `camera_node` publishes `/rov/camera/image_compressed` on onboard for ROS consumers.
- Cockpit video is expected to come from onboard WebRTC services (for example BlueOS camera services), not from `qgc_video_bridge_node`.

Optional legacy fallback path (for UDP-only viewers):

- `qgc_video_bridge_node` on laptop can still forward `/rov/camera/image_compressed` to `udp_host:udp_port` using `ffmpeg`.

Run onboard camera node:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_onboard camera_only_launch.py
```

Run legacy UDP bridge only when needed:

```bash
cd ~/MATE2026
source install/setup.bash
ros2 launch rov_control camera_viewer_only_launch.py
```

If Cockpit video is missing, verify onboard services and ROS camera topic:

```bash
# verify compressed topic exists
ros2 topic list | grep /rov/camera/image_compressed

# verify stream rate
ros2 topic hz /rov/camera/image_compressed
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
ros2 launch rov_onboard onboard_launch.py
```

For Cockpit-only operation, you can leave `GCS_IP` unset.

If you also need legacy MAVLink UDP forwarding to a topside host,
`onboard_launch.py` auto-starts `mavlink-routerd` when `GCS_IP` is set
or when `gcs_ip:=...` is passed directly:

```bash
ros2 launch rov_onboard onboard_launch.py gcs_ip:=<CONTROL_LAPTOP_IP> pix_serial:=/dev/ttyACM0 pix_baud:=115200
```

Legacy compatibility aliases still work (`qgc_ip:=...`, `qgc_port:=...`).

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

That launch now tries to start `mavlink2rest` locally by default. If the binary is not installed, it will print a warning and continue starting the rest of the ROS nodes.

Non-BlueOS Cockpit telemetry backend (auto-start `mavlink2rest` from ROS launch):

```bash
ros2 launch rov_control control_launch.py enable_mavlink2rest:=true
```

Defaults used by this launch:

- `mavlink2rest_bin:=mavlink2rest`
- `mavlink2rest_source:=udpin:0.0.0.0:14550`
- `mavlink2rest_port:=6040`

Example with explicit overrides:

```bash
ros2 launch rov_control control_launch.py \
  enable_mavlink2rest:=true \
  mavlink2rest_bin:=mavlink2rest \
  mavlink2rest_source:=udpin:0.0.0.0:14550 \
  mavlink2rest_port:=6040
```

Then set Cockpit `MAVLink2REST backend` to:

- `http://127.0.0.1:6040` if Cockpit and `mavlink2rest` are on the same laptop
- `http://<HOST_RUNNING_MAVLINK2REST>:6040` if you move it to another host

If you need the legacy UDP video bridge on laptop too:

```bash
ros2 launch rov_control control_launch.py enable_udp_video_bridge:=true
```

---

## Key Config Files

- `src/rov_control/config/control_params.yaml`
  - encoder input topic
  - axis scaling/offset/clamps
  - optional legacy UDP bridge/ffmpeg settings
- `src/rov_onboard/config/onboard_params.yaml`
  - camera settings
  - PinPong + servo pin/range/timeout settings

---

## Notes

- Keep ROS and vehicle-control responsibilities separate:
  - ROS: arm + camera transport
  - Cockpit/autopilot services: vehicle drive and piloting

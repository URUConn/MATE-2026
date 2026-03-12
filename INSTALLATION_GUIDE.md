# MATE 2026 ROV - Complete Installation & Setup Guide

## Overview
This guide covers installing all dependencies, configuring hardware (Radiolink PIX6 with ArduSub), and integrating Xbox controller input with MAVROS for thruster control on the LattePanda.

**System Architecture:**
```
┌─────────────────────────────────┐          ┌──────────────────────────────────┐
│     LattePanda + PIX6           │          │     Laptop (Jetson Nano)         │
│     Ubuntu 22.04 + ROS 2        │   LAN    │      Ubuntu 22.04 + ROS 2        │
│     MAVROS2 + ArduSub (PIX6)    │◄────────►│  rov_control package:            │
│                                 │          │    • Xbox Controller Support      │
│  rov_onboard package:           │          │    • Keyboard Fallback           │
│    • mavros_bridge_node ────────┐         │                                  │
│    • camera_node                │publish──►│    • camera_viewer_node          │
│    • sensor_node                │──────────►    • dashboard_node              │
│    • status_node                │          │    • gamepad_node                │
└─────────────────────────────────┘          └──────────────────────────────────┘
         PIX6 Flight Controller
         (ArduSub via MAVLink)
         Connected via USB
```

---

## STEP 1: Install Dependencies (Both Machines)

### Prerequisites
- Both machines on same LAN (Ethernet recommended)
- Ubuntu 22.04 with ROS 2 Humble already installed
- Python 3.10+

### Install System Packages (Both Machines)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# ROS 2 Humble (if not already installed)
source /opt/ros/humble/setup.bash

# Install Python dependencies
sudo apt install -y \
    python3-pip \
    python3-dev \
    python3-opencv \
    python3-yaml \
    ros-humble-cv-bridge \
    ros-humble-image-transport \
    build-essential \
    git

# Python packages
pip3 install --upgrade pip setuptools wheel
pip3 install pygame pyyaml
```

---

## STEP 2: Install MAVROS2 (LattePanda Only)

MAVROS2 provides the ROS 2 interface to the PIX6 flight controller via MAVLink.

### On LattePanda:

```bash
# Install MAVROS2 package
sudo apt install -y ros-humble-mavros ros-humble-mavros-msgs

# Download and install GeographicLib datasets (required by MAVROS)
cd ~/
wget https://raw.githubusercontent.com/mavlink/mavros/humble-devel/mavros/scripts/install_geographiclib_datasets.sh
chmod +x install_geographiclib_datasets.sh
sudo ./install_geographiclib_datasets.sh

# Verify installation
ros2 pkg list | grep mavros
```

---

## STEP 3: Configure PIX6/ArduSub Hardware

### What You Need
- Radiolink PIX6 flight controller
- USB cable (Micro-USB or USB-C, depending on your PIX6 variant)
- QGroundControl (for initial configuration)

### On the LattePanda:

#### 3.1 Download & Install QGroundControl
```bash
# Download from official source
wget https://d176tv9uyzvq55.cloudfront.net/latest/QGroundControl.AppImage
chmod +x QGroundControl.AppImage
./QGroundControl.AppImage &
```

#### 3.2 Flash ArduSub Firmware to PIX6
1. Connect PIX6 to LattePanda via USB
2. Open QGroundControl
3. Go to **Vehicle Setup → Firmware**
4. Select **ArduSub** from the dropdown (instead of ArduCopter)
5. Click **OK** to download and flash
6. Wait for completion (2-3 minutes)

#### 3.3 Configure ArduSub Parameters
In QGroundControl, go to **Vehicle Setup → Parameters** and verify:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `SERIAL0_BAUD` | 115200 | USB communication speed |
| `SERIAL0_PROTOCOL` | 2 (MAVLink) | Enable MAVLink on USB |
| `SERIAL1_BAUD` | 115200 | (if using UART for other sensors) |
| `FRAME_CLASS` | 2 (Vectored) | Frame type for ROV |
| `MANUAL_RC_MODE` | 0 | Use MANUAL mode |
| `JSK_ENA` | 0 | Joystick disabled (we use MAVLink) |

#### 3.4 Calibrate
- Compass calibration (Vehicle Setup → Compass)
- Radio calibration (Vehicle Setup → Radio)
- ESC/Thruster calibration (in ArduSub docs)

#### 3.5 Test MAVLink Connection
After flashing, verify USB device appears:
```bash
# List USB devices
lsusb
# Should show "Silicon Labs CP210x UART Bridge Controller" or similar

# Check device port
ls /dev/ttyUSB* /dev/ttyACM*
# Typically /dev/ttyACM0 or /dev/ttyUSB0
```

---

## STEP 4: Configure ROS 2 DDS for Network Communication

### On Both Machines

```bash
# Set ROS domain ID (use any number 0-232, both must match)
echo 'export ROS_DOMAIN_ID=42' >> ~/.bashrc

# Source ROS 2 and workspace
echo 'source /opt/ros/humble/setup.bash' >> ~/.bashrc
echo 'source ~/mate_rov_ws/install/setup.bash' >> ~/.bashrc

# Apply changes
source ~/.bashrc
```

### Verify Network Communication

**On LattePanda:**
```bash
ros2 topic pub /test std_msgs/String "data: hello" &
```

**On Laptop:**
```bash
ros2 topic echo /test
```
You should see "hello" printed every second.

---

## STEP 5: Build the Workspace

### On Both Machines

```bash
cd ~/mate_rov_ws

# Ensure ROS 2 is sourced
source /opt/ros/humble/setup.bash

# Build all packages
colcon build --symlink-install

# Source the built workspace
source install/setup.bash
```

If you get dependency errors, run:
```bash
rosdep install --from-paths src --ignore-src -r -y
```

---

## STEP 6: Verify Hardware Connection

### On LattePanda (before running ROS):

```bash
# Find PIX6 serial port
ls -la /dev/ttyACM* /dev/ttyUSB*

# Test MAVLink connection (install mavlink CLI if needed)
# Or check with QGroundControl - should show "Connected"
```

### Determine Serial Port Name
- Most common: `/dev/ttyACM0` (default)
- If multiple devices, might be `/dev/ttyUSB0`, `/dev/ttyUSB1`, etc.
- **Update in config**: see Step 7 below

---

## STEP 7: Configure PIX6 Serial Port in ROS

Edit `src/rov_onboard/config/onboard_params.yaml`:

```yaml
# ...existing params...

mavros:
  ros__parameters:
    # PIX6 serial port (check with: ls /dev/ttyACM*)
    port: "/dev/ttyACM0"
    baud_rate: 115200
    # Set to true ONLY when hardware is ready
    armed: false
```

---

## STEP 8: Launch the System

### Terminal 1: LattePanda (Onboard)
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_onboard onboard_launch.py
```

Expected output:
```
[onboard_launch.py] Starting onboard nodes...
[camera_node-1] Camera opened: 640x480 @ 30fps
[sensor_node-2] Sensor node started
[mavros_bridge_node-3] MAVROS node started, waiting for FCU...
[mavros_bridge_node-3] FCU connected via /dev/ttyACM0
```

### Terminal 2: Laptop (Control Station)
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_control control_launch.py
```

Expected output:
```
[control_launch.py] Starting control nodes...
[gamepad_node-1] Gamepad connected: Xbox 360 Controller
[camera_viewer_node-2] Waiting for camera feed...
[dashboard_node-3] Dashboard started
```

---

## STEP 9: Test Xbox Controller Input

### Quick Test
With both systems running:

```bash
# On laptop, watch the thruster command topic
ros2 topic echo /rov/thruster_command

# Move the Xbox controller sticks around
# You should see values change in the output
```

### Full System Test
1. **On LattePanda**, monitor the MAVROS override topic:
   ```bash
   ros2 topic echo /mavros/rc/override
   ```

2. **On Laptop**, press Xbox controller sticks
3. **Verify** the `/mavros/rc/override` topic shows RC channel values

---

## STEP 10: Keyboard Fallback (Testing Without Controller)

If no Xbox controller is connected, the system automatically falls back to keyboard:

```bash
# On laptop, click the "ROV Keyboard Control" pygame window so it has keyboard focus
# Press keys:
#  W/A/S/D - Forward/Left/Back/Right
#  Up/Down - Vertical thrusters
#  Left/Right - Yaw (rotation)
#  Space - Stop all thrusters
```

---

## STEP 11: Arming the ROV

Once everything is running and tested:

1. **QGroundControl**: Disarm safety by selecting **"Disarmed"** in the flight mode dropdown
2. **Update config**: Set `armed: true` in `onboard_params.yaml`
3. **Rebuild & relaunch**:
   ```bash
   colcon build --symlink-install
   source install/setup.bash
   ros2 launch rov_onboard onboard_launch.py
   ```

**⚠️ WARNING**: Do NOT arm until:
- All thrusters are installed
- ESCs are calibrated
- Propellers are attached
- Safety checks are complete

---

## Troubleshooting

### PIX6 Not Detected
```bash
# Check if device appears
lsusb

# If not listed:
1. Try different USB cable
2. Check USB port on both devices
3. Reinstall CH340 driver (if using clone PIX6):
   sudo apt install -y ch340-dkms

# Verify port
dmesg | tail -20  # Look for device connection message
```

### MAVROS Won't Connect
```bash
# Check serial port permissions
ls -la /dev/ttyACM0

# If not readable, fix permissions
sudo usermod -a -G dialout $USER
newgrp dialout

# Restart the node
```

### No Xbox Controller Detected
```bash
# Check if connected
lsusb | grep -i xbox

# Test pygame detection
python3 -c "import pygame; pygame.init(); print(pygame.joystick.get_count())"

# Fallback to keyboard (automatic)
```

### Network Communication Not Working
```bash
# Verify domain ID on both machines
echo $ROS_DOMAIN_ID  # Should be 42

# Check firewall (if applicable)
sudo ufw allow in proto udp to 224.0.0.0/4
sudo ufw allow in proto udp from 192.168.1.0/24

# Ping between machines
ping <other-machine-ip>

# Check DDS implementation
ros2 run rclpy_tutorials listener  # On one machine
ros2 run rclpy_tutorials talker   # On other machine
```

---

## File Structure (Updated)

```
mate_rov_ws/
├── INSTALLATION_GUIDE.md              # This file
├── src/
│   ├── rov_msgs/
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   └── msg/
│   │       ├── ThrusterCommand.msg
│   │       ├── SensorData.msg
│   │       └── RovStatus.msg
│   │
│   ├── rov_onboard/
│   │   ├── package.xml
│   │   ├── setup.py
│   │   ├── setup.cfg
│   │   ├── config/
│   │   │   └── onboard_params.yaml    # PIX6 serial port config here
│   │   ├── launch/
│   │   │   ├── onboard_launch.py      # Launch all onboard nodes
│   │   │   └── camera_only_launch.py
│   │   └── rov_onboard/
│   │       ├── __init__.py
│   │       ├── camera_node.py
│   │       ├── sensor_node.py
│   │       ├── status_node.py
│   │       ├── thruster_node.py
│   │       └── mavros_bridge_node.py  # NEW: MAVROS integration
│   │
│   └── rov_control/
│       ├── package.xml
│       ├── setup.py
│       ├── setup.cfg
│       ├── config/
│       │   └── control_params.yaml
│       ├── launch/
│       │   ├── control_launch.py      # Updated: add keyboard fallback
│       │   └── camera_viewer_only_launch.py
│       └── rov_control/
│           ├── __init__.py
│           ├── camera_viewer_node.py
│           ├── gamepad_node.py        # Updated: add keyboard input
│           └── dashboard_node.py
```

---

## Next Steps

1. **Complete hardware calibration**: Follow QGroundControl guides for compass, radio, and ESC calibration
2. **Test in tank**: Start with limited power settings
3. **Tune control**: Adjust deadzone and max_power in config files
4. **Add telemetry**: Implement SensorData and RovStatus publishing from PIX6 attitude/depth
5. **Video encoding**: Switch from raw camera to H.264 for bandwidth optimization
6. **Failsafe configuration**: Set RTH (Return to Home) or Safe mode in ArduSub

---

## Quick Reference Commands

```bash
# Build workspace
cd ~/mate_rov_ws && colcon build --symlink-install

# Source workspace
source ~/mate_rov_ws/install/setup.bash

# Launch onboard (LattePanda)
ros2 launch rov_onboard onboard_launch.py

# Launch control (Laptop)
ros2 launch rov_control control_launch.py

# Monitor ROS topics
ros2 topic list
ros2 topic echo /rov/thruster_command
ros2 topic echo /mavros/rc/override

# Debug MAVROS connection
ros2 service call /mavros/set_stream_rate mavros_msgs/StreamRate "{stream_id: 0, message_rate: 10, on_off: 1}"

# View active nodes
ros2 node list
```

---

## Support

- MAVROS Docs: https://docs.px4.io/main/en/ros/
- ArduSub Docs: https://ardupilot.org/ardusub/
- ROS 2 Humble: https://docs.ros.org/en/humble/


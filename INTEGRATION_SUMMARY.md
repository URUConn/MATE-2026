# MATE-2026 ROV - MAVLink Integration Summary

## What Was Done

Your MATE-2026 ROV project has been fully integrated with MAVLink communication for the **Radiolink PIX6** autopilot running **ArduSub**. This enables thruster control, sensor telemetry, and failsafe management through ROS2.

### New Package Created: `rov_mavlink`

A complete MAVLink bridge package was created with the following components:

#### Files Created:
```
src/rov_mavlink/
├── package.xml                          # ROS2 package manifest
├── setup.py                             # Python package setup
├── setup.cfg                            # Build configuration
├── resource/rov_mavlink                 # Package resource file
├── config/
│   └── mavlink_params.yaml              # MAVLink configuration (serial port, baud, etc.)
├── launch/
│   └── mavlink_launch.py                # Standalone MAVLink launch file
└── rov_mavlink/
    ├── __init__.py
    ├── mavlink_bridge_node.py           # Main MAVLink bridge (400+ lines)
    └── mavlink_utils.py                 # MAVLink utilities (PWM normalization, etc.)
```

#### Key Features:

1. **Bidirectional Communication**
   - Subscribes to `/rov/thruster_command` from gamepad/control laptop
   - Converts ROS2 commands to MAVLink SERVO_CONTROL messages
   - Receives MAVLink telemetry and publishes to `/rov/sensor_data` and `/rov/status`

2. **Thread-Safe Operation**
   - Background thread for MAVLink serial/UDP communication
   - ROS2 main thread for subscription/publication
   - Automatic reconnection with retry logic

3. **Servo Channel Mapping**
   - Configurable mapping of 6 thrusters → PIX6 servo channels 1-6
   - PWM normalization (±1.0 → 1100-1900 microseconds)
   - Support for 8 servo channels (expandable for future accessories)

4. **Supported Messages**
   - **Outgoing**: HEARTBEAT, SERVO_CONTROL, COMMAND_LONG (arm/disarm)
   - **Incoming**: HEARTBEAT, SYS_STATUS, ATTITUDE, GLOBAL_POSITION_INT, RANGEFINDER, BATTERY_STATUS, SERVO_OUTPUT_RAW

5. **Configuration**
   - Serial connection (default): `/dev/ttyUSB0:115200`
   - UDP support: `udp:192.168.1.100:14550`
   - Configurable heartbeat interval (default 10 Hz)
   - Configurable telemetry rate (default 10 Hz)

### Modified Files

1. **src/rov_onboard/launch/onboard_launch.py**
   - Added `mavlink_bridge_node` to system launch
   - Added configurable `mavlink_connection` launch argument
   - Node now launches automatically with other onboard services

2. **src/rov_onboard/rov_onboard/thruster_node.py**
   - Updated documentation to explain MAVLink integration
   - Node now acts as a pass-through for thruster commands
   - MAVLink bridge handles actual autopilot communication

3. **src/rov_onboard/package.xml**
   - Added `rov_mavlink` dependency

### Documentation Created

1. **MAVLINK_SETUP.md** (Comprehensive 300+ line guide)
   - Hardware connection diagrams
   - Step-by-step setup for LattePanda and Control Laptop
   - PIX6 configuration in QGroundControl
   - Network setup (ROS2 domain ID, firewall)
   - Launch instructions
   - Verification and testing procedures
   - Troubleshooting guide with common issues
   - Reference links

2. **requirements.txt**
   - Python dependencies (pymavlink, dronekit, pygame, opencv-python)
   - Easy installation with `pip install -r requirements.txt`

3. **install.sh** (Automated setup script)
   - Complete Ubuntu 22.04 installation automation
   - ROS2 Humble installation
   - Workspace creation
   - Dependency installation
   - Build automation

4. **Updated README.md**
   - Added MAVLink architecture diagram
   - Quick start section for MAVLink
   - Link to detailed MAVLINK_SETUP.md

---

## Communication Flow

```
┌──────────────────┐
│  Control Laptop  │
│  (gamepad_node)  │
└────────┬─────────┘
         │
         │ publishes to /rov/thruster_command
         │ (ThrusterCommand message)
         ▼
┌──────────────────────────────────┐
│        LattePanda (ROS2)         │
│                                  │
│  ┌──────────────────────────┐   │
│  │   mavlink_bridge_node    │   │
│  │                          │   │
│  │ Subscribes:              │   │
│  │  /rov/thruster_command   │   │
│  │                          │   │
│  │ Publishes:               │   │
│  │  /rov/sensor_data        │   │
│  │  /rov/status             │   │
│  └────────────┬─────────────┘   │
└───────────────┼──────────────────┘
                │
                │ MAVLink Protocol (Serial/USB)
                │ Port: /dev/ttyUSB0 @ 115200 baud
                │
                ▼
        ┌──────────────────┐
        │  Radiolink PIX6  │
        │  (ArduSub)       │
        │  Autopilot       │
        └────────┬─────────┘
                 │
         ┌───────┴───────┐
         │               │
         │ PWM/DShot     │
         │               │
         ▼               ▼
    ┌─────────┐   ┌──────────┐
    │Thrusters│   │ Sensors  │
    └─────────┘   ├──────────┤
                  │Depth     │
                  │IMU       │
                  │Battery   │
                  │Leak Det. │
                  └──────────┘
```

---

## System Architecture (Complete)

### LattePanda (Onboard)
- **rov_onboard**: Camera, sensors, status, thruster nodes
- **rov_mavlink**: MAVLink bridge to PIX6
- ROS2 Humble with DDS networking

### PIX6 Autopilot
- **ArduSub** firmware
- **ChibiOS** RTOS
- 8 servo outputs (thrusters + accessories)
- Built-in sensors (IMU, compass, barometer)
- Failsafe logic

### Control Laptop
- **rov_control**: Gamepad input, camera viewer, dashboard
- ROS2 Humble (same as LattePanda)
- Network-connected via UDP ROS2 bridge

---

## Installation Quick Start

### 1. On LattePanda (connected via SSH or locally)

```bash
# Clone/setup repository
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws
git clone <your-repo> src/

# Run installation script
bash src/install.sh

# Source setup
source install/setup.bash
export ROS_DOMAIN_ID=42

# Launch system
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=/dev/ttyUSB0:115200
```

### 2. On Control Laptop

```bash
# Same setup as LattePanda
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws
git clone <your-repo> src/

bash src/install.sh

# Source setup
source install/setup.bash
export ROS_DOMAIN_ID=42

# Launch control
ros2 launch rov_control control_launch.py
```

### 3. Configure PIX6 (in QGroundControl)

- **SERIAL2_PROTOCOL**: 38 (MAVLink v2)
- **SERIAL2_BAUD**: 115200
- **SYSID_THISMAV**: 1 (default)
- Set up servo channels 1-6 for thrusters
- Configure failsafes as needed

---

## Key Configuration Files

### `/src/rov_mavlink/config/mavlink_params.yaml`

```yaml
/**:
  ros__parameters:
    connection_string: '/dev/ttyUSB0:115200'  # Change if using different port
    system_id: 1                                # Match PIX6 SYSID_THISMAV
    component_id: 191                           # 191 = Submarine
    heartbeat_interval: 0.1                     # 10 Hz
    telemetry_rate: 10                          # 10 Hz updates
    servo_channel_mapping: [1, 2, 3, 4, 5, 6]  # Thruster channels
```

### Launch with custom connection:

```bash
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=udp:192.168.1.100:14550
```

---

## Next Steps

1. **Test Connection**
   - Plug in PIX6 USB cable
   - Launch system and check for "MAVLink connection established!"
   - Verify topics with `ros2 topic list`

2. **Verify Telemetry**
   ```bash
   ros2 topic echo /rov/status      # Check armed state, mode
   ros2 topic echo /rov/sensor_data # Check attitude, depth, battery
   ```

3. **Test Thruster Commands**
   ```bash
   # Manual command via CLI
   ros2 topic pub /rov/thruster_command rov_msgs/ThrusterCommand \
     "{thruster_front_left: 0.5, thruster_front_right: 0.5, ...}"
   
   # Or use gamepad in control_launch.py
   ```

4. **Implement Arm/Disarm in Gamepad**
   - Add button mapping to `gamepad_node.py`
   - Call `mavlink_bridge_node.arm_autopilot()` or similar ROS service

5. **Add Real Sensors**
   - Extend `sensor_node.py` to read actual depth, IMU data from PIX6
   - Or read directly from sensors connected to LattePanda

---

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| "Connection failed" | Check USB cable, run `ls /dev/ttyUSB*`, verify PIX6 powered |
| "No heartbeat" | Check baud rate, PIX6 SERIAL2_PROTOCOL set to 38, wrong port |
| Topics not visible | Check `ROS_DOMAIN_ID=42` on both machines, firewall, network connectivity |
| Low telemetry rate | Reduce `telemetry_rate` in config, check CPU usage on LattePanda |
| Servo commands not received | Check channel mapping in `servo_channel_mapping`, verify PIX6 servo setup |

---

## File Structure (Complete)

```
MATE-2026/
├── README.md                          # Main project README (updated)
├── MAVLINK_SETUP.md                   # NEW: Detailed setup guide
├── install.sh                         # NEW: Automated installation
├── requirements.txt                   # NEW: Python dependencies
├── LICENSE
├── src/
│   ├── rov_msgs/                      # Custom message definitions
│   │   ├── CMakeLists.txt
│   │   ├── package.xml
│   │   └── msg/
│   │       ├── ThrusterCommand.msg
│   │       ├── SensorData.msg
│   │       └── RovStatus.msg
│   │
│   ├── rov_mavlink/                   # NEW: MAVLink Bridge Package
│   │   ├── package.xml
│   │   ├── setup.py
│   │   ├── setup.cfg
│   │   ├── resource/rov_mavlink
│   │   ├── config/
│   │   │   └── mavlink_params.yaml
│   │   ├── launch/
│   │   │   └── mavlink_launch.py
│   │   └── rov_mavlink/
│   │       ├── __init__.py
│   │       ├── mavlink_bridge_node.py
│   │       └── mavlink_utils.py
│   │
│   ├── rov_onboard/                   # UPDATED: Added MAVLink integration
│   │   ├── package.xml (updated)
│   │   ├── setup.py
│   │   ├── setup.cfg
│   │   ├── config/onboard_params.yaml
│   │   ├── launch/
│   │   │   ├── onboard_launch.py (updated)
│   │   │   └── camera_only_launch.py
│   │   └── rov_onboard/
│   │       ├── __init__.py
│   │       ├── camera_node.py
│   │       ├── sensor_node.py
│   │       ├── status_node.py
│   │       └── thruster_node.py (updated)
│   │
│   └── rov_control/                   # Control station (no changes)
│       ├── package.xml
│       ├── setup.py
│       ├── setup.cfg
│       ├── config/control_params.yaml
│       ├── launch/control_launch.py
│       └── rov_control/
│           ├── __init__.py
│           ├── camera_viewer_node.py
│           ├── dashboard_node.py
│           └── gamepad_node.py
```

---

## Dependencies Summary

### System (Ubuntu 22.04)
- ROS2 Humble
- Python 3.8+
- OpenCV
- libusb (for USB serial)

### Python (via pip)
- `pymavlink` - MAVLink protocol library
- `dronekit` - High-level autopilot interface
- `pyserial` - Serial port communication
- `opencv-python` - Computer vision
- `pygame` - Gamepad input (control laptop)

### ROS2 Packages
- `rclpy`, `std_msgs`, `sensor_msgs` - Core ROS2
- `cv_bridge`, `image_transport` - Camera integration

---

## Support & References

- **ArduSub Docs**: https://ardupilot.org/
- **MAVLink Protocol**: https://mavlink.io/
- **pymavlink GitHub**: https://github.com/ArduPilot/pymavlink
- **ROS2 Humble**: https://docs.ros.org/en/humble/
- **PIX6 Autopilot**: https://www.radiolink.com.cn/

---

## Summary

Your MATE-2026 ROV now has complete MAVLink integration for communicating with the Radiolink PIX6 autopilot running ArduSub. The system is modular, allowing you to:

✅ Send thruster commands from ROS2 gamepad control
✅ Receive telemetry from PIX6 (attitude, depth, battery)
✅ Manage arm/disarm states
✅ Monitor autopilot health
✅ Expand with custom sensor integration
✅ Implement failsafes and autonomous features

**To get started, follow MAVLINK_SETUP.md for detailed instructions!**


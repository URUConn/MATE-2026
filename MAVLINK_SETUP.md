# MATE-2026 ROV - MAVLink Integration Setup Guide

## Overview

This guide covers the integration of ROS2 with the Radiolink PIX6 autopilot running ArduSub via MAVLink protocol.

### System Architecture

```
┌─────────────────────────────────┐
│     LattePanda (Onboard)        │
│     Ubuntu 22.04 + ROS 2        │
│                                 │
│  rov_onboard package            │
│  ├─ camera_node                 │
│  ├─ sensor_node                 │
│  ├─ thruster_node               │
│  └─ status_node                 │
│                                 │
│  rov_mavlink package (NEW)      │
│  └─ mavlink_bridge_node         │
│      (↔ MAVLink)                │
│         │                        │
│         │ Serial/USB (MAVLink)   │
│         ↓                        │
│  ┌─────────────────┐             │
│  │  Radiolink PIX6 │             │
│  │  ArduSub/ChibiOS            │
│  │  (Autopilot)                │
│  └─────────────────┘             │
│         │                        │
│         │ PWM/DShot              │
│         ↓                        │
│  ┌─────────────────┐             │
│  │   Thrusters,    │             │
│  │   Sensors,      │             │
│  │   Leak Detector │             │
│  └─────────────────┘             │
└─────────────────────────────────┘
         ↑                        ↓
       LAN (UDP ROS2 Bridge)
         ↑                        ↓
┌─────────────────────────────────┐
│  Laptop (Control Station)        │
│  Ubuntu 22.04 + ROS 2           │
│                                 │
│  rov_control package            │
│  ├─ gamepad_node                │
│  ├─ dashboard_node              │
│  └─ camera_viewer_node          │
└─────────────────────────────────┘
```

---

## Prerequisites

### Hardware

1. **Radiolink PIX6 Autopilot** with ArduSub firmware
2. **LattePanda** (or compatible ARM/x86 computer with Ubuntu 22.04)
3. **USB/Serial Cable** to connect LattePanda ↔ PIX6 (FTDI TTL or similar)
4. **Thrusters** with ESCs (configured in ArduSub)
5. **Depth Sensor**, **IMU**, **Battery Monitor** connected to PIX6 (optional, but recommended)

### Software

- Ubuntu 22.04 (LattePanda and/or Control Laptop)
- ROS2 Humble or Iron
- Python 3.8+
- git

---

## STEP 1: Install ROS2

If not already installed, follow the official guide: https://docs.ros.org/en/humble/Installation.html

### Quick Install (Ubuntu 22.04)

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install -y curl gnupg lsb-release

# Add ROS2 repository
curl https://repo.ros2.org/ros.key | sudo apt-key add -
sudo sh -c 'echo "deb [arch=$(dpkg --print-architecture)] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" > /etc/apt/sources.list.d/ros2-latest.list'

# Install ROS2 Humble
sudo apt update
sudo apt install -y ros-humble-desktop
```

### Verify Installation

```bash
source /opt/ros/humble/setup.bash
ros2 --version
```

---

## STEP 2: Clone and Build the MATE-2026 Project

### On LattePanda:

```bash
# Create workspace
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws

# Clone the project
git clone <your-repo-url> src/

# Install dependencies
rosdep update
rosdep install --from-paths src --ignore-src -r -y

# Build
colcon build --symlink-install

# Source the setup script
source install/setup.bash
```

### On Control Laptop:

```bash
# Repeat the same steps as above
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws
git clone <your-repo-url> src/
rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

---

## STEP 3: Install Additional Python Dependencies

The `rov_mavlink` package requires `pymavlink`. Install on **LattePanda**:

```bash
pip install pymavlink dronekit
```

Verify installation:

```bash
python3 -c "import pymavlink; print('pymavlink installed successfully')"
```

---

## STEP 4: Hardware Connection - PIX6 to LattePanda

### Serial Connection (Recommended)

**PIX6 Pin Layout** (typical UART connection):
- **TX (out)** → LattePanda RX
- **RX (in)** → LattePanda TX
- **GND** → GND

Most commonly you'll use a **USB-FTDI adapter** to connect:

1. PIX6 TELEM2 port or DEBUG port:
   - Connect TX/RX/GND pins to FTDI adapter
   - FTDI connects to LattePanda via USB

2. Identify the device on LattePanda:

```bash
ls /dev/ttyUSB*
# Should show /dev/ttyUSB0 or similar
```

3. Test the connection:

```bash
# Install minicom for testing
sudo apt install minicom

# Connect and check for heartbeat (should see data)
minicom -D /dev/ttyUSB0 -b 115200
# Press Ctrl+A, then X to exit
```

### Alternative: UDP Network Connection

If you prefer Ethernet/WiFi:

1. Configure PIX6 for UDP forwarding (in QGroundControl):
   - Set `SERIAL2_PROTOCOL` to MAVLink v2
   - Configure IP forwarding if available

2. Use UDP connection string:
   ```
   udp:192.168.1.100:14550
   ```

---

## STEP 5: Configure MAVLink Parameters

Edit `src/rov_mavlink/config/mavlink_params.yaml`:

```yaml
/**:
  ros__parameters:
    # Serial connection (most common)
    connection_string: '/dev/ttyUSB0:115200'
    
    # OR UDP (uncomment to use instead)
    # connection_string: 'udp:192.168.1.100:14550'
    
    system_id: 1                    # Match your PIX6 SYSID_THISMAV
    component_id: 191               # 191 = Submarine/Rover
    
    heartbeat_interval: 0.1         # 10 Hz heartbeat
    telemetry_rate: 10              # 10 Hz telemetry updates
    
    # Servo channel mapping (PIX6 outputs 1-6 for thrusters)
    servo_channel_mapping: [1, 2, 3, 4, 5, 6]
```

### Important: PIX6 Configuration in QGroundControl

Before running, configure ArduSub parameters:

1. **Baud Rate**: Set SERIAL2_BAUD to 115200
2. **Protocol**: Set SERIAL2_PROTOCOL to MAVLink v2 (38)
3. **Servo Mapping**: Configure which channels map to thrusters:
   - CH1-CH6 typically map to thrusters (confirm with your setup)
4. **Failsafe**: Set appropriate failsafe values (e.g., neutral PWM on connection loss)
5. **System ID**: Note the SYSID_THISMAV parameter (usually 1)

---

## STEP 6: Configure Network (ROS2 Domain ID)

For ROS2 to work across LattePanda and Laptop, they must be on the same network and use the same domain ID.

### On Both Machines:

Edit `~/.bashrc`:

```bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
```

Or set before each session:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0
```

### Verify Network Connectivity:

```bash
# On LattePanda
ifconfig | grep inet

# On Laptop
ping <LattePanda-IP>
ping <Laptop-IP>  # From LattePanda
```

---

## STEP 7: Launch the System

### On LattePanda:

```bash
# Terminal 1: Source setup
cd ~/mate_rov_ws
source install/setup.bash
export ROS_DOMAIN_ID=42

# Start all onboard nodes including MAVLink bridge
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=/dev/ttyUSB0:115200
```

You should see:
```
[INFO] [camera_node]: Camera node started
[INFO] [sensor_node]: Sensor node started at 10.0 Hz
[INFO] [thruster_node]: Thruster node started (disarmed by default)
[INFO] [status_node]: Status node started
[INFO] [mavlink_bridge_node]: MAVLink Bridge initializing on /dev/ttyUSB0:115200
[INFO] [mavlink_bridge_node]: Attempting to connect to MAVLink on /dev/ttyUSB0:115200...
[INFO] [mavlink_bridge_node]: MAVLink connection established!
```

### On Control Laptop:

```bash
# Terminal 1: Source setup
cd ~/mate_rov_ws
source install/setup.bash
export ROS_DOMAIN_ID=42

# Launch control nodes
ros2 launch rov_control control_launch.py
```

---

## STEP 8: Verify Communication

### Check ROS2 Topics:

```bash
# On Laptop (see all available topics)
ros2 topic list

# Should show:
# /rov/camera/image_raw
# /rov/camera/image_compressed
# /rov/sensor_data
# /rov/status
# /rov/thruster_command
```

### Check MAVLink Connection:

```bash
# On LattePanda, in another terminal
ros2 topic echo /rov/status

# Should show updates like:
# armed: false
# leak_detected: false
# mode: "STABILIZE"
# ...
```

### Monitor Thruster Commands:

```bash
# On Laptop, in another terminal
ros2 topic pub /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.5, thruster_front_right: 0.5, thruster_back_left: 0.0, \
    thruster_back_right: 0.0, thruster_vertical_left: 0.0, thruster_vertical_right: 0.0}"

# Check PIX6 receives commands (watch servo outputs)
ros2 topic echo /rov/sensor_data  # Or check autopilot directly
```

---

## STEP 9: Arm/Disarm the Vehicle

The MAVLink bridge handles arm/disarm commands. Currently, you can arm via:

### Option 1: Command-line (temporary)

```bash
# (Add a CLI node for arm/disarm in future updates)
# For now, use QGroundControl or Mission Planner
```

### Option 2: Integrate into gamepad_node

Update `src/rov_control/rov_control/gamepad_node.py` to handle arm/disarm buttons.

---

## Troubleshooting

### Issue: "MAVLink connection failed"

**Causes:**
- USB cable not connected
- Wrong serial port (check with `ls /dev/ttyUSB*`)
- Wrong baud rate
- PIX6 not powered

**Solution:**
```bash
# Check device
ls /dev/ttyUSB*

# Test with minicom
minicom -D /dev/ttyUSB0 -b 115200

# Check dmesg for connection logs
dmesg | tail -20
```

### Issue: "No ROS2 topics visible"

**Causes:**
- ROS_DOMAIN_ID mismatch
- Firewall blocking communication
- Network not properly connected

**Solution:**
```bash
# Verify domain ID
echo $ROS_DOMAIN_ID  # Should be 42

# Check network
ping <other-machine-ip>

# Firewall (Ubuntu)
sudo ufw allow 5353/udp  # ROS2 discovery
```

### Issue: "Heartbeat timeout / Connection lost"

**Causes:**
- Serial line noise or corruption
- PIX6 crashed or rebooted
- Baud rate mismatch

**Solution:**
1. Check cable quality
2. Reduce baud rate (try 57600)
3. Check PIX6 logs in QGroundControl
4. Power cycle PIX6

---

## Next Steps

1. **Integrate arm/disarm into gamepad_node** (see rov_control package)
2. **Extend sensor fusion** - read actual sensor data from PIX6 (depth, attitude)
3. **Add telemetry logging** - record flight data to CSV/ROS2 bag
4. **Implement failsafes** - handle connection loss gracefully
5. **Add diagnostics** - monitor system health (CPU, memory, servo status)

---

## References

- **ArduSub Documentation**: https://ardupilot.org/copter/
- **MAVLink Protocol**: https://mavlink.io/
- **pymavlink**: https://github.com/ArduPilot/pymavlink
- **ROS2 Humble Docs**: https://docs.ros.org/en/humble/
- **PIX6 Autopilot**: https://www.radiolink.com.cn/

---

## Support

For issues, check:
1. Serial connection with `minicom`
2. ROS2 connectivity with `ros2 topic list`
3. Autopilot logs in QGroundControl
4. This guide's troubleshooting section


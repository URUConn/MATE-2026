# ROV Control System - Testing & Diagnostics Guide

**Complete step-by-step guide for verifying your ROV control system is working correctly.**

---

## Table of Contents
1. [Network Connectivity Tests](#network-connectivity-tests)
2. [ROS 2 Communication Tests](#ros-2-communication-tests)
3. [Hardware Connection Tests](#hardware-connection-tests)
4. [Full System Tests](#full-system-tests)
5. [Performance Diagnostics](#performance-diagnostics)
6. [Troubleshooting by Symptom](#troubleshooting-by-symptom)

---

## Network Connectivity Tests

### Test 1: Physical Connectivity
```bash
# On both machines, verify Ethernet is up
ip link show

# Look for your interface (eth0, eno0, etc.) with "UP" status
# Should show something like:
# 2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500

# Verify you have an IP address
ip addr show
# Look for inet line (e.g., inet 192.168.1.100/24)
```

**Expected Result:** Both machines show active ethernet connections with IP addresses

**If FAILED:**
```bash
# Check if interface exists
ip link show

# If missing, bring it up
sudo ip link set eth0 up

# If it needs DHCP
sudo dhclient eth0

# Or manually assign
sudo ip addr add 192.168.1.100/24 dev eth0
```

### Test 2: Ping Test
```bash
# From Laptop, ping LattePanda (replace with actual IP)
ping 192.168.1.100

# From LattePanda, ping Laptop
ping 192.168.1.101

# Should see responses like:
# 64 bytes from 192.168.1.100: icmp_seq=1 ttl=64 time=2.34 ms
```

**Expected Result:** Responses with reasonable latency (<10ms for direct connection)

**If FAILED:**
```bash
# Check routing
route -n
# or
ip route show

# Check firewall
sudo ufw status
# Disable temporarily for testing
sudo ufw disable

# After testing, re-enable
sudo ufw enable
```

### Test 3: Network Configuration Verification
```bash
# Verify ROS_DOMAIN_ID is set on both machines
echo $ROS_DOMAIN_ID
# Should output: 42

# If not set, add to ~/.bashrc
echo 'export ROS_DOMAIN_ID=42' >> ~/.bashrc
source ~/.bashrc
```

**Expected Result:** Both machines output `42`

---

## ROS 2 Communication Tests

### Test 4: Check ROS 2 Installation
```bash
# Verify ROS 2 is installed and available
ros2 --version
# Should show: ROS 2 Humble ...

# Verify packages are available
ros2 pkg list | grep rov_
# Should show:
# rov_control
# rov_msgs
# rov_onboard
```

**Expected Result:** ROS 2 version output and three rov_* packages listed

### Test 5: Topic Discovery Across Network

**On LattePanda**, publish a test message:
```bash
cd ~/mate_rov_ws
source install/setup.bash

ros2 topic pub /network_test std_msgs/String "data: 'hello from LattePanda'" -r 1
# (runs in background, republishes every 1 second)
```

**On Laptop**, in a new terminal:
```bash
cd ~/mate_rov_ws
source install/setup.bash

# List all topics (should include /network_test from LattePanda)
ros2 topic list

# Subscribe to the test topic
ros2 topic echo /network_test
```

**Expected Result:** Laptop receives "hello from LattePanda" messages repeatedly

**If FAILED:**
- Check ROS_DOMAIN_ID on both machines (should be 42)
- Check firewall: `sudo ufw allow in proto udp to 224.0.0.0/4`
- Check network is on same subnet: both IPs should be on same network (192.168.1.x)
- Try Cyclone DDS config (see PIX6_HARDWARE_SETUP.md)

### Test 6: Message Type Availability

On either machine:
```bash
# Check if custom messages are available
ros2 interface show rov_msgs/msg/ThrusterCommand
# Should output the message definition

# Check other message types
ros2 interface show rov_msgs/msg/SensorData
ros2 interface show rov_msgs/msg/RovStatus
```

**Expected Result:** All three message definitions displayed

**If FAILED:**
```bash
# Rebuild packages
cd ~/mate_rov_ws
colcon build --symlink-install

# Source workspace
source install/setup.bash
```

---

## Hardware Connection Tests

### Test 7: PIX6 Serial Port Detection

On LattePanda:
```bash
# Check if PIX6 is detected
lsusb
# Look for: "Silicon Labs CP210x UART Bridge Controller" or similar

# List serial ports
ls -la /dev/ttyACM* /dev/ttyUSB*
# Should show /dev/ttyACM0 or /dev/ttyUSB0

# Check permissions
cat /dev/ttyACM0 < /dev/null
# Should work without "Permission denied"
```

**Expected Result:** PIX6 appears in lsusb and has a corresponding /dev/tty* device

**If FAILED:**
```bash
# Try different USB port
# Verify USB cable is not damaged

# Check system logs
dmesg | tail -20

# Fix permissions if needed
sudo usermod -a -G dialout $USER
newgrp dialout

# Or temporarily
sudo chmod 666 /dev/ttyACM0
```

### Test 8: MAVROS Node Connection

On LattePanda:
```bash
cd ~/mate_rov_ws
source install/setup.bash

# Start just the MAVROS bridge node
ros2 run rov_onboard mavros_bridge_node --ros-args --log-level debug
```

**Expected Output:**
```
[mavros_bridge_node] MAVROS Bridge Node initialized
[mavros_bridge_node] FCU Port: /dev/ttyACM0 @ 115200 baud
[mavros_bridge_node] Waiting for thruster commands...
```

**If FAILED:**
- Check serial port: `ls /dev/ttyACM*`
- Check permissions: `cat /dev/ttyACM0`
- Check baud rate in config: should be 115200
- Verify PIX6 is running ArduSub firmware (check QGroundControl)

### Test 9: QGroundControl Connection

On LattePanda:
```bash
# Download QGroundControl
wget https://d176tv9uyzvq55.cloudfront.net/latest/QGroundControl.AppImage
chmod +x QGroundControl.AppImage

# Run it
./QGroundControl.AppImage &
```

In QGroundControl:
- Should auto-detect and connect to PIX6
- Top-left should show "Connected" status
- Should display attitude, altitude, heading
- Should show battery voltage and status

**Expected Result:** QGroundControl shows "Connected" and displays real-time telemetry

**If FAILED:**
- Try different USB port
- Check Device Manager (Windows) or dmesg (Linux) for USB errors
- Verify ArduSub firmware is flashed (not ArduCopter)
- Check MAVLink parameters: SERIAL0_PROTOCOL should be 2

---

## Full System Tests

### Test 10: Launch All Nodes (LattePanda)

**Terminal 1 on LattePanda:**
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_onboard onboard_launch.py
```

**Expected Output:**
```
[onboard_launch.py] Starting onboard nodes...
[camera_node-1] Camera opened: 1280x720 @ 60fps
[sensor_node-2] Sensor node started at 10.0 Hz
[mavros_bridge_node-3] MAVROS Bridge Node initialized
[status_node-4] Status node started
[thruster_node-5] Thruster node started (disarmed by default)
```

**If any node fails:**
```bash
# Check for import errors
cd ~/mate_rov_ws
python3 -c "from rov_onboard.mavros_bridge_node import *"

# Check ROS 2 package availability
ros2 pkg list | grep -E "image_transport|cv_bridge|mavros"
```

### Test 11: Launch All Nodes (Laptop)

**Terminal 2 on Laptop:**
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_control control_launch.py
```

**Expected Output:**
```
[control_launch.py] Starting control nodes...
[camera_viewer_node-1] Waiting for camera feed...
[gamepad_node-2] ✓ Gamepad connected: Xbox 360 Controller
               or
               ⚠ No gamepad detected. Using keyboard fallback.
[dashboard_node-3] Dashboard started
```

**If gamepad not detected:**
- Plug in Xbox controller and restart gamepad_node
- Or use keyboard fallback (W/A/S/D)
- Check: `python3 -c "import pygame; pygame.init(); print(pygame.joystick.get_count())"`

### Test 12: Verify Topic Publication

**Terminal 3 (any machine):**
```bash
# Monitor thruster commands from gamepad
ros2 topic echo /rov/thruster_command

# In another terminal, press keys (W/A/S/D) or move gamepad sticks
# Should see values change:
# thruster_front_left: 0.5
# thruster_front_right: 0.5
# etc.
```

**Expected Result:** Values change as you move controller/keyboard

### Test 13: Verify RC Override

**Terminal 3 (any machine):**
```bash
# Monitor RC override commands to PIX6
ros2 topic echo /mavros/rc/override

# Press keys on laptop (W/A/S/D)
# Should see RC channel values:
# channels: [1500, 1600, 1500, 1500, 1100, 1500, 1500, 1500]
# values in range 1000-2000 µs
```

**Expected Result:** RC channels 1-4 change with controller input, channel 5 always 1100 (manual mode)

### Test 14: Verify Camera Streaming

**Terminal 3 (any machine):**
```bash
# Check camera frames are publishing
ros2 topic hz /rov/camera/image_compressed

# Should show output every 5 seconds:
# average rate: 60.05 Hz
```

**Expected Result:** Shows framerate around 60 Hz (or whatever you configured)

---

## Performance Diagnostics

### Test 15: Network Latency

```bash
# Measure round-trip time between machines
ping -c 10 192.168.1.100 | tail -1
# Look for "avg" value - should be <10ms for local network

# Measure ROS 2 topic latency
# (advanced - requires specialized tools)
```

### Test 16: CPU Usage

**On LattePanda:**
```bash
# Monitor CPU while running nodes
top

# Look for:
# - ROS 2 nodes using 5-15% each
# - Total CPU <50% available
# - Memory <500MB
```

**If HIGH usage:**
- Reduce camera resolution
- Reduce publish rates in config files
- Check for infinite loops in node code

### Test 17: Thruster Command Rate

```bash
# Measure publish rate of thruster commands
ros2 topic hz /rov/thruster_command

# Should show approximately 50 Hz:
# average rate: 50.01 Hz
```

**If SLOWER:**
- Check CPU usage on laptop (might be busy)
- Check network latency (too much delay)
- Increase `publish_rate` in `control_params.yaml`

### Test 18: DDS Statistics

```bash
# View DDS discovery information
# (requires Cyclone DDS tools)

# Or check node connections
ros2 node info /gamepad_node
# Should show it's publishing to /rov/thruster_command
```

---

## Troubleshooting by Symptom

### Symptom: "No topics appear on other machine"

**Diagnosis:**
```bash
# Check ROS_DOMAIN_ID
echo $ROS_DOMAIN_ID  # Both machines should be 42

# Check network connectivity
ping 192.168.1.100

# Check DDS is working
ros2 daemon status
```

**Solutions (in order):**
1. Set ROS_DOMAIN_ID=42 on both machines
2. Verify ping works between machines
3. Disable firewall temporarily: `sudo ufw disable`
4. Check if on same subnet: `ip addr show`
5. Switch to Cyclone DDS with unicast:
   ```bash
   sudo apt install -y ros-humble-rmw-cyclonedds-cpp
   export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
   export CYCLONEDDS_URI=file:///home/$USER/cyclonedds.xml
   ```

### Symptom: "Camera works, but thruster commands don't publish"

**Diagnosis:**
```bash
# Check if gamepad_node is running
ros2 node list | grep gamepad

# Check if topic exists
ros2 topic list | grep thruster_command

# Check for errors
ros2 run rov_control gamepad_node --ros-args --log-level debug
```

**Solutions:**
1. Verify gamepad is connected: `lsusb | grep -i xbox`
2. Install pygame: `pip3 install pygame`
3. Check for import errors: `python3 -c "import pygame"`
4. Use keyboard fallback (automatic if gamepad missing)

### Symptom: "PIX6 not responding to RC commands"

**Diagnosis:**
```bash
# Check serial connection
ls /dev/ttyACM*
cat /dev/ttyACM0 < /dev/null  # Check permissions

# Verify MAVROS bridge is running
ros2 node list | grep mavros_bridge

# Check RC override topic
ros2 topic echo /mavros/rc/override
```

**Solutions:**
1. Verify serial port in config: `fcu_port: "/dev/ttyACM0"`
2. Check baud rate: should be 115200
3. Verify ArduSub firmware flashed (not ArduCopter)
4. Check SERIAL0_PROTOCOL in QGroundControl = 2 (MAVLink)
5. Try different USB port or cable

### Symptom: "Thrusters move wrong direction"

**Diagnosis:**
```bash
# Observe which thrusters move with W key
# Note which thrusters are reversed
# E.g., left thrusters move backward when they should move forward
```

**Solution:**
In QGroundControl, Vehicle Setup → Parameters:
```
MOT_1_DIRECTION = -1  # Reverse front-left thruster
MOT_2_DIRECTION = -1  # Reverse front-right thruster
# etc for others
```

### Symptom: "Very slow network response"

**Diagnosis:**
```bash
# Check network latency
ping -c 10 192.168.1.100

# Check for dropped packets
ping -c 100 192.168.1.100 | grep loss

# Check topic rate
ros2 topic hz /rov/thruster_command
```

**Solutions:**
1. Use direct Ethernet (not WiFi)
2. Reduce camera resolution: `frame_width: 640, frame_height: 480`
3. Reduce publish rate: `publish_rate: 30` (from 50)
4. Enable compression: `publish_compressed: true`
5. Reduce JPEG quality: `jpeg_quality: 20` (from higher)

---

## Complete System Test Procedure

**Run this after setup to verify everything works:**

```bash
# Terminal 1: LattePanda
ssh user@192.168.1.100
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_onboard onboard_launch.py

# Terminal 2: Laptop
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_control control_launch.py

# Terminal 3: Laptop - Monitor commands
ros2 topic hz /rov/thruster_command

# Terminal 4: Laptop - Watch thruster values
ros2 topic echo /rov/thruster_command

# Terminal 5: LattePanda - Watch RC override
ros2 topic echo /mavros/rc/override

# Action: Press W on laptop keyboard
# Expected: Terminal 4 shows forward values
# Expected: Terminal 5 shows pitch=2000 µs (full forward)

# Action: Press D on laptop (strafe right)
# Expected: Terminal 4 shows positive strafe values
# Expected: Terminal 5 shows roll=2000 µs (roll right)

# Action: Press Space on laptop (stop)
# Expected: All values go to zero/1500 µs

# Expected: All framerate monitors show ~50 Hz
```

**If all above works, your ROV is ready for hardware integration!**

---

## Performance Benchmarks

| Metric | Expected | Acceptable | Problem |
|--------|----------|-----------|---------|
| Network latency (ping) | <5 ms | <10 ms | >20 ms |
| ROS topic rate | 50 Hz | 40+ Hz | <30 Hz |
| CPU usage per node | 5-10% | <20% | >30% |
| RAM usage | <500 MB | <1 GB | >2 GB |
| Camera framerate | 60 fps | 30+ fps | <20 fps |
| RC command lag | <50 ms | <100 ms | >200 ms |

---

## Next: Hardware Integration

Once all tests pass:

1. ✓ Connect thrusters to ESCs on PIX6
2. ✓ Verify thruster polarity with manual PWM test
3. ✓ Connect battery (with main power switch)
4. ✓ Perform tank test in shallow water
5. ✓ Tune motor mixing matrix in ArduSub
6. ✓ Monitor battery voltage and shutdown safely

See **PIX6_HARDWARE_SETUP.md** for detailed procedures.


# MATE-2026 MAVLink Integration - Verification Checklist

## Pre-Installation Verification

### Hardware Check
- [ ] LattePanda powered and running Ubuntu 22.04
- [ ] Radiolink PIX6 autopilot available
- [ ] USB-to-Serial cable (FTDI or similar) available
- [ ] Network cable or WiFi connectivity between LattePanda and Control Laptop
- [ ] USB camera connected to LattePanda (optional, for testing)

### Software Prerequisites
- [ ] Ubuntu 22.04 LTS (or compatible)
- [ ] Python 3.8+ installed
- [ ] git installed
- [ ] Internet connection for package downloads

---

## Installation Verification

### Step 1: Basic System Setup
- [ ] Ubuntu 22.04 running on both LattePanda and Laptop
- [ ] Network connectivity verified (ping between machines)
- [ ] ROS2 Humble installed and working
- [ ] Colcon build tool installed

Run:
```bash
ros2 --version  # Should show ROS2 Humble
```

### Step 2: Repository and Build
- [ ] Repository cloned to ~/mate_rov_ws/src/
- [ ] Workspace built successfully
- [ ] No build errors in colcon output
- [ ] install/ and build/ directories created

Run:
```bash
cd ~/mate_rov_ws && colcon build --symlink-install
# Should complete with "Summary" showing all packages built
```

### Step 3: Python Dependencies
- [ ] pymavlink installed
- [ ] dronekit installed
- [ ] pyserial installed
- [ ] opencv-python installed

Run:
```bash
python3 -c "import pymavlink, dronekit, cv2, serial; print('All packages OK')"
```

### Step 4: ROS2 Configuration
- [ ] ROS_DOMAIN_ID=42 set on both machines
- [ ] ROS_LOCALHOST_ONLY=0 set (for network communication)
- [ ] ~/.bashrc updated with sourcing commands

Run:
```bash
echo $ROS_DOMAIN_ID  # Should be 42
source ~/mate_rov_ws/install/setup.bash
ros2 node list  # Should work
```

---

## Hardware Configuration Verification

### PIX6 Physical Connection
- [ ] USB cable connected to LattePanda
- [ ] USB device appears in /dev/ttyUSB*
- [ ] Minicom can connect to serial port at 115200 baud

Run:
```bash
ls /dev/ttyUSB*
minicom -D /dev/ttyUSB0 -b 115200  # Press Ctrl+A then X to exit
dmesg | grep ttyUSB  # Check kernel logs
```

### PIX6 Firmware & Configuration
- [ ] ArduSub firmware loaded on PIX6
- [ ] QGroundControl installed on Control Laptop
- [ ] QGroundControl can connect to PIX6
- [ ] SERIAL2_PROTOCOL set to 38 (MAVLink v2)
- [ ] SERIAL2_BAUD set to 115200
- [ ] SYSID_THISMAV noted (usually 1)
- [ ] Servo channels 1-6 configured for thrusters

QGC Checklist:
```
✓ Vehicle → Parameters → SERIAL2_PROTOCOL = 38
✓ Vehicle → Parameters → SERIAL2_BAUD = 115200
✓ Vehicle → Parameters → SYSID_THISMAV = 1
✓ Vehicle → Parameters → FRAME_CLASS = 2 (Submarine)
✓ Vehicle → Radio → Calibrate channels (if needed)
```

---

## Software Verification

### ROS2 Network Communication
- [ ] DDS discovery working between machines
- [ ] ROS_DOMAIN_ID matches on both machines
- [ ] Network firewall allows UDP 5353 and 7400-7409

Run on Laptop:
```bash
ros2 topic pub /test std_msgs/String "data: hello" &
# Then on LattePanda:
ros2 topic echo /test
# Should see "hello"
```

### MAVLink Bridge Startup
- [ ] rov_mavlink package built successfully
- [ ] mavlink_bridge_node executable exists

Run:
```bash
ros2 run rov_mavlink mavlink_bridge_node --help
which mavlink_bridge_node
```

### Launch File Validation
- [ ] onboard_launch.py has no syntax errors
- [ ] mavlink_launch.py has no syntax errors
- [ ] control_launch.py works independently

Run:
```bash
ros2 launch rov_onboard onboard_launch.py --dry-run
ros2 launch rov_mavlink mavlink_launch.py --dry-run
ros2 launch rov_control control_launch.py --dry-run
```

---

## System Launch Tests

### Test 1: MAVLink Bridge Only (LattePanda)

```bash
# Terminal on LattePanda:
cd ~/mate_rov_ws
source install/setup.bash
export ROS_DOMAIN_ID=42

ros2 run rov_mavlink mavlink_bridge_node
```

Expected Output:
```
[INFO] [mavlink_bridge_node]: MAVLink Bridge initializing on /dev/ttyUSB0:115200
[INFO] [mavlink_bridge_node]: Attempting to connect to MAVLink on /dev/ttyUSB0:115200...
[INFO] [mavlink_bridge_node]: MAVLink connection established!
```

Verification:
- [ ] No exception or error
- [ ] "MAVLink connection established!" message appears
- [ ] No continuous error spam

### Test 2: Full Onboard System (LattePanda)

```bash
# Terminal on LattePanda:
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=/dev/ttyUSB0:115200
```

Expected Output:
```
[camera_node-1] INFO: Camera opened: 1280x720 @ 60fps
[sensor_node-2] INFO: Sensor node started at 10.0 Hz
[thruster_node-3] INFO: Thruster node started (disarmed by default)
[status_node-4] INFO: Status node started
[mavlink_bridge_node-5] INFO: MAVLink connection established!
```

Verification:
- [ ] All 5 nodes start successfully
- [ ] No fatal errors
- [ ] MAVLink connection established
- [ ] CPU/memory reasonable

### Test 3: Control Laptop System

```bash
# Terminal on Control Laptop:
ros2 launch rov_control control_launch.py
```

Expected Output:
```
[gamepad_node-1] INFO: Gamepad node started
[camera_viewer_node-2] INFO: Waiting for camera images...
[dashboard_node-3] INFO: Dashboard node started
```

Verification:
- [ ] All control nodes start
- [ ] No fatal errors
- [ ] Camera viewer window appears (if camera available)

---

## Communication Verification

### Test 4: ROS2 Topics Visible

On Laptop (should see topics from LattePanda):
```bash
ros2 topic list
```

Should include:
- [ ] /rov/camera/image_raw
- [ ] /rov/camera/image_compressed
- [ ] /rov/sensor_data
- [ ] /rov/status
- [ ] /rov/thruster_command

### Test 5: Monitor Telemetry

On Laptop:
```bash
ros2 topic echo /rov/status
```

Should update every ~1 second with:
```
armed: False
leak_detected: False
mode: "STABILIZE"
cpu_temperature: 35.5
uptime_seconds: 120.5
```

- [ ] Updates consistently
- [ ] Values reasonable
- [ ] No connection timeout

### Test 6: Camera Stream

On Laptop:
```bash
ros2 topic hz /rov/camera/image_compressed
```

Should show:
```
average rate: 30.05 Hz
min: 33.22ms max: 33.45ms std dev: 0.08ms
```

- [ ] Framerate ~30+ Hz
- [ ] Consistent timing

### Test 7: Thruster Command Publishing

On Laptop, send a test command:
```bash
ros2 topic pub -1 /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.5, thruster_front_right: 0.5, thruster_back_left: 0.0, thruster_back_right: 0.0, thruster_vertical_left: 0.0, thruster_vertical_right: 0.0}"
```

Check on LattePanda:
```bash
ros2 topic echo /rov/thruster_command
```

- [ ] Command received on LattePanda
- [ ] No warnings in mavlink_bridge_node
- [ ] PIX6 servos respond (check in QGC if available)

---

## Advanced Verification

### Test 8: Network Latency

```bash
# LattePanda: publish timestamps
ros2 run demo_nodes_cpp talker &

# Laptop: check latency
ros2 run rqt_graph rqt_graph
```

- [ ] Latency acceptable (<100ms)
- [ ] No packet loss
- [ ] Connection stable

### Test 9: System Stability (30-minute test)

Run full system for 30 minutes and monitor:
```bash
# LattePanda:
ros2 launch rov_onboard onboard_launch.py > /tmp/onboard.log 2>&1 &

# Laptop:
ros2 launch rov_control control_launch.py > /tmp/control.log 2>&1 &

# Monitor topics
watch 'ros2 topic hz /rov/status'
```

Check after 30 minutes:
- [ ] No crashes in /tmp/*.log
- [ ] Topic rates stable
- [ ] Memory usage not increasing
- [ ] CPU usage reasonable

### Test 10: Error Recovery

Kill MAVLink bridge while system running:
```bash
# Kill on LattePanda
pkill mavlink_bridge_node

# Wait 5 seconds, should reconnect
```

Verify:
- [ ] System logs reconnection attempt
- [ ] Reconnects within 30 seconds
- [ ] Other nodes unaffected

---

## Performance Benchmarks

### Expected Performance
| Metric | Expected | Measured |
|--------|----------|----------|
| Heartbeat Rate | 10 Hz | ___ Hz |
| Telemetry Rate | 10 Hz | ___ Hz |
| Camera FPS | 30+ FPS | ___ FPS |
| MAVLink Latency | <50ms | ___ ms |
| ROS2 Network Latency | <50ms | ___ ms |
| CPU Usage (LattePanda) | <50% | ___ % |
| Memory Usage (LattePanda) | <500MB | ___ MB |
| Connection Stability | 99%+ | ___ % |

---

## Documentation Verification

- [ ] README.md readable and accurate
- [ ] MAVLINK_SETUP.md complete and tested
- [ ] INTEGRATION_SUMMARY.md reflects actual implementation
- [ ] QUICK_REFERENCE.md has correct commands
- [ ] ARCHITECTURE_DIAGRAM.md accurate
- [ ] All setup steps are reproducible

---

## Final Checklist

### Pre-Deployment
- [ ] All tests above passed
- [ ] No critical warnings in logs
- [ ] Hardware connections secure
- [ ] System performance acceptable
- [ ] Documentation reviewed

### Deployment Ready
- [ ] All nodes start cleanly
- [ ] Telemetry flowing correctly
- [ ] Network communication stable
- [ ] MAVLink bridge operational
- [ ] Ready for integration testing with thrusters

### Sign-Off
- [ ] Tested by: ___________________
- [ ] Date: ___________________
- [ ] Notes: ___________________

---

## Troubleshooting Reference

| Issue | Test | Solution |
|-------|------|----------|
| MAVLink connection fails | Test 1 | Check USB cable, port, baud rate |
| No ROS2 topics | Test 4 | Check ROS_DOMAIN_ID, firewall, network |
| Low camera FPS | Test 6 | Reduce resolution, lower JPEG quality |
| Latency too high | Test 8 | Check network, reduce publish rate |
| System unstable | Test 9 | Check logs, CPU/memory, resource conflicts |
| Cannot recover after crash | Test 10 | Check watchdog timeout, reconnect logic |

---

## Additional Testing (Optional)

### Extended Hardware Test
```bash
# Test all 6 thrusters individually
for i in {1..6}; do
  ros2 topic pub -1 /rov/thruster_command rov_msgs/ThrusterCommand \
    "{thruster_front_left: $([ $i -eq 1 ] && echo 1.0 || echo 0.0), \
      thruster_front_right: $([ $i -eq 2 ] && echo 1.0 || echo 0.0), \
      thruster_back_left: $([ $i -eq 3 ] && echo 1.0 || echo 0.0), \
      thruster_back_right: $([ $i -eq 4 ] && echo 1.0 || echo 0.0), \
      thruster_vertical_left: $([ $i -eq 5 ] && echo 1.0 || echo 0.0), \
      thruster_vertical_right: $([ $i -eq 6 ] && echo 1.0 || echo 0.0)}"
  sleep 2
done
```

### Stress Test
```bash
# Publish max thrust continuously for 1 minute
timeout 60 ros2 topic pub /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 1.0, thruster_front_right: 1.0, thruster_back_left: 1.0, \
    thruster_back_right: 1.0, thruster_vertical_left: 1.0, thruster_vertical_right: 1.0}"
```

---

**Complete this checklist before deploying to field!**


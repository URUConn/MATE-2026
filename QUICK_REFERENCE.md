# MATE-2026 Quick Reference

## Environment Setup (Run on Every Terminal)

### LattePanda or Laptop:
```bash
cd ~/mate_rov_ws
source install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=0  # Allow network communication
```

Or add to `~/.bashrc` (permanent):
```bash
echo 'cd ~/mate_rov_ws && source install/setup.bash' >> ~/.bashrc
echo 'export ROS_DOMAIN_ID=42' >> ~/.bashrc
echo 'export ROS_LOCALHOST_ONLY=0' >> ~/.bashrc
source ~/.bashrc
```

---

## Launch Commands

### On LattePanda (All Onboard Services + MAVLink):
```bash
ros2 launch rov_onboard onboard_launch.py
```

With custom MAVLink port:
```bash
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=/dev/ttyUSB0:115200
```

Or for UDP:
```bash
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=udp:192.168.1.100:14550
```

### On Control Laptop (All Control Services):
```bash
ros2 launch rov_control control_launch.py
```

### Launch Only Camera (for testing):
```bash
ros2 launch rov_onboard camera_only_launch.py
```

### View Camera on Laptop Only:
```bash
ros2 launch rov_control camera_viewer_only_launch.py
```

### Launch Only MAVLink Bridge:
```bash
ros2 launch rov_mavlink mavlink_launch.py connection_string:=/dev/ttyUSB0:115200
```

---

## Monitoring & Debugging

### List All Running Nodes:
```bash
ros2 node list
```

### List All Active Topics:
```bash
ros2 topic list
```

### Echo a Topic (view messages):
```bash
ros2 topic echo /rov/thruster_command        # Thruster commands from gamepad
ros2 topic echo /rov/camera/image_compressed # Camera feed (compressed)
ros2 topic echo /rov/sensor_data             # Depth, IMU, battery
ros2 topic echo /rov/status                  # Armed, leak detection, mode
```

### Check Topic Rate (Hz):
```bash
ros2 topic hz /rov/camera/image_compressed
ros2 topic hz /rov/sensor_data
ros2 topic hz /rov/status
```

### Get Topic Info (message type, publishers, subscribers):
```bash
ros2 topic info /rov/thruster_command
```

### View ROS2 Graph (node/topic connections):
```bash
ros2 run rqt_graph rqt_graph
```

---

## Publishing Test Messages

### Publish Thruster Command (via CLI):
```bash
ros2 topic pub /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.5, thruster_front_right: 0.5, \
    thruster_back_left: 0.0, thruster_back_right: 0.0, \
    thruster_vertical_left: 0.0, thruster_vertical_right: 0.0}"
```

### Publish Once and Exit:
```bash
ros2 topic pub -1 /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.5, thruster_front_right: 0.5, \
    thruster_back_left: 0.0, thruster_back_right: 0.0, \
    thruster_vertical_left: 0.0, thruster_vertical_right: 0.0}"
```

### Publish at Fixed Rate (e.g., 10 Hz):
```bash
ros2 topic pub -r 10 /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.3, thruster_front_right: 0.3, ...}"
```

---

## Build Commands

### Build Entire Workspace:
```bash
cd ~/mate_rov_ws
colcon build --symlink-install
```

### Build Single Package:
```bash
colcon build --packages-select rov_mavlink
```

### Build Without Symlink (full rebuild):
```bash
colcon build
```

### Clean Build:
```bash
rm -rf build install log
colcon build
```

---

## Hardware Checks

### List USB Devices:
```bash
ls /dev/ttyUSB*
```

### Test Serial Connection:
```bash
minicom -D /dev/ttyUSB0 -b 115200
# Press Ctrl+A then X to exit
```

### Get Serial Device Info:
```bash
dmesg | grep ttyUSB
lsusb
```

### Check LattePanda IP:
```bash
hostname -I
# or
ip addr show
```

### Ping Control Laptop:
```bash
ping 192.168.1.101  # Replace with actual laptop IP
```

---

## Python Dependency Management

### Install All Python Dependencies:
```bash
pip install -r requirements.txt
```

### Install Specific Package:
```bash
pip install pymavlink dronekit pyserial
```

### Check Installed Packages:
```bash
pip list | grep mavlink
pip list | grep dronekit
```

### Update pymavlink:
```bash
pip install --upgrade pymavlink
```

---

## Logs & Troubleshooting

### View Node Logs (real-time):
```bash
ros2 launch rov_onboard onboard_launch.py --log-level DEBUG
```

### Check System Resources:
```bash
top          # CPU/Memory usage
htop         # More detailed
free -h      # Memory only
df -h        # Disk space
```

### ROS2 Daemon Status:
```bash
ros2 daemon status
ros2 daemon stop
ros2 daemon start
```

### Check if Node Crashed:
```bash
ros2 node info camera_node
ros2 node info mavlink_bridge_node
```

---

## Useful Aliases (add to ~/.bashrc)

```bash
alias mate_ws='cd ~/mate_rov_ws && source install/setup.bash'
alias mate_build='cd ~/mate_rov_ws && colcon build --symlink-install'
alias mate_onboard='ros2 launch rov_onboard onboard_launch.py'
alias mate_control='ros2 launch rov_control control_launch.py'
alias mate_topics='ros2 topic list'
alias mate_nodes='ros2 node list'
alias mate_echo_status='ros2 topic echo /rov/status'
alias mate_echo_sensors='ros2 topic echo /rov/sensor_data'
```

Then use:
```bash
mate_ws
mate_onboard
```

---

## Common Issues & Quick Fixes

| Problem | Command | Fix |
|---------|---------|-----|
| Can't find /dev/ttyUSB0 | `ls /dev/ttyUSB*` | Check USB cable, power on PIX6 |
| Connection refused | `ping 192.168.1.100` | Check network, check IPs |
| No topics visible | `export ROS_DOMAIN_ID=42` | Set domain ID on both machines |
| Low framerate | Edit `onboard_params.yaml` | Reduce resolution, JPEG quality |
| Node won't start | `ros2 node info nodename` | Check dependencies, rebuild |

---

## Documentation Files

- **INTEGRATION_SUMMARY.md** - What was built and why
- **MAVLINK_SETUP.md** - Detailed setup and configuration
- **README.md** - Project overview and basic usage
- **requirements.txt** - Python dependencies
- **install.sh** - Automated setup script

---

## Network Troubleshooting

### Verify Both Machines on Same Network:
```bash
# LattePanda
ifconfig

# Laptop
ifconfig

# Should see similar IP ranges (e.g., 192.168.1.x)
```

### Check Firewall (Ubuntu):
```bash
sudo ufw status
sudo ufw allow 5353/udp  # ROS2 discovery
sudo ufw allow 7400:7409/udp  # ROS2 communication
```

### Test Connectivity:
```bash
ping <other-machine-ip>
nmap -p 5353 <other-machine-ip>  # ROS2 discovery port
```

---

For more detailed info, see:
- **MAVLINK_SETUP.md** - Hardware, configuration, and detailed troubleshooting
- **INTEGRATION_SUMMARY.md** - Architecture and file structure


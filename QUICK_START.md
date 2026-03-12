# Quick Start Guide - MATE 2026 ROV Control System

**TL;DR for Impatient Users:** Jump to [Quick Setup](#quick-setup-5-minutes) or [Full System Test](#full-system-test)

---

## System Overview

Your ROV system consists of:
- **Laptop (Jetson Nano)** - Running Xbox/Keyboard controller input
- **LattePanda** - Running onboard sensors, camera, and MAVROS bridge
- **PIX6 Flight Controller** - Running ArduSub firmware, connected via USB
- **Network** - Ethernet LAN connecting laptop and LattePanda via ROS 2 DDS

**Data Flow:**
```
Xbox Controller (Laptop)
         ↓
gamepad_node (laptop)
         ↓
/rov/thruster_command (ROS 2 topic)
         ↓
mavros_bridge_node (LattePanda)
         ↓
/mavros/rc/override (RC PWM commands)
         ↓
PIX6 Flight Controller (MAVLink)
         ↓
Thrusters via ArduSub
```

---

## Prerequisites

- Both machines on same LAN (Ethernet)
- Ubuntu 22.04 with ROS 2 Humble
- Xbox controller connected to laptop (or use keyboard)
- PIX6 with ArduSub firmware flashed
- `mate_rov_ws` workspace with all packages built

---

## Quick Setup (5 Minutes)

### Step 1: Install Dependencies (Both Machines)

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install ROS 2 packages
sudo apt install -y \
    ros-humble-mavros \
    ros-humble-mavros-msgs \
    python3-pip \
    python3-opencv

# Python packages
pip3 install pygame
```

### Step 2: Flash PIX6 with ArduSub (if not already done)

1. Download QGroundControl: `./QGroundControl.AppImage`
2. Connect PIX6 via USB to LattePanda
3. In QGroundControl: **Vehicle Setup → Firmware → ArduSub**
4. Wait for flash (2-3 minutes)

### Step 3: Configure Serial Port

Find your PIX6 serial port:
```bash
ls /dev/ttyACM* /dev/ttyUSB*
# Typically /dev/ttyACM0
```

Edit `src/rov_onboard/config/onboard_params.yaml`:
```yaml
mavros_bridge_node:
  ros__parameters:
    fcu_port: "/dev/ttyACM0"  # Update if different
    armed: false
```

### Step 4: Build Workspace

```bash
cd ~/mate_rov_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### Step 5: Launch System

**Terminal 1 (LattePanda):**
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_onboard onboard_launch.py
```

**Terminal 2 (Laptop):**
```bash
cd ~/mate_rov_ws
source install/setup.bash
ros2 launch rov_control control_launch.py
```

**Expected Output:**
```
✓ Gamepad connected: Xbox 360 Controller
  or
⚠ No gamepad detected. Using keyboard fallback.
```

---

## Full System Test

### Test 1: Check ROS Connection Between Machines

On **Laptop**:
```bash
ros2 topic list
# Should show:
# /rov/camera/image_raw
# /rov/sensor_data
# /rov/status
# /rov/thruster_command (you'll publish to this)
```

### Test 2: Monitor Thruster Commands

On **LattePanda**:
```bash
ros2 topic echo /rov/thruster_command
```

On **Laptop**, move the Xbox controller or press keys:
```
W/A/S/D or Left/Right/Up/Down arrows
```

You should see values change in the thruster command output.

### Test 3: Check MAVROS RC Override

On **LattePanda**:
```bash
ros2 topic echo /mavros/rc/override
```

Should show RC channel values updating (1000-2000 µs) as you move the controller.

### Test 4: Verify PIX6 Connection

```bash
# Check if PIX6 is detected
lsusb | grep -i "silicon labs\|cp210x"

# Verify QGroundControl shows "Armed" status
# (in QGroundControl, check top-right corner)
```

---

## Controller Mapping

### Xbox Controller
| Action | Control |
|--------|---------|
| Forward/Backward | Left Stick Y |
| Strafe Left/Right | Left Stick X |
| Rotate (Yaw) | Right Stick X |
| Vertical Up/Down | Right/Left Trigger |

### Keyboard Fallback
| Action | Key |
|--------|-----|
| Forward | `W` |
| Backward | `S` |
| Strafe Left | `A` |
| Strafe Right | `D` |
| Vertical Up | `↑` (Up Arrow) |
| Vertical Down | `↓` (Down Arrow) |
| Rotate Left | `←` (Left Arrow) |
| Rotate Right | `→` (Right Arrow) |
| Stop All | `Space` |

---

## Arm the ROV (⚠️ Safety First)

**ONLY DO THIS WHEN:**
1. ✓ All thrusters installed and balanced
2. ✓ Propellers attached
3. ✓ ESCs calibrated
4. ✓ System tested in test tank or air
5. ✓ Safety checks complete

**To Arm:**
1. Set `armed: true` in `src/rov_onboard/config/onboard_params.yaml`
2. Rebuild: `colcon build --symlink-install`
3. Restart nodes: `ros2 launch rov_onboard onboard_launch.py`
4. Monitor in QGroundControl

---

## Troubleshooting

### No Thruster Commands Received
```bash
# Check gamepad/keyboard is working
ps aux | grep gamepad_node

# Test manually publishing (8 thrusters: 4 horizontal + 4 vertical)
ros2 topic pub /rov/thruster_command rov_msgs/ThrusterCommand \
  "{thruster_front_left: 0.5, thruster_front_right: 0.5, \
    thruster_back_left: 0.5, thruster_back_right: 0.5, \
    thruster_vertical_front_left: 0.5, thruster_vertical_front_right: 0.5, \
    thruster_vertical_back_left: 0.5, thruster_vertical_back_right: 0.5}"
```

### Xbox Controller Not Detected
```bash
# Install this tool
sudo apt install -y python3-pygame-sdl2

# Test if detected
python3 -c "import pygame; pygame.init(); print(pygame.joystick.get_count())"

# If 0, try another USB port
# Or use keyboard fallback (automatic if not found)
```

### PIX6 Connection Failed
```bash
# Check serial port
ls -la /dev/ttyACM*

# Fix permissions
sudo usermod -a -G dialout $USER
newgrp dialout

# Restart MAVROS bridge node
ros2 launch rov_onboard onboard_launch.py
```

### Nodes Won't Start
```bash
# Check for Python errors
colcon build --symlink-install --verbose

# Reinstall dependencies
rosdep install --from-paths ~/mate_rov_ws/src --ignore-src -r -y

# Source workspace
source ~/mate_rov_ws/install/setup.bash
```

---

## Safe Testing Procedure

### Tank Testing (Recommended)
1. **Start in air** - No water (test thrust response)
2. **Shallow water** - 30 cm depth
3. **Increase depth** gradually
4. **Monitor battery** - Stop at 3.3V per cell
5. **Watch thrusters** - No cavitation or imbalance

### Thrust Scaling
If thrusters too powerful, reduce in config:
```yaml
mavros_bridge_node:
  ros__parameters:
    thrust_scaling: 0.5  # 0.5 = half power, 0.25 = quarter power
```

Then rebuild: `colcon build --symlink-install`

---

## Monitoring & Diagnostics

### View All ROS 2 Topics
```bash
ros2 topic list
```

### Monitor Specific Topic
```bash
ros2 topic echo /rov/thruster_command
```

### Check Node Status
```bash
ros2 node list
ros2 node info /gamepad_node
```

### Enable Debug Logging
Edit your node's ROS 2 launch file and add:
```python
Node(
    ...
    arguments=['--ros-args', '--log-level', 'debug']
)
```

### View PIX6 Logs via QGroundControl
- Connect via USB
- Go to **Analyze → Logs**
- Download and view sensor readings

---

## Next Steps

### Enhancements
- [ ] Add telemetry feedback (depth, attitude, battery)
- [ ] Implement depth hold mode
- [ ] Add video recording
- [ ] Implement failsafe return-to-surface
- [ ] Add leak detector integration
- [ ] Tune thruster mixing for your specific ROV frame

### Documentation
- See `INSTALLATION_GUIDE.md` for detailed setup
- Check ArduSub docs: https://ardupilot.org/ardusub/
- MAVROS docs: https://docs.px4.io/main/en/ros/

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Thrusters moving backwards | Reverse polarity in ArduSub motor matrix |
| ROV tilts to one side | Recalibrate compass or balance thrusters |
| No video on laptop | Check `/rov/camera/image_raw` topic is publishing |
| Slow response | Increase `publish_rate` in config |
| High latency | Use Ethernet instead of WiFi |
| PIX6 won't arm | Check failsafes in QGroundControl |

---

## Support Resources

- **ArduSub Documentation**: https://ardupilot.org/ardusub/
- **MAVROS Package**: https://docs.px4.io/main/en/ros/
- **ROS 2 Humble**: https://docs.ros.org/en/humble/
- **QGroundControl**: http://qgroundcontrol.com/

---

**Last Updated:** March 12, 2026
**Status:** Ready for deployment ✓


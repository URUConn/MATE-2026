# MATE-2026 ROV Documentation Index

## 📚 Documentation Guide

### Quick Start (Start Here!)
1. **[README.md](README.md)** - Project overview and basic usage
2. **[MAVLINK_SETUP.md](MAVLINK_SETUP.md)** - Complete step-by-step setup guide ⭐ **START HERE**
3. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference card for daily use

### Understanding the System
4. **[ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)** - System diagrams and data flows
5. **[INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md)** - What was built and why

### Installation & Verification
6. **[install.sh](install.sh)** - Automated installation script
7. **[requirements.txt](requirements.txt)** - Python dependencies
8. **[VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)** - Pre-deployment testing checklist

---

## 🎯 By Use Case

### "I just received the project and want to set it up"
→ Follow **MAVLINK_SETUP.md** step-by-step

### "I need to know what was built"
→ Read **INTEGRATION_SUMMARY.md** (explains architecture and all changes)

### "I need to launch the system"
→ Use commands from **QUICK_REFERENCE.md** → Launch Commands section

### "I need to debug why something isn't working"
→ Check **QUICK_REFERENCE.md** → Troubleshooting or **MAVLINK_SETUP.md** → Troubleshooting

### "I want to understand the system architecture"
→ Read **ARCHITECTURE_DIAGRAM.md** for detailed diagrams and data flows

### "I need to verify everything is working before deployment"
→ Follow **VERIFICATION_CHECKLIST.md** point-by-point

### "I'm new to ROS2 or MAVLink"
→ Start with **README.md**, then **ARCHITECTURE_DIAGRAM.md**, then **MAVLINK_SETUP.md**

---

## 📁 File Structure

### Configuration Files
- `src/rov_mavlink/config/mavlink_params.yaml` - MAVLink connection settings
- `src/rov_onboard/config/onboard_params.yaml` - Onboard sensor/camera settings
- `src/rov_control/config/control_params.yaml` - Control station settings

### Launch Files
- `src/rov_onboard/launch/onboard_launch.py` - Start all onboard services (camera, sensors, thrusters, MAVLink bridge)
- `src/rov_mavlink/launch/mavlink_launch.py` - Start only MAVLink bridge
- `src/rov_control/launch/control_launch.py` - Start all control station services

### Source Code (Key Files)
- `src/rov_mavlink/rov_mavlink/mavlink_bridge_node.py` - Main MAVLink bridge (400+ lines)
- `src/rov_onboard/rov_onboard/thruster_node.py` - Thruster command handler
- `src/rov_control/rov_control/gamepad_node.py` - Gamepad input handler

---

## 🚀 Quick Installation

```bash
# 1. Clone and setup
mkdir -p ~/mate_rov_ws/src
cd ~/mate_rov_ws
git clone <repo-url> src/

# 2. Run automated installation
bash src/install.sh

# 3. Source setup
source install/setup.bash
export ROS_DOMAIN_ID=42

# 4. On LattePanda: Launch onboard system
ros2 launch rov_onboard onboard_launch.py mavlink_connection:=/dev/ttyUSB0:115200

# 5. On Control Laptop: Launch control station
ros2 launch rov_control control_launch.py

# 6. Verify telemetry is flowing
ros2 topic echo /rov/status
```

---

## 💾 New Files Created

### Documentation (5 files)
- ✅ `MAVLINK_SETUP.md` (350+ lines) - Comprehensive setup guide
- ✅ `INTEGRATION_SUMMARY.md` (500+ lines) - What was built and architecture
- ✅ `QUICK_REFERENCE.md` (200+ lines) - Command reference card
- ✅ `ARCHITECTURE_DIAGRAM.md` (400+ lines) - System diagrams
- ✅ `VERIFICATION_CHECKLIST.md` (427 lines) - Testing checklist
- ✅ `README_INDEX.md` (this file)

### Code (New Package: rov_mavlink)
- ✅ `src/rov_mavlink/package.xml` - Package manifest
- ✅ `src/rov_mavlink/setup.py` - Python package setup
- ✅ `src/rov_mavlink/setup.cfg` - Build configuration
- ✅ `src/rov_mavlink/config/mavlink_params.yaml` - Configuration
- ✅ `src/rov_mavlink/launch/mavlink_launch.py` - Launch file
- ✅ `src/rov_mavlink/rov_mavlink/mavlink_bridge_node.py` (400+ lines) - Main bridge
- ✅ `src/rov_mavlink/rov_mavlink/mavlink_utils.py` - Utilities
- ✅ `src/rov_mavlink/rov_mavlink/__init__.py` - Package init

### Installation Automation
- ✅ `install.sh` - One-command setup script
- ✅ `requirements.txt` - Python dependencies

### Modified Files
- ✅ `src/rov_onboard/launch/onboard_launch.py` - Added MAVLink bridge launch
- ✅ `src/rov_onboard/rov_onboard/thruster_node.py` - Updated documentation
- ✅ `src/rov_onboard/package.xml` - Added rov_mavlink dependency
- ✅ `README.md` - Added MAVLink section

---

## 🔧 Key Features Implemented

✅ **Bidirectional MAVLink Communication**
- ROS2 commands → MAVLink → PIX6 → Thrusters
- PIX6 telemetry → MAVLink → ROS2 → Dashboard

✅ **Thread-Safe Architecture**
- Background thread for serial/UDP communication
- ROS2 main thread for pub/sub
- Automatic reconnection with retry logic

✅ **Flexible Configuration**
- Serial or UDP connection support
- Configurable heartbeat interval (10 Hz default)
- Adjustable servo channel mapping (CH1-6 for thrusters)

✅ **Complete Message Support**
- Sends: HEARTBEAT, SERVO_CONTROL, COMMAND_LONG
- Receives: HEARTBEAT, SYS_STATUS, ATTITUDE, GLOBAL_POSITION_INT, RANGEFINDER, BATTERY_STATUS

✅ **Safety & Reliability**
- Heartbeat watchdog
- Arm/disarm commands
- PWM range validation
- Error logging and recovery

---

## 📋 System Overview

```
Control Laptop (ROS2)
    ↓ gamepad input
    ↓ /rov/thruster_command
    ↓ (network)
LattePanda (ROS2)
    ↓ MAVLink Bridge Node
    ↓ Serial/USB (115200 baud)
Radiolink PIX6 (ArduSub)
    ↓ PWM outputs
Thrusters & Sensors
```

---

## 🐛 Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| "MAVLink connection failed" | See **MAVLINK_SETUP.md** → Troubleshooting → Connection Issues |
| No ROS2 topics visible | Check `ROS_DOMAIN_ID=42`, see **QUICK_REFERENCE.md** → Network Troubleshooting |
| Low framerate or latency | See **QUICK_REFERENCE.md** → Performance Troubleshooting |
| Hardware not responding | See **VERIFICATION_CHECKLIST.md** → Hardware Configuration Verification |

---

## 📞 Support Resources

- **ArduSub Docs**: https://ardupilot.org/
- **MAVLink Protocol**: https://mavlink.io/
- **ROS2 Documentation**: https://docs.ros.org/en/humble/
- **pymavlink GitHub**: https://github.com/ArduPilot/pymavlink
- **PIX6 Autopilot**: https://www.radiolink.com.cn/

---

## ✅ Deployment Checklist

Before deploying to the field, complete:

1. ☐ Read **MAVLINK_SETUP.md**
2. ☐ Run **install.sh** on both machines
3. ☐ Configure PIX6 in QGroundControl
4. ☐ Test MAVLink connection
5. ☐ Verify ROS2 topics
6. ☐ Run all tests in **VERIFICATION_CHECKLIST.md**
7. ☐ Monitor system for 30+ minutes
8. ☐ Sign off on verification

---

## 📖 Documentation Reading Order

### For First-Time Setup
```
1. README.md (5 min)
   ↓
2. MAVLINK_SETUP.md - Sections 1-4 (20 min)
   ↓
3. Install & Configure Hardware (30 min)
   ↓
4. MAVLINK_SETUP.md - Sections 5-8 (10 min)
   ↓
5. Test & Verify (20 min)
```

### For Understanding Architecture
```
1. README.md (5 min)
   ↓
2. ARCHITECTURE_DIAGRAM.md (20 min)
   ↓
3. INTEGRATION_SUMMARY.md (30 min)
   ↓
4. Source code review (optional)
```

### For Daily Operations
```
1. QUICK_REFERENCE.md (keep open)
   ↓
2. Use command reference as needed
   ↓
3. Consult MAVLINK_SETUP.md for detailed help
```

---

## 🎓 Learning Resources

### If you're new to ROS2:
- Start with: README.md → ARCHITECTURE_DIAGRAM.md → QUICK_REFERENCE.md
- Focus on: Topic publishing/subscribing, launch files, node communication

### If you're new to MAVLink:
- Start with: ARCHITECTURE_DIAGRAM.md (Message Flow section)
- Focus on: What messages are sent/received, how servo control works

### If you're new to both:
- Follow complete MAVLINK_SETUP.md in order
- It explains concepts as you implement them

---

## 🔄 Next Steps After Setup

1. **Test Basic Communication**
   - Verify MAVLink heartbeat
   - Check telemetry flowing
   - Publish test thruster commands

2. **Integrate with Hardware**
   - Test individual thrusters
   - Verify PWM outputs match commands
   - Check sensor readings

3. **Extend Functionality**
   - Add arm/disarm to gamepad
   - Implement failsafe handling
   - Add telemetry logging
   - Enhance dashboard

4. **Advanced Features**
   - Autonomous control
   - Computer vision integration
   - Mission planning
   - Data recording

---

## 📊 Project Statistics

| Metric | Value |
|--------|-------|
| New Python Code | 400+ lines |
| New Documentation | 2000+ lines |
| Configuration Files | 3 YAML files |
| Launch Files | 3 files |
| New Package | 1 (rov_mavlink) |
| Modified Files | 4 |
| Total Documentation | 8 files |
| Setup Time | 30-60 minutes |
| Testing Time | 1-2 hours |

---

## 🎯 Success Criteria

Your system is ready when:
- ✅ All nodes start without errors
- ✅ MAVLink connection established
- ✅ Topics visible on control laptop
- ✅ Telemetry flowing (>5 Hz)
- ✅ Thruster commands received by PIX6
- ✅ All verification tests pass
- ✅ System stable for 30+ minutes

---

**Last Updated**: March 10, 2026

**For the most current information, always check MAVLINK_SETUP.md**

---

## Document Sizes & Estimates

| Document | Size | Read Time |
|----------|------|-----------|
| README.md | 10 KB | 10 min |
| MAVLINK_SETUP.md | 25 KB | 30 min |
| INTEGRATION_SUMMARY.md | 20 KB | 25 min |
| ARCHITECTURE_DIAGRAM.md | 20 KB | 25 min |
| QUICK_REFERENCE.md | 15 KB | 15 min |
| VERIFICATION_CHECKLIST.md | 15 KB | 20 min |
| **Total** | **~105 KB** | **~2 hours** |

---

**Start with MAVLINK_SETUP.md and follow along!** ⭐


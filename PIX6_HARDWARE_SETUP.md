# Radiolink PIX6 & ArduSub Hardware Setup Guide

## Overview

The Radiolink PIX6 is a flight controller that runs ArduSub firmware. It connects to your LattePanda via USB (MAVLink protocol) and communicates with MAVROS to receive thrust commands from your ROS 2 control system.

**Key Features:**
- IMU (6-DOF accelerometer + gyroscope)
- Barometer (depth sensor)
- Compass (magnetometer)
- 14 PWM outputs for thrusters/servos
- USB and serial connectivity
- ArduSub firmware support

---

## Part 1: Initial Setup & Flashing

### Hardware Required
- Radiolink PIX6 flight controller
- USB cable (appropriate for your PIX6 variant)
- Windows/Linux/Mac computer with internet
- QGroundControl application

### Step 1: Download QGroundControl

1. Visit: http://qgroundcontrol.com/downloads
2. Download for your OS
3. Extract and make executable:
   ```bash
   chmod +x QGroundControl.AppImage
   ./QGroundControl.AppImage &
   ```

### Step 2: Connect PIX6 and Flash ArduSub

1. **Connect PIX6 to USB port** on your computer
2. **Open QGroundControl**
3. **Wait for device detection** (top-left corner shows connection status)
4. Go to: **Vehicle Setup → Firmware**
5. **Select ArduSub** from the dropdown (do NOT select ArduCopter)
   - This is critical for underwater operation
6. Click **OK** to download and flash firmware
7. **Wait 2-3 minutes** for flashing to complete
8. You'll see:
   ```
   Flashing...
   Verifying...
   Done.
   ```

**✓ PIX6 now has ArduSub firmware**

---

## Part 2: Parameter Configuration

### Serial Port Settings

After flashing, configure ArduSub parameters. In QGroundControl:

1. Go to: **Vehicle Setup → Parameters**
2. Search for the following and configure:

#### USB/Serial Communication
```
SERIAL0_PROTOCOL    = 2 (MAVLink)
SERIAL0_BAUD        = 115200
SERIAL0_OPTIONS     = 0
```

> SERIAL0 is the USB port. This enables MAVLink communication with MAVROS.

#### Frame Configuration
```
FRAME_CLASS         = 2 (Vectored Six DOF ROV)
FRAME_TYPE          = 0 (BlueRobotics Heavy)
```

> Choose based on your ROV frame. Most common: Frame Class = 2 (Vectored)

#### IMU/Compass
```
INS_GYROFFS_X       = 0.0 (after calibration)
INS_GYROFFS_Y       = 0.0
INS_GYROFFS_Z       = 0.0
COMPASS_ENABLED     = 1
COMPASS_USE         = 1
COMPASS_AUTODEC     = 1 (enable auto declination)
```

#### Motor Output Mapping
```
MOT_1_DIRECTION     = 1 or -1 (1=CCW, -1=CW) [each thruster]
MOT_1_PWM_MIN       = 1100
MOT_1_PWM_MAX       = 1900
MOT_PWM_TYPE        = 0 (PWM)
```

> Configure each MOT_X for your thruster layout. See next section.

#### Failsafe Settings
```
FS_ENA              = 1 (Enable failsafe)
FS_ACTION           = 1 (Hold position on signal loss)
FS_OPTIONS          = 0
```

#### Joystick Disable (we use MAVLink instead)
```
JSK_ENA             = 0 (Disable joystick input)
```

---

## Part 3: Thruster Layout Configuration

### Define Your Thruster Numbering

ArduSub supports up to 8 thrusters. Define in QGroundControl: **Setup → Mandatory Hardware → Frame → Thruster Layout**

**Standard 6-Thruster ROV Layout:**
```
PIX6 PWM Output → ArduSub Channel Mapping:

PWM OUT 1 → Thruster 1 (Front Left)
PWM OUT 2 → Thruster 2 (Front Right)
PWM OUT 3 → Thruster 3 (Back Left)
PWM OUT 4 → Thruster 4 (Back Right)
PWM OUT 5 → Thruster 5 (Vertical Left)
PWM OUT 6 → Thruster 6 (Vertical Right)
PWM OUT 7 → (optional servo)
PWM OUT 8 → (optional servo)
```

### Direction Calibration

For each thruster, ArduSub applies a mixing matrix. You can reverse direction in two ways:

**Method 1: ArduSub Parameters**
```
MOT_1_DIRECTION     = 1  (1=normal, -1=reversed)
MOT_2_DIRECTION     = 1
... (repeat for each thruster)
```

**Method 2: Reverse ESC/Motor Polarity**
- Swap any two of the motor wires connected to the ESC

Test by sending a positive RC command:
- Thruster should spin forward
- If backward, set `MOT_X_DIRECTION = -1`

---

## Part 4: Sensor Calibration

### Compass Calibration

**Essential for heading hold and autonomous features**

1. In QGroundControl: **Vehicle Setup → Compass**
2. Click **Start** button
3. **Rotate the PIX6 in all directions** (like a figure-8) for ~1 minute
4. System will show completion with offset values
5. Click **Accept** to save

### Accelerometer Calibration

1. Go to: **Vehicle Setup → Accelerometer**
2. Place PIX6 **level on a flat surface**
3. Click **Calibrate**
4. Don't move it for ~5 seconds
5. Wait for completion

### Barometer Calibration

Usually auto-calibrates on startup. To force:

1. Go to: **Vehicle Setup → Parameters**
2. Set `GND_ABS_PRESS` = current barometric pressure at your location
   - Check: https://weather.noaa.gov/
   - Look for "altimeter setting" (in inches of Hg or mb)

### Radio/RC Calibration

1. Go to: **Vehicle Setup → Radio**
2. Move all control sticks through full range
3. System will auto-detect min/max values
4. Click **Calibrate**

> For MAVROS control (not traditional RC), you can skip this but it's good for failsafe validation.

---

## Part 5: ESC Calibration (Motor Calibration)

**Critical for consistent thrust output**

Each Electronic Speed Controller (ESC) needs PWM range calibration:

### Procedure

1. **Disconnect battery** from ESCs
2. **Connect PIX6 to USB** (for programming)
3. In QGroundControl: **Vehicle Setup → Power Module**
4. Look for **ESC Calibration** option
5. Click **Calibrate**
6. **Follow on-screen instructions:**
   - Connect battery when prompted
   - Hear three beeps (low-mid-high)
   - PIX6 sends full throttle
   - Hear descending tone when detected
   - **Disconnect battery**
   - System saves ESC throttle range

7. **Repeat for each ESC** if doing individually

Alternatively, use ESC's native calibration tool (depends on ESC model).

---

## Part 6: Motor Matrix Mixing

ArduSub uses a motor mixing matrix to convert command inputs to individual thruster outputs.

### Default 6-Thruster Matrix

For a standard vectored ROV:
```
Thrust Command → Thruster Outputs:

Roll (CH1):     +FL -FR +BL -BR  0   0
Pitch (CH2):    +FL +FR -BL -BR  0   0
Throttle (CH3):  0   0   0   0  +VL +VR
Yaw (CH4):      +FL -FR -BL +BR  0   0
```

### Customize in ArduSub Parameters

Search for `MOT_` parameters:
```
MOT_1_ROLL      = 1.0   (contribution to roll)
MOT_1_PITCH     = 1.0   (contribution to pitch)
MOT_1_THROTTLE  = 0.0
MOT_1_YAW       = 1.0
... (repeat for MOT_2 through MOT_6)
```

**Check your thruster positions and adjust the matrix accordingly.**

---

## Part 7: USB Connection to LattePanda

### Hardware Connection

1. **Connect PIX6 USB port** to a USB port on LattePanda
2. PIX6 will power on (red/green LED indicators)
3. On LattePanda, verify device appears:
   ```bash
   lsusb
   # Look for: "Silicon Labs CP210x UART Bridge Controller" or similar
   ```

4. Find the serial port:
   ```bash
   ls /dev/ttyUSB* /dev/ttyACM*
   # Usually: /dev/ttyACM0 or /dev/ttyUSB0
   ```

### Update ROS Configuration

Edit `src/rov_onboard/config/onboard_params.yaml`:
```yaml
mavros_bridge_node:
  ros__parameters:
    fcu_port: "/dev/ttyACM0"  # Change if different
    fcu_baud: 115200
    armed: false
```

### USB Permissions (if needed)

```bash
# Check if you can read the device
cat /dev/ttyACM0
# If permission denied, fix permissions

sudo usermod -a -G dialout $USER
newgrp dialout

# Or temporarily
sudo chmod 666 /dev/ttyACM0
```

---

## Part 8: Verification & Testing

### Test MAVLink Connection

1. **Connect PIX6 to LattePanda** via USB
2. **Start MAVROS bridge node** (without arming):
   ```bash
   ros2 launch rov_onboard onboard_launch.py
   ```

3. **Monitor debug output:**
   ```bash
   ros2 node info /mavros_bridge_node
   ```

4. **Test publishing RC override** (on laptop):
   ```bash
   ros2 topic pub /mavros/rc/override mavros_msgs/OverrideRCIn \
     "{channels: [1500, 1500, 1500, 1500, 1100, 1500, 1500, 1500]}"
   ```

5. **Monitor on LattePanda:**
   ```bash
   ros2 topic echo /mavros/rc/override
   ```

**Success indicators:**
- ✓ No serial errors in logs
- ✓ RC override values match what you publish
- ✓ QGroundControl shows "Connected" status
- ✓ No red warning lights on PIX6

---

## Part 9: Pre-Flight Checks

Before entering water:

### Safety Checks
- [ ] All thrusters installed and balanced
- [ ] Propellers attached (correctly oriented)
- [ ] All PWM connectors secure
- [ ] USB cable not pinched or damaged
- [ ] Battery fully charged
- [ ] All sensors returning data in QGroundControl

### ROS 2 Checks
- [ ] Thruster commands publishing
- [ ] MAVROS RC override publishing
- [ ] No serial errors
- [ ] All nodes running without crashes

### Manual Thrust Test (in air)
1. Arm using QGroundControl manual arm button
2. Increase thrust slowly with gamepad/keyboard
3. Watch each thruster:
   - Should spin in correct direction
   - Should have balanced power
   - No unusual vibrations or sounds

### Water Entry Test (Shallow)
1. Start in 30 cm water
2. Test forward motion
3. Test side motion
4. Test vertical motion
5. Test rotation
6. Check for leaks immediately after exit

---

## Troubleshooting

### PIX6 Not Detected
```bash
# Check USB device
lsusb | grep -i "silicon\|ftdi\|cp210"

# If not listed:
1. Try different USB cable
2. Try different USB port
3. Restart LattePanda
4. Flash firmware again
```

### No MAVLink Communication
```bash
# Check serial port
ls -la /dev/ttyACM0

# Test connection
sudo minicom -D /dev/ttyACM0 -b 115200

# Should show MAVLink heartbeat data (binary)
```

### Thrusters Won't Respond
```bash
# In QGroundControl:
1. Check Vehicle Health in top-left
2. Verify "Armed" status
3. Check RC Input shows values changing
4. Check Motor Health shows PWM output 1000-2000
```

### Compass Errors
```bash
# In QGroundControl Logs:
- Look for compass offset too large
- Re-calibrate compass away from metal objects
- Check compass isn't upside down
```

---

## Reference: RC Channel Assignments

| Channel | Function | Min | Center | Max |
|---------|----------|-----|--------|-----|
| 1 | Roll (Strafe L/R) | 1000 | 1500 | 2000 |
| 2 | Pitch (Forward/Back) | 1000 | 1500 | 2000 |
| 3 | Throttle (Vertical) | 1000 | 1500 | 2000 |
| 4 | Yaw (Rotate) | 1000 | 1500 | 2000 |
| 5 | Mode/Manual Control | 1000 | 1100 | 2000 |
| 6 | Lights/Camera | 1000 | 1500 | 2000 |

---

## Further Configuration

For advanced users, see:
- ArduSub Wiki: https://ardupilot.org/ardusub/
- Parameter Reference: https://ardupilot.org/ardusub/parameters.html
- Motor Matrix Guide: https://ardupilot.org/ardusub/frame-setup.html

---

**Last Updated:** March 12, 2026


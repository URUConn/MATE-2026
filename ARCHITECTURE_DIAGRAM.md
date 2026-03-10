# MATE-2026 ROV System Diagram

## Hardware Connection Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                         LattePanda (ARM/x86)                          │
│                      Ubuntu 22.04 + ROS2 Humble                       │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    ROS2 Node Network                            │ │
│  │                                                                  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │ │
│  │  │ camera_node  │  │ sensor_node  │  │ status_node  │         │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │ │
│  │         │                 │                 │                 │ │
│  │         ├─────────────────┼─────────────────┤                 │ │
│  │         │   ROS2 Topics   │                 │                 │ │
│  │         ▼                 ▼                 ▼                 │ │
│  │    /rov/camera/*    /rov/sensor_data   /rov/status           │ │
│  │                                                                  │ │
│  │  ┌────────────────────────────────────────────────────────┐   │ │
│  │  │           mavlink_bridge_node (NEW)                    │   │ │
│  │  │                                                         │   │ │
│  │  │  Subscribes to:   /rov/thruster_command                │   │ │
│  │  │  Publishes to:    /rov/sensor_data, /rov/status       │   │ │
│  │  │                                                         │   │ │
│  │  │  Thread 1: MAVLink Serial/UDP Communication            │   │ │
│  │  │  Thread 2: ROS2 Pub/Sub                                │   │ │
│  │  └────────────┬──────────────────┬───────────────────────┘   │ │
│  │               │                  │                            │ │
│  │     ┌─────────▼──────┐          │                            │ │
│  │     │ thruster_node  │          │                            │ │
│  │     │  (pass-through) │          │                            │ │
│  │     └────────────────┘          │                            │ │
│  │                                  │                            │ │
│  │                                  │ MAVLink Protocol           │ │
│  │                                  │ (Python pymavlink)        │ │
│  │                                  │                            │ │
│  └──────────────────────────────────┼────────────────────────────┘ │
│                                      │                              │
│  Hardware Interface:                 │                              │
│  ┌──────────────┐                    │                              │
│  │ USB to TTL   │◄───────────────────┘                              │
│  │ (FTDI)       │                                                   │
│  └──────┬───────┘                                                   │
│         │ TTL Serial (TX/RX/GND)                                    │
└─────────┼──────────────────────────────────────────────────────────┘
          │
          │ MAVLink Binary Protocol
          │ 115200 baud (configurable)
          │ ~/dev/ttyUSB0
          │
          │
┌─────────▼──────────────────────────────────────────────────────────┐
│         Radiolink PIX6 Autopilot (ArduSub / ChibiOS)               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Serial Port (UART)                                         │  │
│  │  • Receives MAVLink messages                                │  │
│  │  • Sends telemetry back                                     │  │
│  │                                                              │  │
│  │  MAVLink Parser / Handler                                   │  │
│  │  • Processes SERVO_CONTROL messages                         │  │
│  │  • Processes COMMAND_LONG (arm/disarm)                      │  │
│  │  • Sends HEARTBEAT, SYS_STATUS, ATTITUDE, etc.              │  │
│  └────┬──────────────────────────────────────────────────────┬─┘  │
│       │                                                       │    │
│       │ PWM Output (8 channels)                              │    │
│       │                                                       │    │
│  ┌────▼────────────────────────────────────────────────────┬─┘    │
│  │ Servo Outputs:                                          │      │
│  │  CH1-CH6: Thrusters (6 DOF)                             │      │
│  │  CH7-CH8: Accessories (cameras, lights, gripper)        │      │
│  │                                                          │      │
│  │ Onboard Sensors:                                         │      │
│  │  • IMU (Attitude: roll, pitch, yaw)                      │      │
│  │  • Compass (Heading)                                     │      │
│  │  • Barometer (Depth sensor / altitude)                   │      │
│  │  • Battery Monitor (Voltage, current)                    │      │
│  │                                                          │      │
│  │ ESC/Motor Drivers:                                       │      │
│  │  • PWM output to ESCs                                    │      │
│  │  • Optional DShot protocol support                       │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
└────────────┬──────────────────────────────────────────────────────┘
             │
      ┌──────┴──────────┐
      │                 │
      ▼                 ▼
  [Thrusters]      [Sensors/Leak Detector]
  (6x vectored)    • Depth/pressure
  • Front Left     • Temperature
  • Front Right    • Leak detector
  • Back Left      • Battery voltage
  • Back Right     • Current draw
  • Vertical Left  • Compass
  • Vertical Right • IMU (accel, gyro)
```

---

## ROS2 Network Communication (Multi-Machine)

```
                    LAN / Ethernet / WiFi
                    (UDP ROS2 Bridge)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        │                   │                   │
┌───────▼──────────┐        │        ┌──────────▼──────────┐
│ LattePanda       │        │        │  Control Laptop    │
│ (IP: 192.168.1.100)       │        │ (IP: 192.168.1.101)│
│                  │        │        │                    │
│ ROS2 Domain ID: │        │        │ ROS2 Domain ID:   │
│        42        │        │        │        42          │
│                  │        │        │                    │
│ Publishers:      │        │        │ Subscribers:       │
│ ✓ /rov/camera/* │        │        │ ✓ /rov/camera/*   │
│ ✓ /rov/sensor..│        │        │ ✓ /rov/sensor..   │
│ ✓ /rov/status   │        │        │ ✓ /rov/status     │
│                  │        │        │                    │
│ Subscribers:     │        │        │ Publishers:        │
│ ✓ /rov/thruster │        │        │ ✓ /rov/thruster   │
│                  │        │        │                    │
│ Discovery Port:  │        │        │ Discovery Port:    │
│      5353 UDP    │────────────────│      5353 UDP       │
│                  │        │        │                    │
│ Communication:   │        │        │ Communication:     │
│    7400+ UDP     │        │        │    7400+ UDP       │
└──────────────────┘        │        └────────────────────┘
                            │
                   Firewall Ports:
                   • 5353/UDP (discovery)
                   • 7400-7409/UDP (ROS2 comms)
```

---

## Message Flow Diagram

### Thruster Command Flow

```
Gamepad Controller
        │
        ▼
[gamepad_node] publishes
        │
        ▼
/rov/thruster_command
    (ThrusterCommand message)
    {thruster_front_left: 0.5,
     thruster_front_right: 0.5,
     thruster_back_left: 0.0,
     thruster_back_right: 0.0,
     thruster_vertical_left: 0.0,
     thruster_vertical_right: 0.0}
        │
        ├──► [thruster_node] (debug logs)
        │
        └──► [mavlink_bridge_node] converts:
                │
                ├─ Channel 1: 0.5 → 1700 μs
                ├─ Channel 2: 0.5 → 1700 μs
                ├─ Channel 3: 0.0 → 1500 μs
                ├─ Channel 4: 0.0 → 1500 μs
                ├─ Channel 5: 0.0 → 1500 μs
                └─ Channel 6: 0.0 → 1500 μs
                │
                ▼
        MAVLink SERVO_CONTROL message:
        (binary protocol, pymavlink)
                │
                ▼
        Serial Port (/dev/ttyUSB0)
        115200 baud, 8N1
                │
                ▼
        Radiolink PIX6:
        • Parse MAVLink binary
        • Update servo outputs
        • Send PWM to ESCs
                │
                ▼
        Thruster ESCs receive PWM:
        • 1100 μs = -100% (full reverse)
        • 1500 μs = 0% (neutral/stop)
        • 1900 μs = +100% (full forward)
                │
                ▼
        Thrusters spin accordingly
```

### Telemetry Return Flow

```
Radiolink PIX6:
• Reads onboard sensors (IMU, pressure, compass)
• Reads PWM from servo outputs
• Generates MAVLink telemetry messages:
  - HEARTBEAT (1 Hz)
  - SYS_STATUS (battery, errors)
  - ATTITUDE (roll, pitch, yaw)
  - GLOBAL_POSITION_INT (GPS, alt)
  - RANGEFINDER (depth sensor)
  - BATTERY_STATUS (voltage, current)
  - SERVO_OUTPUT_RAW (servo feedback)
        │
        ▼
Serial Port (/dev/ttyUSB0)
Binary MAVLink protocol
        │
        ▼
[mavlink_bridge_node]:
• Parses binary MAVLink
• Extracts telemetry data
• Converts to ROS2 messages
        │
        ├──► /rov/status (RovStatus)
        │    {armed, mode, cpu_temp, ...}
        │
        └──► /rov/sensor_data (SensorData)
             {depth, temperature, heading,
              pitch, roll, battery_voltage}
        │
        ▼
[dashboard_node] subscribes and displays:
        │
        ├─ Attitude indicator (roll/pitch)
        ├─ Depth gauge
        ├─ Battery voltage
        ├─ Temperature
        ├─ Armed/disarmed status
        └─ System mode
        │
        ▼
Control Laptop GUI
```

---

## Configuration Hierarchy

```
ROS2 Parameters
      │
      ├─ onboard_params.yaml
      │  (rov_onboard package)
      │  ├─ camera_index: 0
      │  ├─ frame_width: 1280
      │  ├─ frame_height: 720
      │  ├─ fps: 60
      │  ├─ publish_rate: 10.0
      │  └─ armed: false
      │
      ├─ mavlink_params.yaml (NEW)
      │  (rov_mavlink package)
      │  ├─ connection_string: /dev/ttyUSB0:115200
      │  ├─ system_id: 1
      │  ├─ component_id: 191
      │  ├─ heartbeat_interval: 0.1
      │  ├─ telemetry_rate: 10
      │  └─ servo_channel_mapping: [1,2,3,4,5,6]
      │
      └─ control_params.yaml
         (rov_control package)
         ├─ gamepad_deadzone: 0.15
         ├─ max_thrust: 1.0
         └─ ...

Launch Override:
    ros2 launch rov_onboard onboard_launch.py \
        mavlink_connection:=/dev/ttyUSB0:115200 \
        connection_string:=udp:192.168.1.100:14550
```

---

## Software Stack (Layers)

```
┌─────────────────────────────────────────────┐
│  User Applications                          │
│  ├─ Gamepad input handling                  │
│  ├─ Dashboard/GUI display                   │
│  └─ Camera viewer                           │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│  ROS2 Application Layer                     │
│  ├─ gamepad_node (publishes ThrusterCmd)    │
│  ├─ thruster_node (subscribes)              │
│  ├─ camera_node (publishes Image)           │
│  ├─ sensor_node (publishes SensorData)      │
│  ├─ status_node (publishes RovStatus)       │
│  └─ mavlink_bridge_node (NEW - converts)    │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│  ROS2 Middleware (DDS)                      │
│  ├─ Topic discovery (UDP 5353)              │
│  ├─ Message transport (UDP 7400+)           │
│  └─ DDS (Cyclone DDS / Fast-DDS)            │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│  Protocol Layer                             │
│  ├─ MAVLink (on LattePanda)                 │
│  │  └─ pymavlink Python library             │
│  │                                          │
│  └─ UDP/TCP IP (between machines)           │
└─────────────────────────────────────────────┘
                    │
┌─────────────────────────────────────────────┐
│  Hardware Layer                             │
│  ├─ Serial/USB FTDI adapter                 │
│  ├─ Ethernet/WiFi adapter                   │
│  ├─ PIX6 UART port                          │
│  ├─ PIX6 PWM outputs (8x servo)             │
│  └─ Various sensors                         │
└─────────────────────────────────────────────┘
```

---

## Directory Tree

```
MATE-2026/
├── README.md ......................... Main project README
├── MAVLINK_SETUP.md .................. ★ Detailed setup guide (START HERE)
├── INTEGRATION_SUMMARY.md ............ Architecture and summary
├── QUICK_REFERENCE.md ............... Command reference card
├── install.sh ....................... Automated setup script
├── requirements.txt ................. Python dependencies
├── LICENSE
│
└── src/
    ├── rov_msgs/
    │   ├── CMakeLists.txt
    │   ├── package.xml
    │   └── msg/
    │       ├── ThrusterCommand.msg ... Custom message type
    │       ├── SensorData.msg ........ Custom message type
    │       └── RovStatus.msg ......... Custom message type
    │
    ├── rov_mavlink/ ................. ★ NEW MAVLINK PACKAGE
    │   ├── package.xml
    │   ├── setup.py
    │   ├── setup.cfg
    │   ├── resource/rov_mavlink
    │   ├── config/
    │   │   └── mavlink_params.yaml .. Configuration
    │   ├── launch/
    │   │   └── mavlink_launch.py ... Standalone launch
    │   └── rov_mavlink/
    │       ├── __init__.py
    │       ├── mavlink_bridge_node.py  ★ Main bridge (400+ lines)
    │       └── mavlink_utils.py .... Utilities
    │
    ├── rov_onboard/
    │   ├── package.xml (UPDATED)
    │   ├── setup.py
    │   ├── setup.cfg
    │   ├── config/
    │   │   └── onboard_params.yaml
    │   ├── launch/
    │   │   ├── onboard_launch.py (UPDATED) .. Now includes mavlink_bridge_node
    │   │   └── camera_only_launch.py
    │   └── rov_onboard/
    │       ├── __init__.py
    │       ├── camera_node.py
    │       ├── sensor_node.py
    │       ├── status_node.py
    │       └── thruster_node.py (UPDATED) ... MAVLink-aware
    │
    └── rov_control/
        ├── package.xml
        ├── setup.py
        ├── setup.cfg
        ├── config/
        │   └── control_params.yaml
        ├── launch/
        │   ├── control_launch.py
        │   └── camera_viewer_only_launch.py
        └── rov_control/
            ├── __init__.py
            ├── camera_viewer_node.py
            ├── dashboard_node.py
            └── gamepad_node.py
```

---

## Key Data Structures

### ThrusterCommand Message
```protobuf
float32 thruster_front_left       # -1.0 to 1.0
float32 thruster_front_right      # -1.0 to 1.0
float32 thruster_back_left        # -1.0 to 1.0
float32 thruster_back_right       # -1.0 to 1.0
float32 thruster_vertical_left    # -1.0 to 1.0
float32 thruster_vertical_right   # -1.0 to 1.0
```

### SensorData Message
```protobuf
float32 depth                     # meters
float32 temperature               # celsius
float32 heading                   # degrees (0-360)
float32 pitch                     # degrees (-90 to 90)
float32 roll                      # degrees (-180 to 180)
float32 battery_voltage           # volts
```

### RovStatus Message
```protobuf
bool    armed                     # True if vehicle is armed
bool    leak_detected             # True if water detected
string  mode                      # "STABILIZE", "ALT_HOLD", etc.
float32 cpu_temperature           # celsius
float32 uptime_seconds            # seconds since boot
```

---

**For detailed setup instructions, see MAVLINK_SETUP.md**


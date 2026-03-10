"""
MAVLink Bridge Node - Translates between ROS2 messages and MAVLink protocol
Communicates with ArduSub autopilot (Radiolink PIX6) via serial/UDP
Runs on the LattePanda (onboard computer)
"""

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
import threading
import time
from rov_msgs.msg import ThrusterCommand, SensorData, RovStatus
from std_msgs.msg import UInt8

from pymavlink.dialects.v10 import ardusub as mavlink_module
from pymavlink.mavutil import mavconnection

# MAVLink message enums
MAV_MODE_STABILIZE_ARMED = 217
MAV_MODE_STABILIZE_DISARMED = 216


class MAVLinkBridgeNode(Node):
    """Bridge between ROS2 and MAVLink protocol for ArduSub autopilot"""

    def __init__(self):
        super().__init__('mavlink_bridge_node')

        # Declare parameters
        self.declare_parameter('connection_string', '/dev/ttyUSB0:115200')
        self.declare_parameter('system_id', 1)
        self.declare_parameter('component_id', 191)  # 191 = Rover
        self.declare_parameter('heartbeat_interval', 0.1)  # 10 Hz
        self.declare_parameter('telemetry_rate', 10)  # Hz
        self.declare_parameter('servo_channel_mapping', [1, 2, 3, 4, 5, 6])  # Thruster channels
        self.declare_parameter('arm_timeout', 5.0)  # Seconds to wait for arm/disarm

        # Get parameters
        self.connection_string = self.get_parameter('connection_string').value
        self.system_id = self.get_parameter('system_id').value
        self.component_id = self.get_parameter('component_id').value
        self.heartbeat_interval = self.get_parameter('heartbeat_interval').value
        self.telemetry_rate = self.get_parameter('telemetry_rate').value
        self.servo_channels = self.get_parameter('servo_channel_mapping').value
        self.arm_timeout = self.get_parameter('arm_timeout').value

        # State tracking
        self.armed = False
        self.connected = False
        self.last_heartbeat = time.time()
        self.system_status = None
        self.current_servo_values = [0] * 16  # Servo channels 1-16
        self.last_thruster_command = None

        # MAVLink connection (initialized in thread)
        self.mav_connection = None
        self.running = True

        # ROS2 subscriptions
        self.thruster_subscription = self.create_subscription(
            ThrusterCommand,
            '/rov/thruster_command',
            self.thruster_callback,
            10
        )

        # ROS2 publishers
        self.sensor_publisher = self.create_publisher(SensorData, '/rov/sensor_data', 10)
        self.status_publisher = self.create_publisher(RovStatus, '/rov/status', 10)

        self.get_logger().info(f'MAVLink Bridge initializing on {self.connection_string}')

        # Start MAVLink communication thread
        self.mav_thread = threading.Thread(target=self._mavlink_worker, daemon=True)
        self.mav_thread.start()

        # Heartbeat timer (ROS2 context, lower priority)
        self.heartbeat_timer = self.create_timer(
            self.heartbeat_interval,
            self.send_heartbeat
        )

        # Telemetry polling timer
        self.telemetry_timer = self.create_timer(
            1.0 / self.telemetry_rate,
            self.process_mavlink_messages
        )

    def _mavlink_worker(self):
        """Background thread for MAVLink connection and heartbeat"""
        retry_count = 0
        max_retries = 5

        while self.running and retry_count < max_retries:
            try:
                self.get_logger().info(f'Attempting to connect to MAVLink on {self.connection_string}...')
                self.mav_connection = mavconnection(self.connection_string)
                self.connected = True
                retry_count = 0
                self.get_logger().info('MAVLink connection established!')

                # Heartbeat and message loop
                while self.running and self.connected:
                    try:
                        # Send heartbeat
                        now = time.time()
                        if now - self.last_heartbeat > self.heartbeat_interval:
                            self._send_heartbeat_mavlink()
                            self.last_heartbeat = now

                        # Small sleep to prevent busy-waiting
                        time.sleep(0.01)

                    except Exception as e:
                        self.get_logger().warn(f'Heartbeat error: {e}')
                        self.connected = False
                        break

            except Exception as e:
                self.get_logger().warn(f'Failed to connect: {e}. Retrying in 2 seconds...')
                retry_count += 1
                time.sleep(2)

        if not self.running:
            if self.mav_connection:
                self.mav_connection.close()
            self.get_logger().info('MAVLink worker thread shutting down')
        else:
            self.get_logger().error(f'MAVLink connection failed after {max_retries} retries')

    def _send_heartbeat_mavlink(self):
        """Send MAVLink HEARTBEAT message to autopilot"""
        if not self.mav_connection:
            return

        try:
            self.mav_connection.mav.heartbeat_send(
                type=mavlink_module.MAV_TYPE_SUBMARINE,
                autopilot=mavlink_module.MAV_AUTOPILOT_ARDUPILOT,
                base_mode=217 if self.armed else 216,  # armed/disarmed
                system_status=mavlink_module.MAV_STATE_ACTIVE,
                mavlink_version=3
            )
        except Exception as e:
            self.get_logger().debug(f'Heartbeat send error: {e}')

    def send_heartbeat(self):
        """ROS2 timer callback - checks connection status"""
        if not self.connected:
            self.get_logger().warn('MAVLink not connected')

    def process_mavlink_messages(self):
        """ROS2 timer callback - receive and process MAVLink messages"""
        if not self.mav_connection or not self.connected:
            return

        try:
            # Read available messages (non-blocking)
            while True:
                msg = self.mav_connection.recv_match(blocking=False)
                if msg is None:
                    break

                self._handle_mavlink_message(msg)

        except Exception as e:
            self.get_logger().debug(f'Error processing MAVLink messages: {e}')

    def _handle_mavlink_message(self, msg):
        """Process incoming MAVLink messages and publish to ROS2"""
        if msg is None:
            return

        msg_type = msg.get_type()

        if msg_type == 'HEARTBEAT':
            self._handle_heartbeat(msg)
        elif msg_type == 'SYSTEM_TIME':
            pass  # Could update ROS2 clock
        elif msg_type == 'SYS_STATUS':
            self._handle_sys_status(msg)
        elif msg_type == 'ATTITUDE':
            self._handle_attitude(msg)
        elif msg_type == 'GLOBAL_POSITION_INT':
            self._handle_global_position(msg)
        elif msg_type == 'RANGEFINDER':
            self._handle_rangefinder(msg)
        elif msg_type == 'BATTERY_STATUS':
            self._handle_battery_status(msg)
        elif msg_type == 'SERVO_OUTPUT_RAW':
            self._handle_servo_output(msg)

    def _handle_heartbeat(self, msg):
        """Handle HEARTBEAT message"""
        self.system_status = msg.system_status
        # Could update ROS status here

    def _handle_sys_status(self, msg):
        """Handle SYS_STATUS message - battery, errors, etc."""
        # msg.voltage_battery (millivolts)
        # msg.battery_remaining (0-100%)
        # msg.errors_comm, msg.errors_count1, etc.
        pass

    def _handle_attitude(self, msg):
        """Handle ATTITUDE message - roll, pitch, yaw"""
        # msg.roll, msg.pitch, msg.yaw (radians)
        # msg.rollspeed, msg.pitchspeed, msg.yawspeed (rad/s)
        pass

    def _handle_global_position(self, msg):
        """Handle GLOBAL_POSITION_INT message"""
        # msg.lat, msg.lon (degrees * 1e7)
        # msg.alt (mm above mean sea level)
        # msg.relative_alt (mm above home)
        pass

    def _handle_rangefinder(self, msg):
        """Handle RANGEFINDER message (depth sensor)"""
        # msg.distance (m) - actual depth
        # msg.voltage (mV)
        pass

    def _handle_battery_status(self, msg):
        """Handle BATTERY_STATUS message"""
        # msg.voltages[0] (mV)
        # msg.current_battery (cA = centamps, divide by 100 for amps)
        pass

    def _handle_servo_output(self, msg):
        """Handle SERVO_OUTPUT_RAW message"""
        # msg.servo1_raw through servo8_raw (PWM values in microseconds, 1000-2000)
        # This confirms thruster commands were received
        if hasattr(msg, 'servo1_raw'):
            self.current_servo_values[0] = msg.servo1_raw
        if hasattr(msg, 'servo2_raw'):
            self.current_servo_values[1] = msg.servo2_raw
        # ... etc for other servos

    def thruster_callback(self, msg):
        """Receive thruster commands and send to autopilot via MAVLink"""
        if not self.connected or not self.armed:
            return

        self.last_thruster_command = msg
        self._send_servo_commands(msg)

    def _send_servo_commands(self, thruster_cmd):
        """Convert ThrusterCommand to MAVLink SERVO_CONTROL messages"""
        if not self.mav_connection:
            return

        try:
            # Convert normalized thruster commands (-1.0 to 1.0) to PWM (1100-1900 microseconds)
            # 1500 = neutral (0.0), 1100 = full reverse (-1.0), 1900 = full forward (1.0)
            thrusters = [
                thruster_cmd.thruster_front_left,
                thruster_cmd.thruster_front_right,
                thruster_cmd.thruster_back_left,
                thruster_cmd.thruster_back_right,
                thruster_cmd.thruster_vertical_left,
                thruster_cmd.thruster_vertical_right,
            ]

            # Send servo commands for mapped channels
            for channel_idx, thruster_value in enumerate(thrusters):
                if channel_idx < len(self.servo_channels):
                    servo_channel = self.servo_channels[channel_idx]
                    pwm_value = self._normalize_to_pwm(thruster_value)

                    # Send via SERVO_CONTROL (may need SERVO_CONTROL_PROP for autonomous control)
                    self.mav_connection.mav.servo_control_send(
                        time_boot_ms=int(time.time() * 1000),
                        port=0,
                        servo1_raw=pwm_value if servo_channel == 1 else 65535,
                        servo2_raw=pwm_value if servo_channel == 2 else 65535,
                        servo3_raw=pwm_value if servo_channel == 3 else 65535,
                        servo4_raw=pwm_value if servo_channel == 4 else 65535,
                        servo5_raw=pwm_value if servo_channel == 5 else 65535,
                        servo6_raw=pwm_value if servo_channel == 6 else 65535,
                        servo7_raw=65535,
                        servo8_raw=65535,
                    )

        except Exception as e:
            self.get_logger().warn(f'Error sending servo commands: {e}')

    def _normalize_to_pwm(self, value):
        """Convert normalized value (-1.0 to 1.0) to PWM microseconds (1100-1900)"""
        value = max(-1.0, min(1.0, value))  # Clamp to [-1, 1]
        pwm = 1500 + (value * 400)  # 1500 is neutral, ±400 is range
        return int(pwm)

    def arm_autopilot(self):
        """Send ARM command to autopilot"""
        if not self.mav_connection:
            self.get_logger().error('No MAVLink connection')
            return False

        try:
            # Send COMMAND_LONG to ARM_DISARM (cmd 400)
            # param1 = 1 to arm, 0 to disarm
            self.mav_connection.mav.command_long_send(
                target_system=self.system_id,
                target_component=self.component_id,
                command=400,  # MAV_CMD_COMPONENT_ARM_DISARM
                confirmation=0,
                param1=1.0,  # Arm
                param2=0, param3=0, param4=0, param5=0, param6=0, param7=0
            )

            self.armed = True
            self.get_logger().info('ARM command sent')
            return True

        except Exception as e:
            self.get_logger().error(f'Failed to arm: {e}')
            return False

    def disarm_autopilot(self):
        """Send DISARM command to autopilot"""
        if not self.mav_connection:
            self.get_logger().error('No MAVLink connection')
            return False

        try:
            # Send COMMAND_LONG to ARM_DISARM (cmd 400)
            # param1 = 0 to disarm
            self.mav_connection.mav.command_long_send(
                target_system=self.system_id,
                target_component=self.component_id,
                command=400,  # MAV_CMD_COMPONENT_ARM_DISARM
                confirmation=0,
                param1=0.0,  # Disarm
                param2=0, param3=0, param4=0, param5=0, param6=0, param7=0
            )

            self.armed = False
            self.get_logger().info('DISARM command sent')
            return True

        except Exception as e:
            self.get_logger().error(f'Failed to disarm: {e}')
            return False

    def destroy_node(self):
        """Cleanup on shutdown"""
        self.running = False
        if self.mav_connection:
            self.mav_connection.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MAVLinkBridgeNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


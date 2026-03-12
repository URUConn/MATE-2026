"""
MAVROS Bridge Node - Interfaces between ROS 2 thruster commands and MAVROS RC Override.
Runs on the LattePanda (onboard computer).

Converts ThrusterCommand messages to MAVROS RC Override commands for the PIX6 flight controller.
This allows the gamepad/keyboard input from the laptop to drive the ROV thrusters via ArduSub.

Note: Requires MAVROS2 to be installed and the PIX6 connected via USB.
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ThrusterCommand
from mavros_msgs.msg import OverrideRCIn
from std_msgs.msg import Bool
import threading
import time


class MavrosBridgeNode(Node):
    """
    Bridges thruster commands to MAVROS RC Override.
    
    ArduSub uses 6 channels for ROV control (channels 1-6):
    - Channel 1: Roll (1000-2000 µs)
    - Channel 2: Pitch (1000-2000 µs)
    - Channel 3: Throttle/Vertical (1000-2000 µs)
    - Channel 4: Yaw (1000-2000 µs)
    - Channel 5: Manual Control (1100 = manual, 1000 = failsafe)
    - Channel 6: Mode Selection or custom function
    
    This node converts normalized thruster values (-1.0 to 1.0) to RC PWM values (1000-2000 µs).
    """

    def __init__(self):
        super().__init__('mavros_bridge_node')

        # Parameters
        self.declare_parameter('armed', False)
        self.declare_parameter('fcu_port', '/dev/ttyACM0')
        self.declare_parameter('fcu_baud', 115200)
        self.declare_parameter('thrust_scaling', 1.0)
        self.declare_parameter('rc_min_pwm', 1000)
        self.declare_parameter('rc_max_pwm', 2000)
        self.declare_parameter('rc_center_pwm', 1500)

        self.armed = self.get_parameter('armed').value
        self.fcu_port = self.get_parameter('fcu_port').value
        self.fcu_baud = self.get_parameter('fcu_baud').value
        self.thrust_scaling = self.get_parameter('thrust_scaling').value
        self.rc_min_pwm = self.get_parameter('rc_min_pwm').value
        self.rc_max_pwm = self.get_parameter('rc_max_pwm').value
        self.rc_center_pwm = self.get_parameter('rc_center_pwm').value

        # Publishers and subscribers
        self.rc_override_pub = self.create_publisher(OverrideRCIn, '/mavros/rc/override', 10)
        self.thruster_sub = self.create_subscription(
            ThrusterCommand,
            '/rov/thruster_command',
            self.thruster_callback,
            10
        )
        self.arm_sub = self.create_subscription(
            Bool,
            '/rov/arm_cmd',
            self.arm_callback,
            10
        )

        # State tracking
        self.last_command_time = None
        self.connection_timeout = 5.0  # seconds
        self.fcu_connected = False

        # Initial state - all channels to neutral
        self.rc_channels = [
            self.rc_center_pwm,  # Channel 1 - Roll
            self.rc_center_pwm,  # Channel 2 - Pitch
            self.rc_center_pwm,  # Channel 3 - Throttle (vertical)
            self.rc_center_pwm,  # Channel 4 - Yaw
            1100,                 # Channel 5 - Manual control (1100 = manual mode)
            self.rc_center_pwm,  # Channel 6 - Custom
        ]

        # Check connection status periodically
        self.create_timer(1.0, self.check_connection)

        self.get_logger().info('MAVROS Bridge Node initialized')
        self.get_logger().info(f'FCU Port: {self.fcu_port} @ {self.fcu_baud} baud')
        self.get_logger().info(f'Armed: {self.armed}')
        self.get_logger().info('Arm/disarm topic: /rov/arm_cmd (std_msgs/Bool)')
        self.get_logger().info('Waiting for thruster commands...')

    def arm_callback(self, msg: Bool):
        """Arm or disarm runtime command from control laptop."""
        requested = bool(msg.data)
        if requested == self.armed:
            return

        self.armed = requested
        state = 'ARMED' if self.armed else 'DISARMED'
        self.get_logger().warn(f'Runtime arm state changed: {state}')

        if not self.armed:
            self.publish_neutral_override()

    def publish_neutral_override(self):
        """Send neutral RC values immediately when disarmed or timed out."""
        self.rc_channels = [
            self.rc_center_pwm,
            self.rc_center_pwm,
            self.rc_center_pwm,
            self.rc_center_pwm,
            1100,
            self.rc_center_pwm,
        ]
        rc_msg = OverrideRCIn()
        rc_msg.channels = self.rc_channels
        self.rc_override_pub.publish(rc_msg)

    def thruster_callback(self, msg: ThrusterCommand):
        """
        Convert ThrusterCommand to MAVROS RC Override.
        
        Thruster layout assumption (6-thruster vectored ROV):
        - Front left, front right: forward/backward + strafe + yaw
        - Back left, back right: forward/backward + strafe + yaw
        - Vertical left, vertical right: up/down
        """
        if not self.armed:
            return

        self.last_command_time = time.time()

        # Extract thrust values (normalized -1.0 to 1.0)
        fl = msg.thruster_front_left * self.thrust_scaling
        fr = msg.thruster_front_right * self.thrust_scaling
        bl = msg.thruster_back_left * self.thrust_scaling
        br = msg.thruster_back_right * self.thrust_scaling
        vl = msg.thruster_vertical_left * self.thrust_scaling
        vr = msg.thruster_vertical_right * self.thrust_scaling

        # Compute directional commands from thruster outputs
        # Roll (Channel 1): Front left vs Front right difference
        roll = ((fl + bl) - (fr + br)) / 2.0
        
        # Pitch (Channel 2): (Front - Back) for pitch control
        pitch = ((fl + fr) - (bl + br)) / 2.0
        
        # Throttle/Vertical (Channel 3): Average of vertical thrusters
        throttle = (vl + vr) / 2.0
        
        # Yaw (Channel 4): Front left + back right vs Front right + back left
        yaw = ((fl - fr) + (br - bl)) / 2.0

        # Clamp values to [-1.0, 1.0]
        roll = max(-1.0, min(1.0, roll))
        pitch = max(-1.0, min(1.0, pitch))
        throttle = max(-1.0, min(1.0, throttle))
        yaw = max(-1.0, min(1.0, yaw))

        # Convert normalized values (-1.0 to 1.0) to RC PWM values (1000-2000 µs)
        # Center is 1500, min is 1000, max is 2000
        self.rc_channels[0] = int(self.rc_center_pwm + (roll * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[1] = int(self.rc_center_pwm + (pitch * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[2] = int(self.rc_center_pwm + (throttle * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[3] = int(self.rc_center_pwm + (yaw * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[4] = 1100  # Channel 5: Manual control
        self.rc_channels[5] = self.rc_center_pwm  # Channel 6: Custom

        # Clamp to valid PWM range
        for i in range(6):
            self.rc_channels[i] = max(self.rc_min_pwm, min(self.rc_max_pwm, self.rc_channels[i]))

        # Publish RC override
        rc_msg = OverrideRCIn()
        rc_msg.channels = self.rc_channels
        self.rc_override_pub.publish(rc_msg)

        # Log at debug level to reduce spam
        self.get_logger().debug(
            f'RC Override - Ch1:{self.rc_channels[0]} Ch2:{self.rc_channels[1]} '
            f'Ch3:{self.rc_channels[2]} Ch4:{self.rc_channels[3]}'
        )

    def check_connection(self):
        """Check if we're receiving commands and if FCU is connected"""
        if self.last_command_time is None:
            if not self.fcu_connected:
                self.get_logger().info('Waiting for thruster commands and FCU connection...')
            self.fcu_connected = False
            return

        time_since_last_command = time.time() - self.last_command_time

        if time_since_last_command > self.connection_timeout:
            # No commands received recently - send neutral commands to prevent drift
            if self.armed:
                self.publish_neutral_override()
            self.fcu_connected = False
            self.get_logger().warn('No thruster commands received (timeout)')
            return

        if not self.fcu_connected:
            self.get_logger().info('✓ Connected to MAVROS and receiving commands')
            self.fcu_connected = True


def main(args=None):
    rclpy.init(args=args)
    node = MavrosBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


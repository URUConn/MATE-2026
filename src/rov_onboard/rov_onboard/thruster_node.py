"""
Thruster Node - Receives thruster commands from control laptop and drives motors via MAVROS.
Runs on the LattePanda (onboard computer).
Converts normalized thruster values (-1.0 to 1.0) to MAVROS actuator commands.
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ThrusterCommand
from std_msgs.msg import Bool
from mavros_msgs.msg import ActuatorControl
from mavros_msgs.msg import State
import time


class ThrusterNode(Node):
    """
    Converts ThrusterCommand messages to MAVROS ActuatorControl for direct motor control.
    
    Thruster mapping (6-thruster vectored ROV):
    - Channel 0: Front left motor
    - Channel 1: Front right motor
    - Channel 2: Back left motor
    - Channel 3: Back right motor
    - Channel 4: Vertical left motor
    - Channel 5: Vertical right motor
    - Channels 6-7: Reserved/unused
    """

    def __init__(self):
        super().__init__('thruster_node')

        self.declare_parameter('armed', False)
        self.declare_parameter('thrust_scaling', 1.0)
        self.declare_parameter('fcu_timeout', 5.0)

        self.armed = self.get_parameter('armed').value
        self.thrust_scaling = self.get_parameter('thrust_scaling').value
        self.fcu_timeout = self.get_parameter('fcu_timeout').value

        # Publishers
        self.actuator_pub = self.create_publisher(
            ActuatorControl,
            '/mavros/actuator_control',
            10
        )

        # Subscribers
        self.subscription = self.create_subscription(
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
        self.mavros_state_sub = self.create_subscription(
            State,
            '/mavros/state',
            self.mavros_state_callback,
            10
        )
        self.mavros_state_sub_uas1 = self.create_subscription(
            State,
            '/uas1/mavros/state',
            self.mavros_state_callback,
            10
        )

        # State tracking
        self.fcu_connected = False
        self.last_command_time = None
        self.last_log_time = 0.0
        self.connected_namespaces = {'mavros': False, 'uas1': False}

        self.get_logger().info('Thruster node started (disarmed by default)')
        self.get_logger().info('Arm/disarm topic: /rov/arm_cmd (std_msgs/Bool)')
        self.get_logger().info('Motor control via MAVROS ActuatorControl')

    def mavros_state_callback(self, msg: State):
        """Track FCU connection status from either namespace."""
        # Update both namespace tracking and combined connection status
        if msg._connection.node_name == '/mavros/mavros' or '/mavros/state' in str(msg):
            self.connected_namespaces['mavros'] = bool(msg.connected)
        else:
            self.connected_namespaces['uas1'] = bool(msg.connected)
        
        # Connection is true if either namespace is connected
        self.fcu_connected = any(self.connected_namespaces.values())
        
        now = time.time()
        if self.fcu_connected and now - self.last_log_time > 10.0:
            self.get_logger().info('FCU connected via MAVROS')
            self.last_log_time = now
        elif not self.fcu_connected and now - self.last_log_time > 10.0:
            self.get_logger().warn('FCU disconnected - motors will not respond')
            self.last_log_time = now

    def arm_callback(self, msg: Bool):
        """Handle arm/disarm commands."""
        requested = bool(msg.data)
        if requested == self.armed:
            return
        self.armed = requested
        state = 'ARMED' if self.armed else 'DISARMED'
        self.get_logger().warn(f'Thruster state changed: {state}')

        if not self.armed:
            # Send neutral command when disarmed for safety
            self.publish_neutral_actuators()

    def publish_neutral_actuators(self):
        """Send neutral (zero thrust) actuator command."""
        msg = ActuatorControl()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.group_mix = 0  # Group 0 for all motors
        msg.controls = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.actuator_pub.publish(msg)

    def thruster_callback(self, msg: ThrusterCommand):
        """Convert ThrusterCommand to MAVROS ActuatorControl."""
        if not self.armed:
            return

        if not self.fcu_connected:
            now = time.time()
            if now - self.last_log_time > 3.0:
                self.get_logger().warn('FCU not connected - thruster commands ignored')
                self.last_log_time = now
            return

        self.last_command_time = time.time()

        # Extract normalized thrust values (-1.0 to 1.0) and apply scaling
        fl = msg.thruster_front_left * self.thrust_scaling
        fr = msg.thruster_front_right * self.thrust_scaling
        bl = msg.thruster_back_left * self.thrust_scaling
        br = msg.thruster_back_right * self.thrust_scaling
        vl = msg.thruster_vertical_left * self.thrust_scaling
        vr = msg.thruster_vertical_right * self.thrust_scaling

        # Clamp all values to [-1.0, 1.0] range
        fl = max(-1.0, min(1.0, fl))
        fr = max(-1.0, min(1.0, fr))
        bl = max(-1.0, min(1.0, bl))
        br = max(-1.0, min(1.0, br))
        vl = max(-1.0, min(1.0, vl))
        vr = max(-1.0, min(1.0, vr))

        # Build MAVROS ActuatorControl message
        # Channels 0-5 map to our 6 thrusters
        actuator_msg = ActuatorControl()
        actuator_msg.header.stamp = self.get_clock().now().to_msg()
        actuator_msg.group_mix = 0  # Group 0: standard multirotor/vectored
        actuator_msg.controls = [fl, fr, bl, br, vl, vr, 0.0, 0.0]

        self.actuator_pub.publish(actuator_msg)

        # Log at debug level to reduce spam
        self.get_logger().debug(
            f'Actuators - FL:{fl:.2f} FR:{fr:.2f} BL:{bl:.2f} BR:{br:.2f} VL:{vl:.2f} VR:{vr:.2f}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = ThrusterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

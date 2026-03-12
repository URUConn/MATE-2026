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
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import time


class ThrusterNode(Node):
    """
    Converts ThrusterCommand messages to MAVROS ActuatorControl for direct motor control.
    
    Thruster mapping (8-thruster vectored ROV with 4 vertical thrusters):
    - Channel 0: Front left motor (horizontal)
    - Channel 1: Front right motor (horizontal)
    - Channel 2: Back left motor (horizontal)
    - Channel 3: Back right motor (horizontal)
    - Channel 4: Vertical front left motor
    - Channel 5: Vertical front right motor
    - Channel 6: Vertical back left motor
    - Channel 7: Vertical back right motor
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

        # MAVROS state is typically published as BEST_EFFORT.
        mavros_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        self.mavros_state_sub = self.create_subscription(
            State,
            '/mavros/state',
            lambda msg: self.mavros_state_callback(msg, 'mavros'),
            mavros_qos,
        )
        self.mavros_state_sub_uas1 = self.create_subscription(
            State,
            '/uas1/mavros/state',
            lambda msg: self.mavros_state_callback(msg, 'uas1'),
            mavros_qos,
        )

        # State tracking
        self.fcu_connected = False
        self.last_command_time = None
        self.last_log_time = 0.0
        self.connected_namespaces = {'mavros': False, 'uas1': False}
        self._missing_thruster_fields_logged = set()

        self.get_logger().info('Thruster node started (disarmed by default)')
        self.get_logger().info('Arm/disarm topic: /rov/arm_cmd (std_msgs/Bool)')
        self.get_logger().info('Motor control via MAVROS ActuatorControl')

    def mavros_state_callback(self, msg: State, source: str):
        """Track FCU connection status from either namespace."""
        self.connected_namespaces[source] = bool(msg.connected)

        # Connection is true if either namespace is connected
        self.fcu_connected = any(self.connected_namespaces.values())

        now = time.time()
        if self.fcu_connected and now - self.last_log_time > 10.0:
            connected_sources = [name for name, connected in self.connected_namespaces.items() if connected]
            self.get_logger().info(f'FCU connected via MAVROS ({", ".join(connected_sources)})')
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
        self.get_logger().info(f'Thruster state changed: {state}')

        # Always send neutral command when disarmed for safety
        # This is critical to stop all motor movement immediately
        if not self.armed:
            self.publish_neutral_actuators()
            self.get_logger().warn('DISARM: Sending neutral actuators command')

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
        # Horizontal thrusters
        fl = msg.thruster_front_left * self.thrust_scaling
        fr = msg.thruster_front_right * self.thrust_scaling
        bl = msg.thruster_back_left * self.thrust_scaling
        br = msg.thruster_back_right * self.thrust_scaling
        # Vertical thrusters (4 vertical thrusters)
        vfl = self._get_thruster_value(msg, 'thruster_vertical_front_left', 'vertical_front_left') * self.thrust_scaling
        vfr = self._get_thruster_value(msg, 'thruster_vertical_front_right', 'vertical_front_right') * self.thrust_scaling
        vbl = self._get_thruster_value(msg, 'thruster_vertical_back_left', 'vertical_back_left') * self.thrust_scaling
        vbr = self._get_thruster_value(msg, 'thruster_vertical_back_right', 'vertical_back_right') * self.thrust_scaling

        # Clamp all values to [-1.0, 1.0] range
        fl = max(-1.0, min(1.0, fl))
        fr = max(-1.0, min(1.0, fr))
        bl = max(-1.0, min(1.0, bl))
        br = max(-1.0, min(1.0, br))
        vfl = max(-1.0, min(1.0, vfl))
        vfr = max(-1.0, min(1.0, vfr))
        vbl = max(-1.0, min(1.0, vbl))
        vbr = max(-1.0, min(1.0, vbr))

        # Build MAVROS ActuatorControl message
        # Channels 0-7 map to our 8 thrusters
        actuator_msg = ActuatorControl()
        actuator_msg.header.stamp = self.get_clock().now().to_msg()
        actuator_msg.group_mix = 0  # Group 0: standard multirotor/vectored
        actuator_msg.controls = [fl, fr, bl, br, vfl, vfr, vbl, vbr]

        self.actuator_pub.publish(actuator_msg)

        # Log at debug level to reduce spam
        self.get_logger().debug(
            f'Actuators - FL:{fl:.2f} FR:{fr:.2f} BL:{bl:.2f} BR:{br:.2f} '
            f'VFL:{vfl:.2f} VFR:{vfr:.2f} VBL:{vbl:.2f} VBR:{vbr:.2f}'
        )

    def _get_thruster_value(self, msg: ThrusterCommand, canonical_name: str, legacy_name: str) -> float:
        if hasattr(msg, canonical_name):
            return float(getattr(msg, canonical_name))
        if hasattr(msg, legacy_name):
            return float(getattr(msg, legacy_name))

        key = f'{canonical_name}|{legacy_name}'
        if key not in self._missing_thruster_fields_logged:
            self.get_logger().error(
                f'ThrusterCommand missing expected fields: {canonical_name} or {legacy_name}. Using 0.0.'
            )
            self._missing_thruster_fields_logged.add(key)
        return 0.0


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

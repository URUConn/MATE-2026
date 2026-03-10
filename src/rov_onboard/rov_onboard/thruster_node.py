"""
Thruster Node - Receives thruster commands and sends to MAVLink bridge.
Runs on the LattePanda (onboard computer).
Commands are forwarded to the MAVLink bridge, which handles communication with ArduSub autopilot.
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ThrusterCommand


class ThrusterNode(Node):
    def __init__(self):
        super().__init__('thruster_node')

        self.declare_parameter('armed', False)
        self.armed = self.get_parameter('armed').value

        # Subscribe to thruster commands from gamepad/control
        self.subscription = self.create_subscription(
            ThrusterCommand,
            '/rov/thruster_command',
            self.thruster_callback,
            10
        )

        self.get_logger().info('Thruster node started (disarmed by default)')
        self.get_logger().info('Commands will be forwarded to MAVLink bridge for ArduSub autopilot')

    def thruster_callback(self, msg):
        """
        Receive thruster commands from control station.
        The MAVLink bridge node subscribes to the same topic and sends
        commands to the autopilot via MAVLink/SERVO_CONTROL messages.

        This node primarily logs for debugging; actual thruster control
        happens in the MAVLink bridge node.
        """
        if not self.armed:
            self.get_logger().debug('Received thruster command but ROV is disarmed - ignoring')
            return

        # Log current command (debug)
        self.get_logger().debug(
            f'Thruster command received - FL={msg.thruster_front_left:.2f} '
            f'FR={msg.thruster_front_right:.2f} '
            f'BL={msg.thruster_back_left:.2f} '
            f'BR={msg.thruster_back_right:.2f} '
            f'VL={msg.thruster_vertical_left:.2f} '
            f'VR={msg.thruster_vertical_right:.2f}'
        )
        # MAVLink bridge node will also receive and process this message


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

"""Toggle crab detection ON/OFF by pressing C on the keyboard."""

import threading, sys, termios, tty
import rclpy
from rclpy.node import Node
from rov_msgs.msg import CrabClassifyTrigger


class CrabTriggerNode(Node):

    def __init__(self):
        super().__init__('crab_trigger_node')
        self.declare_parameter('trigger_topic', '/rov/crab/trigger')
        topic = self.get_parameter('trigger_topic').value

        self.pub     = self.create_publisher(CrabClassifyTrigger, topic, 10)
        self._active = False

        self.get_logger().info(
            "Crab trigger ready. Press 'C' to toggle ON/OFF. Ctrl+C to quit."
        )
        threading.Thread(target=self._keyboard_loop, daemon=True).start()

    def _publish(self, active: bool):
        msg             = CrabClassifyTrigger()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.active      = active
        self.pub.publish(msg)
        self.get_logger().info(f'Detector {"ON" if active else "OFF"}')

    def _keyboard_loop(self):
        fd  = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while rclpy.ok():
                ch = sys.stdin.read(1).lower()
                if ch == 'c':
                    self._active = not self._active   # TOGGLE
                    self._publish(self._active)
                elif ch == '\x03':                    # Ctrl+C
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main(args=None):
    rclpy.init(args=args)
    node = CrabTriggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
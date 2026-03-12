"""
Status Node - Publishes overall ROV health/status information.
Runs on the LattePanda (onboard computer).
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import RovStatus
from std_msgs.msg import Bool, String
from mavros_msgs.msg import State
import time


class StatusNode(Node):
    def __init__(self):
        super().__init__('status_node')

        self.declare_parameter('publish_rate', 1.0)
        publish_rate = self.get_parameter('publish_rate').value

        self.publisher = self.create_publisher(RovStatus, '/rov/status', 10)
        self.arm_sub = self.create_subscription(Bool, '/rov/arm_cmd', self.arm_callback, 10)
        self.input_mode_sub = self.create_subscription(String, '/rov/input_mode_state', self.mode_callback, 10)
        self.mavros_state_sub = self.create_subscription(State, '/mavros/state', self.mavros_state_callback, 10)

        self.start_time = time.time()
        self.current_armed = False
        self.current_mode = 'manual'
        self.fcu_connected = False
        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.publish_status)

        self.get_logger().info('Status node started')

    def publish_status(self):
        msg = RovStatus()
        msg.armed = self.current_armed
        msg.leak_detected = False
        msg.mode = self.current_mode
        msg.cpu_temperature = self._read_cpu_temp()
        msg.uptime_seconds = float(time.time() - self.start_time)

        self.publisher.publish(msg)

    def arm_callback(self, msg: Bool):
        self.current_armed = bool(msg.data)

    def mode_callback(self, msg: String):
        mode = msg.data.strip().lower()
        if mode in ('keyboard', 'xbox'):
            self.current_mode = mode

    def mavros_state_callback(self, msg: State):
        # Prefer FCU truth when available.
        self.fcu_connected = bool(msg.connected)
        self.current_armed = bool(msg.armed)

    def _read_cpu_temp(self):
        """Read CPU temperature on Linux. Returns 0.0 on failure."""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return float(f.read().strip()) / 1000.0
        except Exception:
            return 0.0


def main(args=None):
    rclpy.init(args=args)
    node = StatusNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

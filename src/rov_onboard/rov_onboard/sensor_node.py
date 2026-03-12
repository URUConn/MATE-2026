"""
Sensor Node - Reads sensors and publishes data to the control laptop.
Runs on the LattePanda (onboard computer).
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import SensorData
from sensor_msgs.msg import Imu, BatteryState
import math


class SensorNode(Node):
    def __init__(self):
        super().__init__('sensor_node')

        self.declare_parameter('publish_rate', 10.0)
        publish_rate = self.get_parameter('publish_rate').value

        self.publisher = self.create_publisher(SensorData, '/rov/sensor_data', 10)
        self.imu_sub = self.create_subscription(Imu, '/mavros/imu/data', self.imu_callback, 10)
        self.battery_sub = self.create_subscription(BatteryState, '/mavros/battery', self.battery_callback, 10)

        self.heading_deg = 0.0
        self.pitch_deg = 0.0
        self.roll_deg = 0.0
        self.battery_voltage = 0.0
        self.has_imu = False
        self.has_battery = False

        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.publish_sensors)

        self.get_logger().info(f'Sensor node started at {publish_rate} Hz')

    def imu_callback(self, msg: Imu):
        qx = msg.orientation.x
        qy = msg.orientation.y
        qz = msg.orientation.z
        qw = msg.orientation.w

        # Quaternion -> roll, pitch, yaw (radians)
        sinr_cosp = 2.0 * (qw * qx + qy * qz)
        cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        self.roll_deg = math.degrees(roll)
        self.pitch_deg = math.degrees(pitch)
        # Convert yaw to compass-like heading [0, 360)
        self.heading_deg = (math.degrees(yaw) + 360.0) % 360.0
        self.has_imu = True

    def battery_callback(self, msg: BatteryState):
        self.battery_voltage = float(msg.voltage)
        self.has_battery = True

    def publish_sensors(self):
        msg = SensorData()

        # These can be replaced with dedicated depth/temperature sensors when wired.
        msg.depth = 0.0
        msg.temperature = 0.0
        msg.heading = float(self.heading_deg)
        msg.pitch = float(self.pitch_deg)
        msg.roll = float(self.roll_deg)
        msg.battery_voltage = float(self.battery_voltage)

        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SensorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

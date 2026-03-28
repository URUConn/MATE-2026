"""
Arm Encoder Bridge Node

This node accepts encoder values from a laptop-side source node and publishes
servo angle commands for the onboard arm controller.
"""

from typing import List

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ArmServoCommand
from std_msgs.msg import Float32MultiArray


DEFAULT_AXIS_NAMES = [
    'base',
    'shoulder',
    'elbow',
    'wrist_pitch',
    'wrist_roll',
    'wrist_yaw',
    'tool_rotate',
    'gripper',
]


class ArmEncoderBridgeNode(Node):
    """
    Arm Encoder Bridge Node
    """
    def __init__(self) -> None:
        """
        Constructor
        """
        super().__init__('arm_encoder_bridge_node')

        self.declare_parameter('axis_count', 8)
        self.declare_parameter('input_topic', '/rov/arm/encoder_values')
        self.declare_parameter('output_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('scales', [1.0] * 8)
        self.declare_parameter('offsets_deg', [0.0] * 8)
        self.declare_parameter('servo_min_deg', [0.0] * 8)
        self.declare_parameter('servo_max_deg', [180.0] * 8)

        self.axis_count = int(self.get_parameter('axis_count').value)
        self.input_topic = str(self.get_parameter('input_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)

        self.axis_names = self._normalize_list(
            list(self.get_parameter('axis_names').value),
            DEFAULT_AXIS_NAMES,
            'axis_names',
        )
        self.scales = self._normalize_float_list(
            list(self.get_parameter('scales').value),
            [1.0] * self.axis_count,
            'scales',
        )
        self.offsets_deg = self._normalize_float_list(
            list(self.get_parameter('offsets_deg').value),
            [0.0] * self.axis_count,
            'offsets_deg',
        )
        self.servo_min_deg = self._normalize_float_list(
            list(self.get_parameter('servo_min_deg').value),
            [0.0] * self.axis_count,
            'servo_min_deg',
        )
        self.servo_max_deg = self._normalize_float_list(
            list(self.get_parameter('servo_max_deg').value),
            [180.0] * self.axis_count,
            'servo_max_deg',
        )

        self.publisher = self.create_publisher(ArmServoCommand, self.output_topic, 10)
        self.subscription = self.create_subscription(
            Float32MultiArray,
            self.input_topic,
            self._encoder_callback,
            10,
        )

        self.get_logger().info(
            f'Arm encoder bridge active: {self.input_topic} -> {self.output_topic} '
            f'({self.axis_count} axes)'
        )

    def _normalize_list(self, values: List[str], fallback: List[str], name: str) -> List[str]:
        """
        Normalizes a list of string parameters to match the expected axis count.
        :param values: The list of values to normalize.
        :param fallback: The fallback list to use if the input list is invalid.
        :param name: The name of the parameter (for logging purposes).
        :return: A list of strings normalized to the axis count.
        """
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return values[: self.axis_count]

    def _normalize_float_list(self, values: List[float], fallback: List[float], name: str) -> List[float]:
        """
        Normalizes a list of float values to match the expected axis count.
        :param values: The list of float values to normalize.
        :param fallback: The fallback list to use if the input list is invalid.
        :param name: The name of the parameter (for logging purposes).
        :return: A list of floats normalized to the axis count.
        """
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [float(v) for v in values[: self.axis_count]]

    def _encoder_callback(self, msg: Float32MultiArray) -> None:
        """
        Callback function executed when an encoder command is received.
        :param msg: The incoming message containing encoder values for each axis.
        :return: None
        """
        if len(msg.data) < self.axis_count:
            self.get_logger().warn(
                f'Expected {self.axis_count} encoder values, received {len(msg.data)}'
            )
            return

        command = ArmServoCommand()
        command.header.stamp = self.get_clock().now().to_msg()

        for index in range(self.axis_count):
            raw_value = float(msg.data[index])
            target = raw_value * self.scales[index] + self.offsets_deg[index]
            target = max(self.servo_min_deg[index], min(self.servo_max_deg[index], target))
            command.target_deg[index] = float(target)

        self.publisher.publish(command)


def main(args=None) -> None:
    """
    Main function
    :param args: Arguments passed from the command line.
    :return: None
    """
    rclpy.init(args=args)
    node = ArmEncoderBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


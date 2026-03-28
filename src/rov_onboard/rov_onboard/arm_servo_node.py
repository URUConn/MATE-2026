"""
Arm Servo Node

Subscribes to arm servo commands and writes angles to onboard servos using
PinPong when available.
"""

from typing import List

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ArmServoCommand


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


class ArmServoNode(Node):
    """
    Arm Servo Node
    """
    def __init__(self) -> None:
        """
        Constructor for Arm Servo Node
        """
        super().__init__('arm_servo_node')

        # Declare parameters with defaults
        self.declare_parameter('axis_count', 8)
        self.declare_parameter('command_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('servo_min_deg', [0.0] * 8)
        self.declare_parameter('servo_max_deg', [180.0] * 8)
        self.declare_parameter('neutral_deg', [90.0] * 8)
        self.declare_parameter('command_timeout_sec', 0.5)
        self.declare_parameter('use_pinpong', False)
        self.declare_parameter('pinpong_board', 'uno')
        self.declare_parameter('pinpong_port', '/dev/ttyUSB0')
        self.declare_parameter('servo_pins', [2, 3, 4, 5, 6, 7, 8, 9])

        self.axis_count = int(self.get_parameter('axis_count').value)
        self.command_topic = str(self.get_parameter('command_topic').value)
        self.command_timeout_sec = float(self.get_parameter('command_timeout_sec').value)
        self.use_pinpong = bool(self.get_parameter('use_pinpong').value)
        self.pinpong_board = str(self.get_parameter('pinpong_board').value)
        self.pinpong_port = str(self.get_parameter('pinpong_port').value)

        self.axis_names = self._normalize_list(
            list(self.get_parameter('axis_names').value),
            DEFAULT_AXIS_NAMES,
            'axis_names',
        )
        if len(self.axis_names) != self.axis_count:
            self.get_logger().warn(
                f"Configured axis_names length ({len(self.axis_names)}) does not match "
                f"axis_count ({self.axis_count})."
            )
        self.get_logger().debug(f"Arm servo axis order: {self.axis_names}")
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
        self.neutral_deg = self._normalize_float_list(
            list(self.get_parameter('neutral_deg').value),
            [90.0] * self.axis_count,
            'neutral_deg',
        )
        self.servo_pins = self._normalize_int_list(
            list(self.get_parameter('servo_pins').value),
            [2, 3, 4, 5, 6, 7, 8, 9],
            'servo_pins',
        )

        self._servo_driver = self._create_servo_driver()
        self._last_command_time = self.get_clock().now()
        self._timed_out = False

        # Subscribe to ROS topic
        self.subscription = self.create_subscription(
            ArmServoCommand,
            self.command_topic,
            self._command_callback,
            10,
        )

        # Start timeout timer
        self.timer = self.create_timer(0.1, self._check_timeout)

        self.get_logger().info(
            f'Arm servo node active on {self.command_topic} ({self.axis_count} axes)'
        )

    def _normalize_list(self, values: List[str], fallback: List[str], name: str) -> List[str]:
        """
        Normalizes a list parameter to match the expected axis count, using fallback values if necessary.
        :param values: The list of values to normalize.
        :param fallback: The fallback list to use if the input list is invalid.
        :param name: The name of the parameter (for logging purposes).
        :return: A normalized list of values.
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
        Normalizes a list of float values to match the expected axis count, using fallback values if necessary.
        :param values: The list of float values to normalize.
        :param fallback: The fallback list to use if the input list is invalid.
        :param name: The name of the parameter (for logging purposes).
        :return: A normalized list of float values.
        """

        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [float(v) for v in values[: self.axis_count]]

    def _normalize_int_list(self, values: List[int], fallback: List[int], name: str) -> List[int]:
        """
        Normalizes a list of integer values to match the expected axis count, using fallback values if necessary.
        :param values: The list of integer values to normalize.
        :param fallback: The fallback list to use if the input list is invalid.
        :param name: The name of the parameter (for logging purposes).
        :return: A normalized list of integer values.
        """
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [int(v) for v in values[: self.axis_count]]

    def _create_servo_driver(self):
        """
        Create the servo driver.
        :return: A list of servo objects if PinPong is available and enabled, otherwise None for dry-run mode.
        """

        # Check if pinpong is enabled in the config
        if not self.use_pinpong:
            self.get_logger().warn('use_pinpong=false, running in dry-run mode')
            return None

        try:
            from pinpong.board import Board, Servo

            Board(self.pinpong_board, self.pinpong_port).begin()
            servos = [Servo(pin) for pin in self.servo_pins]
            self.get_logger().info(
                f'PinPong ready on {self.pinpong_board} {self.pinpong_port} with pins {self.servo_pins}'
            )
            return servos
        except Exception as exc:
            self.get_logger().error(f'Failed to initialize PinPong: {exc}. Falling back to dry-run mode.')
            return None

    def _clamp_angle(self, index: int, angle: float) -> float:
        """
        Clamp angle to the defined range.
        :param index: The index of the servo axis.
        :param angle: The angle in degrees to clamp.
        :return: The clamped angle in degrees.
        """
        return max(self.servo_min_deg[index], min(self.servo_max_deg[index], angle))

    def _write_servo(self, index: int, angle_deg: float) -> None:
        """
        Write servo data.
        :param index: The index of the servo axis.
        :param angle_deg: The target angle in degrees to write to the servo.
        :return: None
        """
        angle_deg = self._clamp_angle(index, float(angle_deg))

        if self._servo_driver is None:
            return

        servo = self._servo_driver[index]
        if hasattr(servo, 'write_angle'):
            servo.write_angle(angle_deg)
        elif hasattr(servo, 'write'):
            servo.write(angle_deg)
        else:
            # Avoid raising here so a mismatched Servo API does not crash the node.
            # Log the error once and skip further writes.
            if not getattr(self, '_servo_api_error_logged', False):
                self.get_logger().error(
                    'Unsupported PinPong Servo API for servo index %d: expected write_angle() or write()',
                    index,
                )
                setattr(self, '_servo_api_error_logged', True)
            return

    def _command_callback(self, msg: ArmServoCommand) -> None:
        """
        Callback function that is called when a command is received.
        :param msg: The ArmServoCommand message containing the target angles for each servo axis.
        :return: None
        """
        self._last_command_time = self.get_clock().now()
        self._timed_out = False

        max_index = min(self.axis_count, len(msg.target_deg))
        for index in range(max_index):
            self._write_servo(index, msg.target_deg[index])

    def _check_timeout(self) -> None:
        """
        Check if the last command has timed out. If it has, drive all servos to the neutral position for safety.
        :return: None
        """
        elapsed = (self.get_clock().now() - self._last_command_time).nanoseconds / 1e9
        if elapsed <= self.command_timeout_sec:
            return

        if not self._timed_out:
            self.get_logger().warn(
                f'No arm command for {elapsed:.2f}s, driving to neutral pose for safety'
            )
            for index in range(self.axis_count):
                self._write_servo(index, self.neutral_deg[index])
            self._timed_out = True


def main(args=None) -> None:
    """
    Main entry point.
    :param args: Arguments passed from the command line.
    :return: None
    """
    rclpy.init(args=args)
    node = ArmServoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()



"""Subscribe to arm servo commands and drive servos on the onboard computer."""

from typing import List

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ArmServoCommand


DEFAULT_AXIS_NAMES = [
    'base',
    'shoulder',
    'elbow',
    'wrist_roll',
    'wrist_pitch',
    'wrist_yaw',
    'gripper',
]
DEFAULT_SERVO_MIN_DEG = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
DEFAULT_SERVO_MAX_DEG = [270.0, 357.0, 357.0, 270.0, 270.0, 360.0, 270.0]
DEFAULT_NEUTRAL_DEG = [82.5, 59.5, 59.5, 135.0, 135.0, 180.0, 90.0]
DEFAULT_SERVO_PINS = [2, 3, 4, 5, 6, 7, 8]


class ArmServoNode(Node):
    """Drive arm servos from `ArmServoCommand` topic values."""

    def __init__(self) -> None:
        super().__init__('arm_servo_node')

        self.declare_parameter('axis_count', 7)
        self.declare_parameter('command_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('servo_pins', DEFAULT_SERVO_PINS)
        self.declare_parameter('servo_min_deg', DEFAULT_SERVO_MIN_DEG)
        self.declare_parameter('servo_max_deg', DEFAULT_SERVO_MAX_DEG)
        self.declare_parameter('neutral_deg', DEFAULT_NEUTRAL_DEG)
        self.declare_parameter('command_timeout_sec', 0.5)
        self.declare_parameter('use_pinpong', False)
        self.declare_parameter('pinpong_platform', 'auto')

        self.axis_count = int(self.get_parameter('axis_count').value)
        self.axis_count = max(1, min(self.axis_count, len(DEFAULT_AXIS_NAMES)))
        self.command_topic = str(self.get_parameter('command_topic').value)
        self.command_timeout_sec = float(self.get_parameter('command_timeout_sec').value)
        self.use_pinpong = bool(self.get_parameter('use_pinpong').value)
        self.pinpong_platform = str(self.get_parameter('pinpong_platform').value)

        self.axis_names = self._normalize_list(
            list(self.get_parameter('axis_names').value),
            DEFAULT_AXIS_NAMES,
            'axis_names',
        )
        self.servo_pins = self._normalize_int_list(
            list(self.get_parameter('servo_pins').value),
            DEFAULT_SERVO_PINS,
            'servo_pins',
        )
        self.servo_min_deg = self._normalize_float_list(
            list(self.get_parameter('servo_min_deg').value),
            DEFAULT_SERVO_MIN_DEG,
            'servo_min_deg',
        )
        self.servo_max_deg = self._normalize_float_list(
            list(self.get_parameter('servo_max_deg').value),
            DEFAULT_SERVO_MAX_DEG,
            'servo_max_deg',
        )
        self.neutral_deg = self._normalize_float_list(
            list(self.get_parameter('neutral_deg').value),
            DEFAULT_NEUTRAL_DEG,
            'neutral_deg',
        )

        self._servo_driver = self._create_servo_driver()
        self._servo_api_error_logged = False
        self._last_command_time = self.get_clock().now()
        self._timed_out = False

        self.subscription = self.create_subscription(
            ArmServoCommand,
            self.command_topic,
            self._command_callback,
            10,
        )
        self.timer = self.create_timer(0.1, self._check_timeout)

        self.get_logger().info(
            f'Arm servo node active on {self.command_topic} ({self.axis_count} axes: {self.axis_names})'
        )

    def _normalize_list(self, values: List[str], fallback: List[str], name: str) -> List[str]:
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return values[: self.axis_count]

    def _normalize_float_list(self, values: List[float], fallback: List[float], name: str) -> List[float]:
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [float(v) for v in values[: self.axis_count]]

    def _normalize_int_list(self, values: List[int], fallback: List[int], name: str) -> List[int]:
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [int(v) for v in values[: self.axis_count]]

    def _build_servo(self, pin: int):
        """Create one Servo instance using API variants seen across PinPong versions."""
        from pinpong.board import Pin, Servo

        errors = []
        try:
            return Servo(pin)
        except Exception as exc:
            errors.append(f'Servo({pin}) -> {exc}')

        try:
            return Servo(Pin(pin))
        except Exception as exc:
            errors.append(f'Servo(Pin({pin})) -> {exc}')

        raise RuntimeError('; '.join(errors))

    def _create_servo_driver(self):
        if not self.use_pinpong:
            self.get_logger().warn('use_pinpong=false, running in dry-run mode')
            return None

        try:
            from pinpong.board import Board

            platform = self.pinpong_platform.strip()
            board = None
            if platform and platform.lower() != 'auto':
                try:
                    board = Board(platform)
                    board.begin()
                except Exception as exc:
                    self.get_logger().warn(
                        f'PinPong platform "{platform}" not supported ({exc}); trying auto-detect.'
                    )

            if board is None:
                board = Board()
                board.begin()

            servos = []
            for pin in self.servo_pins:
                try:
                    servos.append(self._build_servo(pin))
                except Exception as exc:
                    self.get_logger().error(f'Failed to initialize Servo on pin {pin}: {exc}')
                    servos.append(None)

            usable = sum(1 for servo in servos if servo is not None)
            if usable == 0:
                raise RuntimeError('No servo instances initialized')

            self.get_logger().info(
                f'PinPong ready in direct mode (platform={platform or "auto"}) '
                f'with pins {self.servo_pins} (usable channels: {usable}/{len(servos)})'
            )
            return servos
        except Exception as exc:
            self.get_logger().error(f'Failed to initialize PinPong: {exc}. Falling back to dry-run mode.')
            return None

    def _clamp_angle(self, index: int, angle: float) -> float:
        return max(self.servo_min_deg[index], min(self.servo_max_deg[index], angle))

    def _write_servo(self, index: int, angle_deg: float) -> None:
        angle_cmd = int(round(self._clamp_angle(index, float(angle_deg))))

        if self._servo_driver is None:
            return

        servo = self._servo_driver[index]
        if servo is None:
            return

        if hasattr(servo, 'write_angle'):
            servo.write_angle(angle_cmd)
            return
        if hasattr(servo, 'write'):
            servo.write(angle_cmd)
            return

        if not self._servo_api_error_logged:
            self.get_logger().error(
                f'Unsupported PinPong Servo API on axis {index}: expected write_angle() or write()'
            )
            self._servo_api_error_logged = True

    def _command_callback(self, msg: ArmServoCommand) -> None:
        self._last_command_time = self.get_clock().now()
        self._timed_out = False

        max_index = min(self.axis_count, len(msg.target_deg))
        if self._servo_driver is not None:
            max_index = min(max_index, len(self._servo_driver))

        for index in range(max_index):
            self._write_servo(index, msg.target_deg[index])

    def _check_timeout(self) -> None:
        elapsed = (self.get_clock().now() - self._last_command_time).nanoseconds / 1e9
        if elapsed <= self.command_timeout_sec or self._timed_out:
            return

        self.get_logger().warn(
            f'No arm command for {elapsed:.2f}s, driving to neutral pose for safety'
        )
        max_index = self.axis_count
        if self._servo_driver is not None:
            max_index = min(max_index, len(self._servo_driver))

        for index in range(max_index):
            self._write_servo(index, self.neutral_deg[index])
        self._timed_out = True


def main(args=None) -> None:
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


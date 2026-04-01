"""Subscribe to arm servo commands and drive servos on the onboard computer."""

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
        self.declare_parameter('axis_count', 7)
        self.declare_parameter('command_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('offsets_deg', [0.0] * 7)
        self.declare_parameter('continuous_axes', [False] * 7)
        self.declare_parameter('continuous_deadband', 0.08)
        self.declare_parameter('continuous_reverse_min_interval_sec', [0.0] * 7)
        self.declare_parameter('continuous_neutral_deg', [90.0] * 7)
        self.declare_parameter('continuous_span_deg', [90.0] * 7)
        self.declare_parameter('rate_limit_deg_per_sec', [0.0] * 7)
        self.declare_parameter('servo_min_deg', [0.0] * 7)
        self.declare_parameter('servo_max_deg', [180.0] * 7)
        self.declare_parameter('neutral_deg', [90.0] * 7)
        self.declare_parameter('command_timeout_sec', 0.5)
        self.declare_parameter('use_pinpong', False)
        self.declare_parameter('pinpong_platform', 'auto')
        # Deprecated compatibility params from external-board workflow.
        self.declare_parameter('pinpong_board', '')
        self.declare_parameter('pinpong_port', '')
        self.declare_parameter('servo_pins', [2, 3, 4, 5, 6, 7, 8])

        self.axis_count = int(self.get_parameter('axis_count').value)
        self.command_topic = str(self.get_parameter('command_topic').value)
        self.command_timeout_sec = float(self.get_parameter('command_timeout_sec').value)
        self.use_pinpong = bool(self.get_parameter('use_pinpong').value)
        self.pinpong_platform = str(self.get_parameter('pinpong_platform').value)
        self._legacy_pinpong_board = str(self.get_parameter('pinpong_board').value)
        self._legacy_pinpong_port = str(self.get_parameter('pinpong_port').value)
        if self._legacy_pinpong_board or self._legacy_pinpong_port:
            self.get_logger().warn(
                'pinpong_board/pinpong_port are deprecated and ignored. '
                f'Using direct PinPong platform mode: {self.pinpong_platform}.'
            )

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
        self.offsets_deg = self._normalize_float_list(
            list(self.get_parameter('offsets_deg').value),
            [0.0] * self.axis_count,
            'offsets_deg',
        )
        self.continuous_axes = self._normalize_bool_list(
            list(self.get_parameter('continuous_axes').value),
            [False] * self.axis_count,
            'continuous_axes',
        )
        self.continuous_deadband = float(self.get_parameter('continuous_deadband').value)
        self.continuous_reverse_min_interval_sec = self._normalize_float_list(
            list(self.get_parameter('continuous_reverse_min_interval_sec').value),
            [0.0] * self.axis_count,
            'continuous_reverse_min_interval_sec',
        )
        self.continuous_neutral_deg = self._normalize_float_list(
            list(self.get_parameter('continuous_neutral_deg').value),
            [90.0] * self.axis_count,
            'continuous_neutral_deg',
        )
        self.continuous_span_deg = self._normalize_float_list(
            list(self.get_parameter('continuous_span_deg').value),
            [90.0] * self.axis_count,
            'continuous_span_deg',
        )
        self.rate_limit_deg_per_sec = self._normalize_float_list(
            list(self.get_parameter('rate_limit_deg_per_sec').value),
            [0.0] * self.axis_count,
            'rate_limit_deg_per_sec',
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
        self.neutral_deg = self._normalize_float_list(
            list(self.get_parameter('neutral_deg').value),
            [90.0] * self.axis_count,
            'neutral_deg',
        )
        self.servo_pins = self._normalize_int_list(
            list(self.get_parameter('servo_pins').value),
            [2, 3, 4, 5, 6, 7, 8],
            'servo_pins',
        )

        self._servo_driver = self._create_servo_driver()
        self._last_command_time = self.get_clock().now()
        self._timed_out = False
        self._last_output_deg: List[float] = [float(self.neutral_deg[index]) for index in range(self.axis_count)]
        now_sec = self.get_clock().now().nanoseconds / 1e9
        self._last_output_time_sec: List[float] = [now_sec] * self.axis_count
        self._continuous_last_nonzero_sign: List[int] = [0] * self.axis_count
        self._continuous_last_nonzero_time_sec: List[float] = [now_sec] * self.axis_count

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

    def _build_servo(self, pin: int):
        """Create one Servo instance using API variants seen across PinPong versions."""
        from pinpong.board import Servo, Pin

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

    def _normalize_bool_list(self, values: List[bool], fallback: List[bool], name: str) -> List[bool]:
        """Normalize a bool parameter list to axis_count."""
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return [bool(v) for v in values[: self.axis_count]]

    def _continuous_command_to_angle(self, index: int, normalized_cmd: float) -> float:
        """Map normalized continuous-servo command [-1, 1] to servo driver angle."""
        now_sec = self.get_clock().now().nanoseconds / 1e9
        cmd = max(-1.0, min(1.0, float(normalized_cmd)))
        if abs(cmd) < self.continuous_deadband:
            cmd = 0.0

        sign = 0
        if cmd > 0.0:
            sign = 1
        elif cmd < 0.0:
            sign = -1

        if sign != 0:
            prev_sign = int(self._continuous_last_nonzero_sign[index])
            prev_time = float(self._continuous_last_nonzero_time_sec[index])
            min_interval = max(0.0, float(self.continuous_reverse_min_interval_sec[index]))

            if prev_sign != 0 and sign != prev_sign and (now_sec - prev_time) < min_interval:
                cmd = 0.0
            else:
                self._continuous_last_nonzero_sign[index] = sign
                self._continuous_last_nonzero_time_sec[index] = now_sec

        return self.continuous_neutral_deg[index] + cmd * self.continuous_span_deg[index]

    def _apply_rate_limit(self, index: int, target_deg: float) -> float:
        """Limit per-axis output slew in deg/s. <=0 disables limiting for that axis."""
        max_rate = float(self.rate_limit_deg_per_sec[index])
        now_sec = self.get_clock().now().nanoseconds / 1e9

        prev_deg = float(self._last_output_deg[index])
        prev_sec = float(self._last_output_time_sec[index])

        limited = float(target_deg)
        if max_rate > 0.0:
            dt = max(0.0, now_sec - prev_sec)
            max_delta = max_rate * dt
            delta = limited - prev_deg
            if delta > max_delta:
                limited = prev_deg + max_delta
            elif delta < -max_delta:
                limited = prev_deg - max_delta

        self._last_output_deg[index] = float(limited)
        self._last_output_time_sec[index] = now_sec
        return limited

    def _create_servo_driver(self):
        """
        Create the servo driver for direct onboard GPIO access.
        :return: A list of servo objects if PinPong is available and enabled, otherwise None for dry-run mode.
        """

        # Check if pinpong is enabled in the config
        if not self.use_pinpong:
            self.get_logger().warn('use_pinpong=false, running in dry-run mode')
            return None

        try:
            from pinpong.board import Board, Servo

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
                    self.get_logger().error(
                        f'Failed to initialize Servo on pin {pin}: {exc}'
                    )
                    servos.append(None)

            usable = sum(1 for servo in servos if servo is not None)
            if usable == 0:
                raise RuntimeError(
                    'No servo instances initialized. Check PinPong platform selection and pin support.'
                )
            self.get_logger().info(
                f'PinPong ready in direct mode (platform={platform or "auto"}) '
                f'with pins {self.servo_pins} (usable channels: {usable}/{len(servos)})'
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
        angle_deg = self._apply_rate_limit(index, angle_deg)
        angle_deg = self._clamp_angle(index, float(angle_deg))
        # Some PinPong backends expect integer degrees and fail on float math/bit ops.
        angle_cmd = int(round(angle_deg))

        if self._servo_driver is None:
            return

        servo = self._servo_driver[index]
        if servo is None:
            return
        if hasattr(servo, 'write_angle'):
            servo.write_angle(angle_cmd)
        elif hasattr(servo, 'write'):
            servo.write(angle_cmd)
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
            if self.continuous_axes[index]:
                target_deg = self._continuous_command_to_angle(index, msg.target_deg[index])
            else:
                target_deg = float(msg.target_deg[index]) + self.offsets_deg[index]
            self._write_servo(index, target_deg)

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
            # Use the number of available servo drivers when PinPong is enabled to
            # avoid indexing errors if axis_count and the driver list length differ.
            max_index = self.axis_count
            if self._servo_driver is not None:
                max_index = min(max_index, len(self._servo_driver))
            for index in range(max_index):
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


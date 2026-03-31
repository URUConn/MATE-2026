"""Bridge arm encoder and joystick inputs to servo commands."""

import glob
import time
from typing import List

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ArmServoCommand
from std_msgs.msg import Float32MultiArray


DEFAULT_AXIS_NAMES = [
    'base',
    'shoulder',
    'elbow',
    'wrist_roll',
    'wrist_pitch',
    'wrist_yaw',
    'gripper',
]

DEFAULT_JOINT_TO_SERVO_RATIO = [1.5454545455, 3.0, 3.0, 1.0, 1.0, 1.0, 1.0]
DEFAULT_JOINT_MIN_DEG = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
DEFAULT_JOINT_MAX_DEG = [165.0, 119.0, 119.0, 270.0, 270.0, 360.0, 180.0]
DEFAULT_POST_RATIO_JOINT_MIN_DEG = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
DEFAULT_POST_RATIO_JOINT_MAX_DEG = [165.0, 119.0, 119.0, 270.0, 270.0, 360.0, 180.0]
DEFAULT_SERVO_MIN_DEG = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
DEFAULT_SERVO_MAX_DEG = [270.0, 357.0, 357.0, 270.0, 270.0, 360.0, 270.0]


class ArmEncoderBridgeNode(Node):
    """Convert control-side inputs into `ArmServoCommand` targets."""

    def __init__(self) -> None:
        super().__init__('arm_encoder_bridge_node')

        self.declare_parameter('axis_count', 7)
        self.declare_parameter('encoder_axis_count', 5)
        self.declare_parameter('input_topic', '/rov/arm/encoder_values')
        self.declare_parameter('joystick_topic', '/rov/arm/joystick_values')
        self.declare_parameter('output_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('input_scales', [1.0] * 7)
        self.declare_parameter('input_offsets_deg', [0.0] * 7)
        self.declare_parameter('joint_to_servo_ratio', DEFAULT_JOINT_TO_SERVO_RATIO)
        self.declare_parameter('joint_min_deg', DEFAULT_JOINT_MIN_DEG)
        self.declare_parameter('joint_max_deg', DEFAULT_JOINT_MAX_DEG)
        self.declare_parameter('post_ratio_joint_min_deg', DEFAULT_POST_RATIO_JOINT_MIN_DEG)
        self.declare_parameter('post_ratio_joint_max_deg', DEFAULT_POST_RATIO_JOINT_MAX_DEG)
        self.declare_parameter('servo_min_deg', DEFAULT_SERVO_MIN_DEG)
        self.declare_parameter('servo_max_deg', DEFAULT_SERVO_MAX_DEG)
        self.declare_parameter('joystick_min_deg', DEFAULT_JOINT_MIN_DEG)
        self.declare_parameter('joystick_max_deg', DEFAULT_JOINT_MAX_DEG)
        self.declare_parameter('joystick_defaults', [0.0, 0.0])
        self.declare_parameter('use_serial_input', True)
        self.declare_parameter('serial_port', '/dev/ttyACM0')
        self.declare_parameter('serial_baud_rate', 921600)
        self.declare_parameter('serial_timeout_sec', 0.02)
        self.declare_parameter('serial_poll_sec', 0.01)
        self.declare_parameter('serial_reconnect_sec', 1.0)
        self.declare_parameter('serial_auto_discover', True)

        command_size = 8
        self.axis_count = int(self.get_parameter('axis_count').value)
        if self.axis_count < 1:
            self.get_logger().warn('axis_count must be >= 1, using 7')
            self.axis_count = 7
        if self.axis_count > command_size:
            self.get_logger().warn(
                f'axis_count {self.axis_count} exceeds ArmServoCommand size {command_size}, '
                f'using {command_size}'
            )
            self.axis_count = command_size

        self.encoder_axis_count = int(self.get_parameter('encoder_axis_count').value)
        self.encoder_axis_count = max(0, min(self.encoder_axis_count, self.axis_count))

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.joystick_topic = str(self.get_parameter('joystick_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        self.use_serial_input = bool(self.get_parameter('use_serial_input').value)
        self.serial_port = str(self.get_parameter('serial_port').value)
        self.serial_baud_rate = int(self.get_parameter('serial_baud_rate').value)
        self.serial_timeout_sec = float(self.get_parameter('serial_timeout_sec').value)
        self.serial_poll_sec = float(self.get_parameter('serial_poll_sec').value)
        self.serial_reconnect_sec = float(self.get_parameter('serial_reconnect_sec').value)
        self.serial_auto_discover = bool(self.get_parameter('serial_auto_discover').value)

        self.axis_names = self._normalize_list(
            list(self.get_parameter('axis_names').value),
            DEFAULT_AXIS_NAMES,
            'axis_names',
        )
        self.input_scales = self._normalize_float_list(
            list(self.get_parameter('input_scales').value),
            [1.0] * self.axis_count,
            'input_scales',
        )
        self.input_offsets_deg = self._normalize_float_list(
            list(self.get_parameter('input_offsets_deg').value),
            [0.0] * self.axis_count,
            'input_offsets_deg',
        )
        self.joint_to_servo_ratio = self._normalize_float_list(
            list(self.get_parameter('joint_to_servo_ratio').value),
            DEFAULT_JOINT_TO_SERVO_RATIO,
            'joint_to_servo_ratio',
        )
        self.joint_min_deg = self._normalize_float_list(
            list(self.get_parameter('joint_min_deg').value),
            DEFAULT_JOINT_MIN_DEG,
            'joint_min_deg',
        )
        self.joint_max_deg = self._normalize_float_list(
            list(self.get_parameter('joint_max_deg').value),
            DEFAULT_JOINT_MAX_DEG,
            'joint_max_deg',
        )
        self.post_ratio_joint_min_deg = self._normalize_float_list(
            list(self.get_parameter('post_ratio_joint_min_deg').value),
            DEFAULT_POST_RATIO_JOINT_MIN_DEG,
            'post_ratio_joint_min_deg',
        )
        self.post_ratio_joint_max_deg = self._normalize_float_list(
            list(self.get_parameter('post_ratio_joint_max_deg').value),
            DEFAULT_POST_RATIO_JOINT_MAX_DEG,
            'post_ratio_joint_max_deg',
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
        self.joystick_min_deg = self._normalize_float_list(
            list(self.get_parameter('joystick_min_deg').value),
            DEFAULT_JOINT_MIN_DEG,
            'joystick_min_deg',
        )
        self.joystick_max_deg = self._normalize_float_list(
            list(self.get_parameter('joystick_max_deg').value),
            DEFAULT_JOINT_MAX_DEG,
            'joystick_max_deg',
        )

        joystick_axes = self.axis_count - self.encoder_axis_count
        self.joystick_defaults = self._normalize_float_list(
            list(self.get_parameter('joystick_defaults').value),
            [0.0] * joystick_axes,
            'joystick_defaults',
            expected_len=joystick_axes,
        )
        self._joystick_values: List[float] = list(self.joystick_defaults)

        self.publisher = self.create_publisher(ArmServoCommand, self.output_topic, 10)

        self.joystick_subscription = None
        if joystick_axes > 0:
            self.joystick_subscription = self.create_subscription(
                Float32MultiArray,
                self.joystick_topic,
                self._joystick_callback,
                10,
            )

        self.subscription = None
        self._serial = None
        self._serial_timer = None
        self._last_serial_attempt_sec = 0.0

        if self.use_serial_input and self.encoder_axis_count > 0:
            self._setup_serial_reader()
        elif self.encoder_axis_count > 0:
            self.subscription = self.create_subscription(
                Float32MultiArray,
                self.input_topic,
                self._encoder_callback,
                10,
            )

        self.get_logger().info(
            'Arm encoder bridge active: '
            f'encoders={self.encoder_axis_count}, joystick_axes={joystick_axes}, '
            f'output={self.output_topic}'
        )

    def _setup_serial_reader(self) -> None:
        self._serial_timer = self.create_timer(self.serial_poll_sec, self._serial_worker)
        self._serial_worker()

    def _candidate_ports(self) -> List[str]:
        ports = [self.serial_port]
        if self.serial_auto_discover:
            ports.extend(sorted(glob.glob('/dev/serial/by-id/*')))
            ports.extend(sorted(glob.glob('/dev/ttyACM*')))
            ports.extend(sorted(glob.glob('/dev/ttyUSB*')))

        unique_ports: List[str] = []
        for port in ports:
            if port and port not in unique_ports:
                unique_ports.append(port)
        return unique_ports

    def _try_open_serial(self) -> None:
        try:
            import serial  # type: ignore
        except Exception as exc:
            self.get_logger().error(f'pyserial is not available: {exc}')
            return

        for candidate in self._candidate_ports():
            try:
                self._serial = serial.Serial(
                    candidate,
                    self.serial_baud_rate,
                    timeout=self.serial_timeout_sec,
                )
                self._serial.reset_input_buffer()
                self.serial_port = candidate
                self.get_logger().info(
                    f'Reading encoders from {candidate} @ {self.serial_baud_rate} bps'
                )
                return
            except Exception:
                continue

        self._serial = None
        self.get_logger().warn(
            f'Unable to open encoder serial port. Retrying in {self.serial_reconnect_sec:.1f}s.'
        )

    def _serial_worker(self) -> None:
        if self._serial is None:
            now = time.monotonic()
            if now - self._last_serial_attempt_sec >= self.serial_reconnect_sec:
                self._last_serial_attempt_sec = now
                self._try_open_serial()
            return

        self._read_serial_once()

    def _read_serial_once(self) -> None:
        if self._serial is None:
            return

        try:
            line = self._serial.readline().decode('utf-8', errors='ignore').strip()
        except Exception as exc:
            self.get_logger().warn(f'Serial read failed: {exc}')
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
            return

        if not line:
            return

        parts = [part.strip() for part in line.split(',')]
        if len(parts) < self.encoder_axis_count:
            self.get_logger().warn(
                f'Expected at least {self.encoder_axis_count} encoder values, got {len(parts)}: {line}'
            )
            return

        try:
            encoder_values = [float(parts[index]) for index in range(self.encoder_axis_count)]
        except ValueError:
            self.get_logger().warn(f'Invalid encoder CSV frame: {line}')
            return

        self._publish_from_inputs(encoder_values)

    def _normalize_list(self, values: List[str], fallback: List[str], name: str) -> List[str]:
        if len(values) != self.axis_count:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match axis_count '
                f'{self.axis_count}. Using defaults.'
            )
            values = list(fallback)
        return values[: self.axis_count]

    def _normalize_float_list(
        self,
        values: List[float],
        fallback: List[float],
        name: str,
        expected_len: int = -1,
    ) -> List[float]:
        target_len = self.axis_count if expected_len < 0 else expected_len
        if len(values) != target_len:
            self.get_logger().warn(
                f'Parameter {name} length {len(values)} does not match expected length '
                f'{target_len}. Using defaults.'
            )
            values = list(fallback)
        return [float(v) for v in values[:target_len]]

    def _clamp(self, value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    def _joystick_callback(self, msg: Float32MultiArray) -> None:
        joystick_axes = self.axis_count - self.encoder_axis_count
        if joystick_axes <= 0:
            return

        if len(msg.data) < joystick_axes:
            self.get_logger().warn(
                f'Expected {joystick_axes} joystick values, received {len(msg.data)}'
            )
            return

        self._joystick_values = [
            self._clamp(float(msg.data[index]), -1.0, 1.0)
            for index in range(joystick_axes)
        ]

    def _encoder_callback(self, msg: Float32MultiArray) -> None:
        if len(msg.data) < self.encoder_axis_count:
            self.get_logger().warn(
                f'Expected {self.encoder_axis_count} encoder values, received {len(msg.data)}'
            )
            return

        encoder_values = [float(msg.data[index]) for index in range(self.encoder_axis_count)]
        self._publish_from_inputs(encoder_values)

    def _joystick_to_joint_deg(self, axis_index: int, value: float) -> float:
        ratio = (self._clamp(value, -1.0, 1.0) + 1.0) * 0.5
        min_deg = self.joystick_min_deg[axis_index]
        max_deg = self.joystick_max_deg[axis_index]
        return min_deg + ratio * (max_deg - min_deg)

    def _publish_from_inputs(self, encoder_values: List[float]) -> None:
        if len(encoder_values) < self.encoder_axis_count:
            return

        command = ArmServoCommand()
        command.header.stamp = self.get_clock().now().to_msg()

        for index in range(self.axis_count):
            if index < self.encoder_axis_count:
                raw_value = float(encoder_values[index])
            else:
                joystick_index = index - self.encoder_axis_count
                joystick_value = self.joystick_defaults[joystick_index]
                if joystick_index < len(self._joystick_values):
                    joystick_value = self._joystick_values[joystick_index]
                raw_value = self._joystick_to_joint_deg(index, joystick_value)

            joint_value = raw_value * self.input_scales[index] + self.input_offsets_deg[index]
            joint_value = self._clamp(joint_value, self.joint_min_deg[index], self.joint_max_deg[index])

            ratio = self.joint_to_servo_ratio[index]
            servo_target = joint_value * ratio

            post_min = self.post_ratio_joint_min_deg[index] * ratio
            post_max = self.post_ratio_joint_max_deg[index] * ratio
            servo_target = self._clamp(servo_target, min(post_min, post_max), max(post_min, post_max))

            servo_target = self._clamp(servo_target, self.servo_min_deg[index], self.servo_max_deg[index])
            command.target_deg[index] = float(servo_target)

        self.publisher.publish(command)


def main(args=None) -> None:
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


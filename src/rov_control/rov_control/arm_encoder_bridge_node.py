"""Bridge Arduino encoder CSV data to arm servo commands."""

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
    'wrist_pitch',
    'wrist_roll',
    'wrist_yaw',
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

        self.declare_parameter('axis_count', 7)
        self.declare_parameter('input_topic', '/rov/arm/encoder_values')
        self.declare_parameter('output_topic', '/rov/arm/servo_command')
        self.declare_parameter('axis_names', DEFAULT_AXIS_NAMES)
        self.declare_parameter('scales', [1.0] * 7)
        self.declare_parameter('offsets_deg', [0.0] * 7)
        self.declare_parameter('servo_min_deg', [0.0] * 7)
        self.declare_parameter('servo_max_deg', [180.0] * 7)
        self.declare_parameter('use_serial_input', True)
        self.declare_parameter('serial_port', '/dev/ttyACM0')
        self.declare_parameter('serial_baud_rate', 921600)
        self.declare_parameter('serial_timeout_sec', 0.02)
        self.declare_parameter('serial_poll_sec', 0.01)
        self.declare_parameter('serial_reconnect_sec', 1.0)
        self.declare_parameter('serial_auto_discover', True)

        _ARM_SERVO_COMMAND_SIZE = 8
        self.axis_count = int(self.get_parameter('axis_count').value)
        if self.axis_count > _ARM_SERVO_COMMAND_SIZE:
            self.get_logger().error(
                f'Configured axis_count {self.axis_count} exceeds '
                f'ArmServoCommand.target_deg size ({_ARM_SERVO_COMMAND_SIZE}). '
                f'Overriding axis_count to {_ARM_SERVO_COMMAND_SIZE}.'
            )
            self.axis_count = _ARM_SERVO_COMMAND_SIZE
        if self.axis_count < 1:
            self.get_logger().error('axis_count must be >= 1. Overriding axis_count to 7.')
            self.axis_count = 7
        self.input_topic = str(self.get_parameter('input_topic').value)
        self.output_topic = str(self.get_parameter('output_topic').value)
        self.use_serial_input = bool(self.get_parameter('use_serial_input').value)
        self.serial_port = str(self.get_parameter('serial_port').value)
        self.serial_baud_rate = int(self.get_parameter('serial_baud_rate').value)
        self.serial_timeout_sec = float(self.get_parameter('serial_timeout_sec').value)
        self.serial_poll_sec = float(self.get_parameter('serial_poll_sec').value)
        self.serial_reconnect_sec = float(self.get_parameter('serial_reconnect_sec').value)
        self.serial_auto_discover = bool(self.get_parameter('serial_auto_discover').value)

        self._serial = None
        self._serial_timer = None
        self._last_serial_attempt_sec = 0.0

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

        if self.use_serial_input:
            self._setup_serial_reader()
        else:
            self.subscription = self.create_subscription(
                Float32MultiArray,
                self.input_topic,
                self._encoder_callback,
                10,
            )

        self.get_logger().info(
            f'Arm encoder bridge active: -> {self.output_topic} ({self.axis_count} axes)'
        )

    def _setup_serial_reader(self) -> None:
        """Start periodic serial polling with automatic reconnect."""
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

        attempted = self._candidate_ports()
        for candidate in attempted:
            try:
                self._serial = serial.Serial(
                    candidate,
                    self.serial_baud_rate,
                    timeout=self.serial_timeout_sec,
                )
                self._serial.reset_input_buffer()
                self.serial_port = candidate
                self.get_logger().info(
                    f'Reading encoders from Arduino serial {candidate} @ {self.serial_baud_rate} bps'
                )
                return
            except Exception:
                continue

        self._serial = None
        if attempted:
            self.get_logger().warn(
                f'Unable to open Arduino serial port. Retrying in {self.serial_reconnect_sec:.1f}s. '
                f'Candidates: {attempted}'
            )

    def _serial_worker(self) -> None:
        now = time.monotonic()
        if self._serial is None:
            if now - self._last_serial_attempt_sec >= self.serial_reconnect_sec:
                self._last_serial_attempt_sec = now
                self._try_open_serial()
            return

        self._read_serial_once()

    def _read_serial_once(self) -> None:
        """Read one CSV line from Arduino and publish it as ArmServoCommand."""
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
        if len(parts) < self.axis_count:
            self.get_logger().warn(
                f'Expected at least {self.axis_count} CSV values from Arduino, got {len(parts)}: {line}'
            )
            return

        try:
            values = [float(parts[index]) for index in range(self.axis_count)]
        except ValueError:
            self.get_logger().warn(f'Invalid Arduino CSV frame: {line}')
            return

        self._publish_command(values)

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

        self._publish_command([float(msg.data[index]) for index in range(self.axis_count)])

    def _publish_command(self, raw_values: List[float]) -> None:
        """Apply scaling/clamping and publish arm command."""
        if len(raw_values) < self.axis_count:
            return

        command = ArmServoCommand()
        command.header.stamp = self.get_clock().now().to_msg()

        for index in range(self.axis_count):
            raw_value = float(raw_values[index])
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


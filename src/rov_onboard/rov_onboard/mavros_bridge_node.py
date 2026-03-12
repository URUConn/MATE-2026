"""
MAVROS Bridge Node - Interfaces between ROS 2 thruster commands and MAVROS RC Override.
Runs on the LattePanda (onboard computer).

Converts ThrusterCommand messages to MAVROS RC Override commands for the PIX6 flight controller.
This allows the gamepad/keyboard input from the laptop to drive the ROV thrusters via ArduSub.

Supports 8-thruster Vectored ROV with 4 vertical thrusters configuration.

Note: Requires MAVROS2 to be installed and the PIX6 connected via USB.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rov_msgs.msg import ThrusterCommand
from mavros_msgs.msg import OverrideRCIn
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool
from std_msgs.msg import Bool
import time


class MavrosBridgeNode(Node):
    """
    Bridges thruster commands to MAVROS RC Override.
    
    ArduSub uses 6 channels for ROV control (channels 1-6):
    - Channel 1: Roll (1000-2000 µs)
    - Channel 2: Pitch (1000-2000 µs)
    - Channel 3: Throttle/Vertical (1000-2000 µs)
    - Channel 4: Yaw (1000-2000 µs)
    - Channel 5: Forward (surge)
    - Channel 6: Lateral (strafe)
    
    This node converts normalized thruster values (-1.0 to 1.0) to RC PWM values (1000-2000 µs).
    """

    RC_CHANNEL_COUNT = 18
    RC_NO_CHANGE = 65535

    def __init__(self):
        super().__init__('mavros_bridge_node')

        # Parameters
        self.declare_parameter('armed', False)
        self.declare_parameter('fcu_port', '/dev/ttyACM0')
        self.declare_parameter('fcu_baud', 115200)
        self.declare_parameter('thrust_scaling', 1.0)
        self.declare_parameter('rc_min_pwm', 1000)
        self.declare_parameter('rc_max_pwm', 2000)
        self.declare_parameter('rc_center_pwm', 1500)

        self.armed = self.get_parameter('armed').value
        self.fcu_port = self.get_parameter('fcu_port').value
        self.fcu_baud = self.get_parameter('fcu_baud').value
        self.thrust_scaling = self.get_parameter('thrust_scaling').value
        self.rc_min_pwm = self.get_parameter('rc_min_pwm').value
        self.rc_max_pwm = self.get_parameter('rc_max_pwm').value
        self.rc_center_pwm = self.get_parameter('rc_center_pwm').value

        # Publishers and subscribers
        self.rc_override_publishers = {
            'mavros': self.create_publisher(OverrideRCIn, '/mavros/rc/override', 10),
            'uas1': self.create_publisher(OverrideRCIn, '/uas1/mavros/rc/override', 10),
        }
        self.thruster_sub = self.create_subscription(
            ThrusterCommand,
            '/rov/thruster_command',
            self.thruster_callback,
            10
        )
        self.arm_sub = self.create_subscription(
            Bool,
            '/rov/arm_cmd',
            self.arm_callback,
            10
        )
        mavros_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self.mavros_state_sub = self.create_subscription(
            State,
            '/mavros/state',
            lambda msg: self.mavros_state_callback(msg, 'mavros'),
            mavros_qos,
        )
        self.mavros_state_sub_uas1 = self.create_subscription(
            State,
            '/uas1/mavros/state',
            lambda msg: self.mavros_state_callback(msg, 'uas1'),
            mavros_qos,
        )
        self.arm_clients = {
            '/mavros/cmd/arming': self.create_client(CommandBool, '/mavros/cmd/arming'),
            '/mavros/mavros/arming': self.create_client(CommandBool, '/mavros/mavros/arming'),
            '/cmd/arming': self.create_client(CommandBool, '/cmd/arming'),
            '/uas1/mavros/cmd/arming': self.create_client(CommandBool, '/uas1/mavros/cmd/arming'),
            '/uas1/mavros/arming': self.create_client(CommandBool, '/uas1/mavros/arming'),
            '/uas1/cmd/arming': self.create_client(CommandBool, '/uas1/cmd/arming'),
        }

        # State tracking
        self.last_command_time = None
        self.connection_timeout = 5.0  # seconds
        self.fcu_connected = False
        self.connected_namespaces = {'mavros': False, 'uas1': False}
        self.armed_namespaces = {'mavros': False, 'uas1': False}
        self.active_namespace = None
        self.active_arm_service = None
        self.last_waiting_log_time = 0.0
        self._missing_thruster_fields_logged = set()
        self.last_arm_service_warn_time = 0.0
        self.last_reported_armed = self.armed

        # Initial state - all channels to neutral
        self.rc_channels = self._build_neutral_channels()

        # Check connection status periodically
        self.create_timer(1.0, self.check_connection)

        self.get_logger().info('MAVROS Bridge Node initialized')
        self.get_logger().info(f'FCU Port: {self.fcu_port} @ {self.fcu_baud} baud')
        self.get_logger().info(f'Armed: {self.armed}')
        self.get_logger().info('Arm/disarm topic: /rov/arm_cmd (std_msgs/Bool)')
        self.get_logger().info('Waiting for thruster commands...')

    def arm_callback(self, msg: Bool):
        """Arm or disarm runtime command from control laptop."""
        requested = bool(msg.data)
        if requested and requested == self.armed:
            return

        if not requested:
            # CRITICAL: Always gate off immediately on disarm for safety
            # Do NOT wait for MAVROS confirmation - send neutral RC immediately
            was_armed = self.armed
            self.armed = False
            self.publish_neutral_override()  # Send neutral RC commands
            if was_armed:
                self.get_logger().warn('DISARM COMMAND RECEIVED: Sending neutral RC override immediately')
            else:
                self.get_logger().info('Disarm command received (was already disarmed)')

        arm_client = self._get_ready_arm_client()
        if arm_client is None:
            now = time.time()
            if now - self.last_arm_service_warn_time > 2.0:
                self.get_logger().warn(
                    f'MAVROS {"arming" if requested else "disarming"} service not ready: '
                    'tried /mavros/cmd/arming, /mavros/mavros/arming, /cmd/arming, '
                    '/uas1/mavros/cmd/arming, /uas1/mavros/arming, /uas1/cmd/arming'
                )
                self.last_arm_service_warn_time = now
            return

        req = CommandBool.Request()
        req.value = requested
        future = arm_client.call_async(req)
        future.add_done_callback(lambda f: self._on_arm_service_response(f, requested))

    def _get_ready_arm_client(self):
        ordered_service_candidates = []

        if self.active_namespace == 'uas1':
            ordered_service_candidates.extend([
                '/uas1/mavros/cmd/arming',
                '/uas1/mavros/arming',
                '/uas1/cmd/arming',
            ])
        elif self.active_namespace == 'mavros':
            ordered_service_candidates.extend([
                '/mavros/cmd/arming',
                '/mavros/mavros/arming',
                '/cmd/arming',
            ])

        # Fallback if active namespace is unknown or service is temporarily unavailable.
        ordered_service_candidates.extend([
            '/mavros/cmd/arming',
            '/mavros/mavros/arming',
            '/cmd/arming',
            '/uas1/mavros/cmd/arming',
            '/uas1/mavros/arming',
            '/uas1/cmd/arming',
        ])

        for service_name in ordered_service_candidates:
            client = self.arm_clients.get(service_name)
            if client and client.service_is_ready():
                if self.active_arm_service != service_name:
                    self.active_arm_service = service_name
                    self.get_logger().info(f'Using arming service: {service_name}')
                return client

        self.active_arm_service = None
        for _, client in self.arm_clients.items():
            if client.service_is_ready():
                return client
        return None

    def mavros_state_callback(self, msg: State, source: str):
        self.connected_namespaces[source] = bool(msg.connected)
        if bool(msg.connected):
            self.armed_namespaces[source] = bool(msg.armed)

        self.fcu_connected = any(self.connected_namespaces.values())

        if self.connected_namespaces['uas1']:
            self.active_namespace = 'uas1'
        elif self.connected_namespaces['mavros']:
            self.active_namespace = 'mavros'
        else:
            self.active_namespace = None

        previous_armed = self.armed
        if self.active_namespace is not None:
            self.armed = bool(self.armed_namespaces[self.active_namespace])
        else:
            self.armed = False

        if previous_armed != self.armed and self.last_reported_armed != self.armed:
            self.last_reported_armed = self.armed
            state = 'ARMED' if self.armed else 'DISARMED'
            self.get_logger().info(f'FCU state update from MAVROS: {state}')

    def _on_arm_service_response(self, future, requested: bool):
        try:
            response = future.result()
        except Exception as ex:
            self.get_logger().error(f'Arming service call failed: {ex}')
            if requested:
                self.armed = False
            return

        if response.success:
            self.armed = requested
            state = 'ARMED' if requested else 'DISARMED'
            self.get_logger().warn(f'FCU arm command accepted: {state}')
            if not requested:
                self.publish_neutral_override()
        else:
            if requested:
                self.armed = False
            self.get_logger().error(
                f'FCU arm command rejected (result={response.result})'
            )

    def publish_neutral_override(self):
        """Send neutral RC values immediately when disarmed or timed out."""
        self.rc_channels = self._build_neutral_channels()
        self.publish_rc_override()

    def _build_neutral_channels(self):
        channels = [self.RC_NO_CHANGE] * self.RC_CHANNEL_COUNT
        channels[0] = self.rc_center_pwm
        channels[1] = self.rc_center_pwm
        channels[2] = self.rc_center_pwm
        channels[3] = self.rc_center_pwm
        channels[4] = self.rc_center_pwm
        channels[5] = self.rc_center_pwm
        return channels

    def publish_rc_override(self):
        if len(self.rc_channels) != self.RC_CHANNEL_COUNT:
            self.get_logger().error('RC override channel array invalid; resetting to neutral.')
            self.rc_channels = self._build_neutral_channels()
        rc_msg = OverrideRCIn()
        rc_msg.channels = self.rc_channels

        # Publish to active namespace first; also mirror to the other namespace to
        # tolerate MAVROS naming differences across deployments.
        if self.active_namespace in self.rc_override_publishers:
            self.rc_override_publishers[self.active_namespace].publish(rc_msg)
            for name, pub in self.rc_override_publishers.items():
                if name != self.active_namespace:
                    pub.publish(rc_msg)
            return

        for pub in self.rc_override_publishers.values():
            pub.publish(rc_msg)

    def thruster_callback(self, msg: ThrusterCommand):
        """
        Convert ThrusterCommand to MAVROS RC Override.
        
        Thruster layout (8-thruster vectored ROV with 4 vertical thrusters):
        Horizontal thrusters (for forward/backward, strafe, yaw):
        - Front left, front right: forward/backward + strafe + yaw
        - Back left, back right: forward/backward + strafe + yaw
        
        Vertical thrusters (for up/down, roll, pitch):
        - Vertical front left, vertical front right: up/down + pitch + roll
        - Vertical back left, vertical back right: up/down + pitch + roll
        """
        if not self.armed:
            return

        self.last_command_time = time.time()

        # Extract horizontal thrust values (normalized -1.0 to 1.0)
        fl = self._get_thruster_value(msg, 'thruster_front_left', 'front_left') * self.thrust_scaling
        fr = self._get_thruster_value(msg, 'thruster_front_right', 'front_right') * self.thrust_scaling
        bl = self._get_thruster_value(msg, 'thruster_back_left', 'back_left') * self.thrust_scaling
        br = self._get_thruster_value(msg, 'thruster_back_right', 'back_right') * self.thrust_scaling
        
        # Extract vertical thrust values (4 vertical thrusters)
        vfl = self._get_thruster_value(msg, 'thruster_vertical_front_left', 'vertical_front_left') * self.thrust_scaling
        vfr = self._get_thruster_value(msg, 'thruster_vertical_front_right', 'vertical_front_right') * self.thrust_scaling
        vbl = self._get_thruster_value(msg, 'thruster_vertical_back_left', 'vertical_back_left') * self.thrust_scaling
        vbr = self._get_thruster_value(msg, 'thruster_vertical_back_right', 'vertical_back_right') * self.thrust_scaling

        # Recover motion axes from 8-thruster mixed command.
        # Publisher mix: fl=f+s+y fr=f-s-y bl=f-s+y br=f+s-y
        forward = (fl + fr + bl + br) / 4.0
        lateral = (fl - fr - bl + br) / 4.0
        yaw = (fl - fr + bl - br) / 4.0

        # Vertical channel comes from average of the 4 vertical thrusters.
        throttle = (vfl + vfr + vbl + vbr) / 4.0

        # Keep roll/pitch neutral unless vertical thrusters are intentionally
        # used with differential values.
        roll = ((vfl + vbl) - (vfr + vbr)) / 2.0
        pitch = ((vfl + vfr) - (vbl + vbr)) / 2.0

        # Clamp values to [-1.0, 1.0]
        roll = max(-1.0, min(1.0, roll))
        pitch = max(-1.0, min(1.0, pitch))
        throttle = max(-1.0, min(1.0, throttle))
        yaw = max(-1.0, min(1.0, yaw))
        forward = max(-1.0, min(1.0, forward))
        lateral = max(-1.0, min(1.0, lateral))

        # Convert normalized values (-1.0 to 1.0) to RC PWM values (1000-2000 µs)
        # Center is 1500, min is 1000, max is 2000
        self.rc_channels[0] = int(self.rc_center_pwm + (roll * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[1] = int(self.rc_center_pwm + (pitch * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[2] = int(self.rc_center_pwm + (throttle * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[3] = int(self.rc_center_pwm + (yaw * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[4] = int(self.rc_center_pwm + (forward * (self.rc_max_pwm - self.rc_center_pwm)))
        self.rc_channels[5] = int(self.rc_center_pwm + (lateral * (self.rc_max_pwm - self.rc_center_pwm)))

        # Clamp to valid PWM range
        for i in range(6):
            self.rc_channels[i] = max(self.rc_min_pwm, min(self.rc_max_pwm, self.rc_channels[i]))

        # Publish RC override
        self.publish_rc_override()

        # Log at debug level to reduce spam
        self.get_logger().debug(
            f'RC Override - Ch1:{self.rc_channels[0]} Ch2:{self.rc_channels[1]} '
            f'Ch3:{self.rc_channels[2]} Ch4:{self.rc_channels[3]} '
            f'Ch5:{self.rc_channels[4]} Ch6:{self.rc_channels[5]}'
        )

    def _get_thruster_value(self, msg: ThrusterCommand, canonical_name: str, legacy_name: str) -> float:
        if hasattr(msg, canonical_name):
            return float(getattr(msg, canonical_name))
        if hasattr(msg, legacy_name):
            return float(getattr(msg, legacy_name))

        key = f'{canonical_name}|{legacy_name}'
        if key not in self._missing_thruster_fields_logged:
            self.get_logger().error(
                f'ThrusterCommand missing expected fields: {canonical_name} or {legacy_name}. Using 0.0.'
            )
            self._missing_thruster_fields_logged.add(key)
        return 0.0

    def check_connection(self):
        """Check if we're receiving commands and if FCU is connected"""
        now = time.time()

        if not self.fcu_connected:
            if now - self.last_waiting_log_time > 15.0:
                self.get_logger().info('Waiting for FCU connection from MAVROS state...')
                self.last_waiting_log_time = now
            return

        if self.last_command_time is None:
            if now - self.last_waiting_log_time > 15.0:
                self.get_logger().info('FCU connected, waiting for thruster commands on /rov/thruster_command...')
                self.last_waiting_log_time = now
            return

        time_since_last_command = time.time() - self.last_command_time

        if time_since_last_command > self.connection_timeout:
            # No commands received recently - send neutral commands to prevent drift
            if self.armed:
                self.publish_neutral_override()
            now = time.time()
            if now - self.last_waiting_log_time > 5.0:
                self.get_logger().warn('No thruster commands received (timeout)')
                self.last_waiting_log_time = now
            return



def main(args=None):
    rclpy.init(args=args)
    node = MavrosBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


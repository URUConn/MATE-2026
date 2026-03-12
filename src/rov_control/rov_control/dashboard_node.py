"""Dashboard Node - Centralized control UI for operator commands and telemetry."""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import SensorData, RovStatus
from std_msgs.msg import Bool, String
import time

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    PYGAME_AVAILABLE = False


class DashboardNode(Node):
    def __init__(self):
        super().__init__('dashboard_node')

        self.sensor_sub = self.create_subscription(SensorData, '/rov/sensor_data', self.sensor_callback, 10)
        self.status_sub = self.create_subscription(RovStatus, '/rov/status', self.status_callback, 10)
        self.input_mode_state_sub = self.create_subscription(
            String,
            '/rov/input_mode_state',
            self.input_mode_state_callback,
            10,
        )

        self.arm_pub = self.create_publisher(Bool, '/rov/arm_cmd', 10)
        self.input_mode_pub = self.create_publisher(String, '/rov/input_mode_cmd', 10)

        self.latest_sensor = None
        self.latest_status = None
        self.current_input_mode = 'unknown'
        self.last_click_feedback = 'No command sent yet'
        self.pending_arm_state = None
        self.pending_arm_sent_time = 0.0
        self.pending_arm_retries = 0

        self.declare_parameter('display_rate', 20.0)
        display_rate = float(self.get_parameter('display_rate').value)

        if not PYGAME_AVAILABLE:
            self.get_logger().error('pygame not installed. Install with: pip3 install pygame')
            return

        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((760, 540))
        pygame.display.set_caption('ROV Central Control Dashboard')
        self.font_title = pygame.font.SysFont(None, 34)
        self.font_body = pygame.font.SysFont(None, 24)
        self.font_small = pygame.font.SysFont(None, 20)

        self.buttons = {
            'arm': pygame.Rect(36, 70, 160, 48),
            'disarm': pygame.Rect(214, 70, 160, 48),
            'keyboard': pygame.Rect(420, 70, 140, 48),
            'xbox': pygame.Rect(576, 70, 140, 48),
        }

        self.timer = self.create_timer(1.0 / display_rate, self.tick)

        self.get_logger().info('Dashboard UI started')

    def sensor_callback(self, msg):
        self.latest_sensor = msg

    def status_callback(self, msg):
        self.latest_status = msg

    def input_mode_state_callback(self, msg: String):
        self.current_input_mode = msg.data

    def publish_arm(self, armed: bool):
        self.publish_arm_gate(armed)
        self.pending_arm_state = armed
        self.pending_arm_retries = 8
        self.pending_arm_sent_time = time.time()
        self.last_click_feedback = 'Sent ARM command' if armed else 'Sent DISARM command'

    def publish_arm_gate(self, armed: bool):
        msg = Bool()
        msg.data = armed
        self.arm_pub.publish(msg)


    def publish_input_mode(self, mode: str):
        msg = String()
        msg.data = mode
        self.input_mode_pub.publish(msg)
        self.last_click_feedback = f'Sent input mode command: {mode}'

    def tick(self):
        if not PYGAME_AVAILABLE:
            return

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.handle_click(event.pos)

        self.process_pending_arm()

        self.draw()

    def process_pending_arm(self):
        if self.pending_arm_state is None:
            return

        if self.latest_status and self.latest_status.armed == self.pending_arm_state:
            self.last_click_feedback = f'Arm state confirmed: {self.pending_arm_state}'
            self.pending_arm_state = None
            self.pending_arm_retries = 0
            return

        now = time.time()
        if self.pending_arm_retries > 0 and (now - self.pending_arm_sent_time) > 0.35:
            self.publish_arm_gate(self.pending_arm_state)
            self.pending_arm_sent_time = now
            self.pending_arm_retries -= 1
        elif self.pending_arm_retries == 0:
            self.last_click_feedback = 'Arm command sent, awaiting status confirmation'
            self.pending_arm_state = None

    def handle_click(self, pos):
        if self.buttons['arm'].collidepoint(pos):
            self.publish_arm(True)
        elif self.buttons['disarm'].collidepoint(pos):
            self.publish_arm(False)
        elif self.buttons['keyboard'].collidepoint(pos):
            self.publish_input_mode('keyboard')
        elif self.buttons['xbox'].collidepoint(pos):
            self.publish_input_mode('xbox')

    def draw_button(self, key, label, color):
        rect = self.buttons[key]
        pygame.draw.rect(self.screen, color, rect, border_radius=8)
        text = self.font_body.render(label, True, (20, 20, 20))
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)

    def draw(self):
        self.screen.fill((18, 22, 30))

        title = self.font_title.render('ROV Central Control Dashboard', True, (235, 235, 235))
        self.screen.blit(title, (36, 20))

        self.draw_button('arm', 'ARM', (120, 220, 120))
        self.draw_button('disarm', 'DISARM', (240, 120, 120))
        self.draw_button('keyboard', 'Keyboard', (130, 190, 255))
        self.draw_button('xbox', 'Xbox', (170, 170, 255))

        y = 150
        info_lines = []
        if self.latest_status:
            s = self.latest_status
            info_lines.extend([
                f'Armed (reported): {s.armed}',
                f'Mode (reported): {s.mode}',
                f'Leak detected: {s.leak_detected}',
                f'CPU temp: {s.cpu_temperature:.1f} C',
                f'Uptime: {s.uptime_seconds:.0f} s',
            ])
        else:
            info_lines.append('Status: no data')

        if self.latest_sensor:
            d = self.latest_sensor
            info_lines.extend([
                f'Depth: {d.depth:.2f} m',
                f'Temperature: {d.temperature:.1f} C',
                f'Heading: {d.heading:.1f} deg',
                f'Pitch: {d.pitch:.1f} deg',
                f'Roll: {d.roll:.1f} deg',
                f'Battery: {d.battery_voltage:.2f} V',
            ])
        else:
            info_lines.append('Sensors: no data')

        info_lines.append(f'Input mode (reported): {self.current_input_mode}')
        info_lines.append(f'Last UI action: {self.last_click_feedback}')

        for line in info_lines:
            text = self.font_body.render(line, True, (210, 218, 232))
            self.screen.blit(text, (36, y))
            y += 30

        hint = self.font_small.render('Use buttons above to arm/disarm and switch Keyboard/Xbox on the fly.', True, (180, 185, 195))
        self.screen.blit(hint, (36, 500))

        pygame.display.flip()

    def destroy_node(self):
        if PYGAME_AVAILABLE:
            pygame.quit()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = DashboardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

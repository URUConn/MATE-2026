"""
Gamepad Node - Reads Xbox controller or keyboard input and publishes thruster commands.
Runs on the control laptop.
Requires pygame: pip3 install pygame

Xbox Controller Mapping (Default):
- Left Stick Y: Forward/Backward
- Left Stick X: Strafe Left/Right
- Right Stick X: Yaw (Rotation)
- Right Trigger - Left Trigger: Vertical Movement

Keyboard Fallback (if no controller):
- W/A/S/D: Forward/Left/Back/Right
- Up/Down: Vertical Up/Down
- Left/Right: Yaw
- Space: Stop all thrusters
"""

import rclpy
from rclpy.node import Node
from rov_msgs.msg import ThrusterCommand
import sys

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class GamepadNode(Node):
    def __init__(self):
        super().__init__('gamepad_node')

        self.declare_parameter('publish_rate', 50.0)
        self.declare_parameter('deadzone', 0.1)
        self.declare_parameter('max_power', 1.0)
        self.declare_parameter('use_keyboard_fallback', True)

        publish_rate = self.get_parameter('publish_rate').value
        self.deadzone = self.get_parameter('deadzone').value
        self.max_power = self.get_parameter('max_power').value
        use_keyboard_fallback = self.get_parameter('use_keyboard_fallback').value

        self.publisher = self.create_publisher(ThrusterCommand, '/rov/thruster_command', 10)

        # Keyboard state tracking
        self.keyboard_forward = 0.0
        self.keyboard_strafe = 0.0
        self.keyboard_yaw = 0.0
        self.keyboard_vertical = 0.0
        self.use_keyboard = False
        self.joystick = None
        self.keyboard_window = None

        if not PYGAME_AVAILABLE:
            self.get_logger().error('pygame not installed. Run: pip3 install pygame')
            return

        pygame.init()
        pygame.joystick.init()

        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.get_logger().info(f'✓ Gamepad connected: {self.joystick.get_name()}')
            self.use_keyboard = False
        else:
            if use_keyboard_fallback:
                self.get_logger().warn('No gamepad detected. Using keyboard fallback.')
                self.get_logger().info('Keyboard Controls: W/A/S/D (move), Arrow Keys (vertical/yaw), Space (stop)')
                self.use_keyboard = True
                # pygame only reports keyboard state for the focused window.
                self.keyboard_window = pygame.display.set_mode((460, 120))
                pygame.display.set_caption('ROV Keyboard Control - Click to focus')
                # Enable key repeat for smooth movement
                pygame.key.set_repeat(50, 50)
                self.get_logger().info('Click the pygame window to focus keyboard input.')
            else:
                self.get_logger().error('No gamepad detected and keyboard fallback disabled.')
                return

        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.read_input)

    def apply_deadzone(self, value):
        if abs(value) < self.deadzone:
            return 0.0
        return value * self.max_power

    def read_input(self):
        """Read input from either gamepad or keyboard"""
        if self.use_keyboard:
            self.read_keyboard()
        else:
            self.read_gamepad()
        
        self.publish_thruster_command()

    def read_gamepad(self):
        """Read Xbox controller input"""
        if not self.joystick:
            return

        pygame.event.pump()

        # Xbox controller axis mapping:
        # Axis 0: Left Stick X (strafe)
        # Axis 1: Left Stick Y (forward, inverted)
        # Axis 3: Right Stick X (yaw)
        # Axis 4: Right Trigger (0 to 1)
        # Axis 5: Left Trigger (0 to 1)
        
        forward = -self.apply_deadzone(self.joystick.get_axis(1))   # Left stick Y
        strafe = self.apply_deadzone(self.joystick.get_axis(0))     # Left stick X
        yaw = self.apply_deadzone(self.joystick.get_axis(3))        # Right stick X
        
        # Combine triggers (right positive, left negative for vertical)
        right_trigger = self.joystick.get_axis(4) if self.joystick.get_numaxes() > 4 else 0
        left_trigger = self.joystick.get_axis(5) if self.joystick.get_numaxes() > 5 else 0
        vertical = (right_trigger - left_trigger) * self.max_power

        self.keyboard_forward = forward
        self.keyboard_strafe = strafe
        self.keyboard_yaw = yaw
        self.keyboard_vertical = vertical

    def read_keyboard(self):
        """Read keyboard input and update movement values"""
        # Process all queued events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise KeyboardInterrupt()

        # Get currently pressed keys
        keys = pygame.key.get_pressed()
        
        # WASD movement
        self.keyboard_forward = 0.0
        self.keyboard_strafe = 0.0
        if keys[pygame.K_w]:
            self.keyboard_forward = self.max_power
        if keys[pygame.K_s]:
            self.keyboard_forward = -self.max_power
        if keys[pygame.K_d]:
            self.keyboard_strafe = self.max_power
        if keys[pygame.K_a]:
            self.keyboard_strafe = -self.max_power

        # Arrow keys for vertical and yaw
        self.keyboard_vertical = 0.0
        self.keyboard_yaw = 0.0
        if keys[pygame.K_UP]:
            self.keyboard_vertical = self.max_power
        if keys[pygame.K_DOWN]:
            self.keyboard_vertical = -self.max_power
        if keys[pygame.K_RIGHT]:
            self.keyboard_yaw = self.max_power
        if keys[pygame.K_LEFT]:
            self.keyboard_yaw = -self.max_power

        # Space to stop all
        if keys[pygame.K_SPACE]:
            self.keyboard_forward = 0.0
            self.keyboard_strafe = 0.0
            self.keyboard_vertical = 0.0
            self.keyboard_yaw = 0.0

    def publish_thruster_command(self):
        """Publish thruster command based on current input values"""
        forward = self.keyboard_forward
        strafe = self.keyboard_strafe
        yaw = self.keyboard_yaw
        vertical = self.keyboard_vertical

        # Convert to individual thruster values (basic mixing for 6-thruster vectored ROV)
        msg = ThrusterCommand()
        msg.thruster_front_left = float(forward + strafe + yaw)
        msg.thruster_front_right = float(forward - strafe - yaw)
        msg.thruster_back_left = float(forward - strafe + yaw)
        msg.thruster_back_right = float(forward + strafe - yaw)
        msg.thruster_vertical_left = float(vertical)
        msg.thruster_vertical_right = float(vertical)

        # Clamp all values to [-1.0, 1.0]
        for attr in ['thruster_front_left', 'thruster_front_right',
                      'thruster_back_left', 'thruster_back_right',
                      'thruster_vertical_left', 'thruster_vertical_right']:
            val = getattr(msg, attr)
            setattr(msg, attr, max(-1.0, min(1.0, val)))

        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = GamepadNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

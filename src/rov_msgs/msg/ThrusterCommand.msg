# ThrusterCommand.msg
# Command message sent from control laptop to ROV thrusters
# Values range from -1.0 (full reverse) to 1.0 (full forward)
#
# Vectored ROV with 8 thrusters (4 horizontal + 4 vertical):
# Horizontal thrusters (for forward/backward, strafe, yaw):
#   - front_left, front_right, back_left, back_right
# Vertical thrusters (for up/down, roll, pitch):
#   - vertical_front_left, vertical_front_right, vertical_back_left, vertical_back_right

float32 thruster_front_left
float32 thruster_front_right
float32 thruster_back_left
float32 thruster_back_right
float32 thruster_vertical_front_left
float32 thruster_vertical_front_right
float32 thruster_vertical_back_left
float32 thruster_vertical_back_right

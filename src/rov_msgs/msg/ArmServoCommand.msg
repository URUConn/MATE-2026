# ArmServoCommand.msg
# Desired servo targets in degrees for the 8-axis manipulator.
# Axis order defaults to:
# [base, shoulder, elbow, wrist_pitch, wrist_roll, wrist_yaw, tool_rotate, gripper]

std_msgs/Header header
float32[8] target_deg

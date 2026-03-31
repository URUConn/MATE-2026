# ArmServoCommand.msg
# Desired servo targets in degrees.
# Current axis order:
# [base, shoulder, elbow, wrist_roll, wrist_pitch, wrist_yaw, gripper]
# target_deg keeps 8 slots for backward compatibility; axis 7 is currently unused.

std_msgs/Header header
float32[8] target_deg

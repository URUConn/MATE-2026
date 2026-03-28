"""Launch onboard camera and arm servo nodes on the LattePanda."""

from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('rov_onboard'),
        'config',
        'onboard_params.yaml'
    )

    return LaunchDescription([
        Node(
            package='rov_onboard',
            executable='camera_node',
            name='camera_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='arm_servo_node',
            name='arm_servo_node',
            parameters=[config],
            output='screen',
        ),
    ])

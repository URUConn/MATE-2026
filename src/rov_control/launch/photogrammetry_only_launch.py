"""Launch only the control-side photogrammetry node."""

from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('rov_control'),
        'config',
        'control_params.yaml'
    )

    return LaunchDescription([
        Node(
            package='rov_control',
            executable='photogrammetry_node',
            name='photogrammetry_node',
            parameters=[config],
            output='screen',
        ),
    ])


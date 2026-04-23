"""Launch arm bridge and QGC video bridge nodes on the control laptop."""

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
            executable='arm_encoder_bridge_node',
            name='arm_encoder_bridge_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_control',
            executable='qgc_video_bridge_node',
            name='qgc_video_bridge_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_control',
            executable='crab_trigger_node',
            name='crab_trigger_node',
            parameters=[config],
            output='screen',
        ),
    ])

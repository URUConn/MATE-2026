"""Launch control-laptop nodes (arm bridge + optional legacy UDP video bridge)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    enable_udp_video_bridge = LaunchConfiguration('enable_udp_video_bridge')

    config = os.path.join(
        get_package_share_directory('rov_control'),
        'config',
        'control_params.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_udp_video_bridge',
            default_value='false',
            description='Enable qgc_video_bridge_node for legacy UDP video consumers (e.g., QGC).',
        ),
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
            condition=IfCondition(enable_udp_video_bridge),
            output='screen',
        ),
    ])

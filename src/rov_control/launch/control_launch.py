"""Launch arm bridge, QGC video bridge, and optional photogrammetry nodes."""

from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
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

    enable_photogrammetry = LaunchConfiguration('enable_photogrammetry')

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_photogrammetry',
            default_value='true',
            description='Start control-side photogrammetry node',
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
            output='screen',
        ),
        Node(
            package='rov_control',
            executable='photogrammetry_node',
            name='photogrammetry_node',
            parameters=[config],
            output='screen',
            condition=IfCondition(enable_photogrammetry),
        ),
    ])

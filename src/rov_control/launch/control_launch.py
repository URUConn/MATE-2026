"""Launch arm bridge and QGC video bridge nodes on the control laptop."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    enable_qgc_bridge = LaunchConfiguration('enable_qgc_bridge')
    enable_slam_bridge = LaunchConfiguration('enable_slam_bridge')

    config = os.path.join(
        get_package_share_directory('rov_control'),
        'config',
        'control_params.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_qgc_bridge',
            default_value='true',
            description='Run QGC ffmpeg video forwarding bridge.',
        ),
        DeclareLaunchArgument(
            'enable_slam_bridge',
            default_value='true',
            description='Run control-side SLAM image bridge node.',
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
            condition=IfCondition(enable_qgc_bridge),
            output='screen',
        ),
        Node(
            package='rov_control',
            executable='slam_image_bridge_node',
            name='slam_image_bridge_node',
            parameters=[config],
            condition=IfCondition(enable_slam_bridge),
            output='screen',
        ),
    ])

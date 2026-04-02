"""Launch the control-side monocular SLAM pipeline.

This launch file is intentionally separate from the QGC bridge path so SLAM can
run without touching the video-forwarding node.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('rov_slam')
    slam_config = os.path.join(package_share, 'config', 'slam_params.yaml')
    rviz_config = os.path.join(package_share, 'rviz', 'slam_view.rviz')

    return LaunchDescription([
        DeclareLaunchArgument(
            'start_rviz',
            default_value='true',
            description='Start RViz with the SLAM visualization layout.',
        ),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=rviz_config,
            description='Path to the RViz config used for SLAM visualization.',
        ),
        Node(
            package='rov_slam',
            executable='monocular_slam_node',
            name='monocular_slam_node',
            parameters=[slam_config],
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', LaunchConfiguration('rviz_config')],
            condition=IfCondition(LaunchConfiguration('start_rviz')),
            output='screen',
        ),
    ])


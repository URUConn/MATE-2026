"""Launch the control-side camera calibration workflow."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = get_package_share_directory('rov_slam')
    calibration_config = os.path.join(package_share, 'config', 'camera_calibration_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=calibration_config,
            description='Camera calibration parameter file.',
        ),
        Node(
            package='rov_slam',
            executable='camera_calibration_node',
            name='camera_calibration_node',
            parameters=[LaunchConfiguration('params_file')],
            output='screen',
        ),
    ])


"""
Launch file for all onboard ROV nodes.
Run this on the LattePanda.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    config = os.path.join(
        get_package_share_directory('rov_onboard'),
        'config',
        'onboard_params.yaml'
    )

    mavros_launch = os.path.join(
        get_package_share_directory('mavros'),
        'launch',
        'mavros.launch.py'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'fcu_url',
            default_value='serial:///dev/ttyACM0:115200',
            description='MAVROS FCU connection URL'
        ),
        DeclareLaunchArgument(
            'gcs_url',
            default_value='',
            description='Optional MAVROS GCS URL'
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(mavros_launch),
            launch_arguments={
                'fcu_url': LaunchConfiguration('fcu_url'),
                'gcs_url': LaunchConfiguration('gcs_url'),
            }.items(),
        ),
        Node(
            package='rov_onboard',
            executable='camera_node',
            name='camera_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='thruster_node',
            name='thruster_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='sensor_node',
            name='sensor_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='status_node',
            name='status_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='mavros_bridge_node',
            name='mavros_bridge_node',
            parameters=[config],
            output='screen',
        ),
    ])

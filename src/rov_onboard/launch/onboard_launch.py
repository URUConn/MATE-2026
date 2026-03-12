"""
Launch file for all onboard ROV nodes.
Run this on the LattePanda.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
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

    mavros_launch_dir = os.path.join(get_package_share_directory('mavros'), 'launch')
    mavros_launch = None
    for candidate in ('mavros.launch.py', 'node.launch.py', 'apm.launch.py', 'px4.launch.py'):
        candidate_path = os.path.join(mavros_launch_dir, candidate)
        if os.path.exists(candidate_path):
            mavros_launch = candidate_path
            break

    actions = [
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
    ]

    if mavros_launch:
        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(mavros_launch),
                launch_arguments={
                    'fcu_url': LaunchConfiguration('fcu_url'),
                    'gcs_url': LaunchConfiguration('gcs_url'),
                }.items(),
            )
        )
    else:
        actions.extend([
            LogInfo(msg='MAVROS launch file not found; starting mavros_node directly.'),
            Node(
                package='mavros',
                executable='mavros_node',
                name='mavros',
                output='screen',
                parameters=[{
                    'fcu_url': LaunchConfiguration('fcu_url'),
                    'gcs_url': LaunchConfiguration('gcs_url'),
                }],
            ),
        ])

    actions.extend([
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

    return LaunchDescription(actions)


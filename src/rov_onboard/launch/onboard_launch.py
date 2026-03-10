"""
Launch file for all onboard ROV nodes.
Run this on the LattePanda.
Includes MAVLink bridge for ArduSub autopilot communication.
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    # Onboard config
    onboard_config = os.path.join(
        get_package_share_directory('rov_onboard'),
        'config',
        'onboard_params.yaml'
    )

    # MAVLink config
    mavlink_config = os.path.join(
        get_package_share_directory('rov_mavlink'),
        'config',
        'mavlink_params.yaml'
    )

    # Launch arguments
    connection_arg = DeclareLaunchArgument(
        'mavlink_connection',
        default_value='/dev/ttyUSB0:115200',
        description='MAVLink connection string (e.g., /dev/ttyUSB0:115200 or udp:192.168.1.100:14550)'
    )

    nodes = [
        Node(
            package='rov_onboard',
            executable='camera_node',
            name='camera_node',
            parameters=[onboard_config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='thruster_node',
            name='thruster_node',
            parameters=[onboard_config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='sensor_node',
            name='sensor_node',
            parameters=[onboard_config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='status_node',
            name='status_node',
            parameters=[onboard_config],
            output='screen',
        ),
        # MAVLink bridge node for ArduSub autopilot
        Node(
            package='rov_mavlink',
            executable='mavlink_bridge_node',
            name='mavlink_bridge',
            parameters=[
                mavlink_config,
                {'connection_string': LaunchConfiguration('mavlink_connection')}
            ],
            output='screen',
        ),
    ]

    return LaunchDescription([
        connection_arg,
    ] + nodes)

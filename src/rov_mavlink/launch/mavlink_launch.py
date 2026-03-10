"""
MAVLink Bridge Launch File
Launches the MAVLink bridge node for ArduSub communication
"""

from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import LaunchConfiguration
from launch.actions import DeclareLaunchArgument


def generate_launch_description():
    """Generate launch description for MAVLink bridge"""

    # Declare launch arguments
    connection_arg = DeclareLaunchArgument(
        'connection_string',
        default_value='/dev/ttyUSB0:115200',
        description='MAVLink connection string (serial or UDP)'
    )

    use_sim_arg = DeclareLaunchArgument(
        'use_sim',
        default_value='false',
        description='Use simulated MAVLink connection'
    )

    # MAVLink bridge node
    mavlink_bridge_node = Node(
        package='rov_mavlink',
        executable='mavlink_bridge_node',
        name='mavlink_bridge',
        parameters=[
            {
                'connection_string': LaunchConfiguration('connection_string'),
                'system_id': 1,
                'component_id': 191,
                'heartbeat_interval': 0.1,
                'telemetry_rate': 10,
                'servo_channel_mapping': [1, 2, 3, 4, 5, 6],
            }
        ],
        output='screen'
    )

    return LaunchDescription([
        connection_arg,
        use_sim_arg,
        mavlink_bridge_node,
    ])


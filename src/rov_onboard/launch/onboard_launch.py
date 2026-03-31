"""Launch onboard camera/arm nodes and optional MAVLink forwarding on LattePanda."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    enable_mavlink_forward = LaunchConfiguration('enable_mavlink_forward')
    qgc_ip = LaunchConfiguration('qgc_ip')
    qgc_port = LaunchConfiguration('qgc_port')
    pix_serial = LaunchConfiguration('pix_serial')
    pix_baud = LaunchConfiguration('pix_baud')
    mavlink_router_bin = LaunchConfiguration('mavlink_router_bin')

    run_mavlink_forward = ExecuteProcess(
        # Use env vars so launch substitutions can be injected cleanly into a shell command.
        cmd=[
            'bash', '-lc',
            'exec "${MAVLINK_ROUTER_BIN}" -e "${QGC_IP}:${QGC_PORT}" "${PIX_SERIAL}:${PIX_BAUD}"',
        ],
        additional_env={
            'MAVLINK_ROUTER_BIN': mavlink_router_bin,
            'QGC_IP': qgc_ip,
            'QGC_PORT': qgc_port,
            'PIX_SERIAL': pix_serial,
            'PIX_BAUD': pix_baud,
        },
        condition=IfCondition(PythonExpression([
            "'", enable_mavlink_forward, "'.lower() in ['1', 'true', 'yes'] and '", qgc_ip, "' != ''"
        ])),
        output='screen',
        respawn=True,
    )

    config = os.path.join(
        get_package_share_directory('rov_onboard'),
        'config',
        'onboard_params.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_mavlink_forward',
            default_value='true',
            description='If true, run mavlink-routerd to forward Pixhawk MAVLink to QGC.',
        ),
        DeclareLaunchArgument(
            'qgc_ip',
            default_value=EnvironmentVariable('QGC_IP', default_value=''),
            description='Control computer IP for MAVLink UDP forwarding. Empty disables forwarding.',
        ),
        DeclareLaunchArgument(
            'qgc_port',
            default_value='14550',
            description='Control computer UDP port for QGC MAVLink input.',
        ),
        DeclareLaunchArgument(
            'pix_serial',
            default_value='/dev/ttyACM0',
            description='Serial device for Pixhawk/Pix6 MAVLink over USB.',
        ),
        DeclareLaunchArgument(
            'pix_baud',
            default_value='115200',
            description='Serial baud for Pixhawk/Pix6 MAVLink over USB.',
        ),
        DeclareLaunchArgument(
            'mavlink_router_bin',
            default_value='mavlink-routerd',
            description='Executable name/path for MAVLink router process.',
        ),
        run_mavlink_forward,
        Node(
            package='rov_onboard',
            executable='camera_node',
            name='camera_node',
            parameters=[config],
            output='screen',
        ),
        Node(
            package='rov_onboard',
            executable='arm_servo_node',
            name='arm_servo_node',
            parameters=[config],
            output='screen',
        ),
    ])

"""Launch onboard camera/arm nodes and optional MAVLink forwarding to a topside GCS."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import EnvironmentVariable, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    enable_mavlink_forward = LaunchConfiguration('enable_mavlink_forward')
    gcs_ip = LaunchConfiguration('gcs_ip')
    gcs_port = LaunchConfiguration('gcs_port')
    # Backward-compatible aliases (legacy docs/scripts may still pass qgc_*).
    qgc_ip = LaunchConfiguration('qgc_ip')
    qgc_port = LaunchConfiguration('qgc_port')
    pix_serial = LaunchConfiguration('pix_serial')
    pix_baud = LaunchConfiguration('pix_baud')
    mavlink_router_bin = LaunchConfiguration('mavlink_router_bin')

    run_mavlink_forward = ExecuteProcess(
        # Use env vars so launch substitutions can be injected cleanly into a shell command.
        cmd=[
            'bash', '-lc',
            'TARGET_IP="${GCS_IP:-${QGC_IP}}"; '
            'TARGET_PORT="${GCS_PORT:-${QGC_PORT}}"; '
            'exec "${MAVLINK_ROUTER_BIN}" -e "${TARGET_IP}:${TARGET_PORT}" "${PIX_SERIAL}:${PIX_BAUD}"',
        ],
        additional_env={
            'MAVLINK_ROUTER_BIN': mavlink_router_bin,
            'GCS_IP': gcs_ip,
            'GCS_PORT': gcs_port,
            'QGC_IP': qgc_ip,
            'QGC_PORT': qgc_port,
            'PIX_SERIAL': pix_serial,
            'PIX_BAUD': pix_baud,
        },
        condition=IfCondition(PythonExpression([
            "'", enable_mavlink_forward, "'.lower() in ['1', 'true', 'yes'] and ('",
            gcs_ip,
            "' != '' or '",
            qgc_ip,
            "' != '')",
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
            description='If true, run mavlink-routerd to forward Pixhawk MAVLink to a topside GCS.',
        ),
        DeclareLaunchArgument(
            'gcs_ip',
            default_value=EnvironmentVariable('GCS_IP', default_value='192.168.50.1'),
            description='Topside Cockpit/GCS IP for MAVLink UDP forwarding. Defaults to 192.168.50.1.',
        ),
        DeclareLaunchArgument(
            'gcs_port',
            default_value='14550',
            description='Topside UDP port for MAVLink input (Cockpit/other GCS backend).',
        ),
        DeclareLaunchArgument(
            'qgc_ip',
            default_value=EnvironmentVariable('QGC_IP', default_value=''),
            description='Deprecated alias for gcs_ip (kept for backward compatibility).',
        ),
        DeclareLaunchArgument(
            'qgc_port',
            default_value='14550',
            description='Deprecated alias for gcs_port (kept for backward compatibility).',
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

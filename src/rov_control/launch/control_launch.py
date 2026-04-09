"""Launch control-laptop nodes (arm bridge + optional legacy UDP video bridge)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    enable_udp_video_bridge = LaunchConfiguration('enable_udp_video_bridge')
    enable_mavlink2rest = LaunchConfiguration('enable_mavlink2rest')
    mavlink2rest_bin = LaunchConfiguration('mavlink2rest_bin')
    mavlink2rest_args = LaunchConfiguration('mavlink2rest_args')

    run_mavlink2rest = ExecuteProcess(
        # Keep arg formatting configurable because mavlink2rest packaging/CLI varies by install source.
        cmd=[
            'bash', '-lc',
            'if command -v "${MAVLINK2REST_BIN}" >/dev/null 2>&1; then '
            '  if [ -n "${MAVLINK2REST_ARGS}" ]; then '
            '    exec "${MAVLINK2REST_BIN}" ${MAVLINK2REST_ARGS}; '
            '  else '
            '    exec "${MAVLINK2REST_BIN}"; '
            '  fi; '
            'else '
            '  echo "[mavlink2rest] binary not found: ${MAVLINK2REST_BIN} (skipping)"; '
            '  exit 0; '
            'fi',
        ],
        additional_env={
            'MAVLINK2REST_BIN': mavlink2rest_bin,
            'MAVLINK2REST_ARGS': mavlink2rest_args,
        },
        condition=IfCondition(enable_mavlink2rest),
        output='screen',
    )

    config = os.path.join(
        get_package_share_directory('rov_control'),
        'config',
        'control_params.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'enable_udp_video_bridge',
            default_value='false',
            description='Enable qgc_video_bridge_node for legacy UDP video consumers (e.g., QGC).',
        ),
        DeclareLaunchArgument(
            'enable_mavlink2rest',
            default_value='true',
            description='If true, start mavlink2rest for Cockpit telemetry/control backend.',
        ),
        DeclareLaunchArgument(
            'mavlink2rest_bin',
            default_value='mavlink2rest',
            description='Executable name/path for mavlink2rest.',
        ),
        DeclareLaunchArgument(
            'mavlink2rest_args',
            default_value='',
            description='Optional extra CLI args passed to mavlink2rest (leave blank to run with no args).',
        ),
        run_mavlink2rest,
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
            condition=IfCondition(enable_udp_video_bridge),
            output='screen',
        ),
    ])

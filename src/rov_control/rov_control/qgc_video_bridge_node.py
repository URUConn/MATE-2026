"""
QGC Video Bridge Node

Subscribes to the ROS compressed camera topic and forwards frames to QGroundControl
using an ffmpeg UDP stream.
"""

import subprocess
import threading
from typing import List, Optional

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage


class QgcVideoBridgeNode(Node):
    """
    QGC Video Bridge Node
    """
    def __init__(self) -> None:
        """
        Constructor for QGC Video Bridge Node
        """
        super().__init__('qgc_video_bridge_node')

        self.declare_parameter('input_topic', '/rov/camera/image_compressed')
        self.declare_parameter('ffmpeg_path', 'ffmpeg')
        self.declare_parameter('udp_host', '127.0.0.1')
        self.declare_parameter('udp_port', 5600)
        self.declare_parameter('bitrate', '2500k')
        self.declare_parameter('output_format', 'h264')
        self.declare_parameter('gop_size', 30)

        self.input_topic = str(self.get_parameter('input_topic').value)
        self.ffmpeg_path = str(self.get_parameter('ffmpeg_path').value)
        self.udp_host = str(self.get_parameter('udp_host').value)
        self.udp_port = int(self.get_parameter('udp_port').value)
        self.bitrate = str(self.get_parameter('bitrate').value)
        self.output_format = str(self.get_parameter('output_format').value).lower()
        self.gop_size = int(self.get_parameter('gop_size').value)

        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._ffmpeg_stderr_thread: Optional[threading.Thread] = None
        self._frame_count = 0

        # Subscribe to the ROS compressed image topic
        self.subscription = self.create_subscription(
            CompressedImage,
            self.input_topic,
            self._image_callback,
            10,
        )

        self._start_ffmpeg()
        self.get_logger().info(
            f'QGC bridge active: {self.input_topic} -> udp://{self.udp_host}:{self.udp_port} ({self.output_format})'
        )

    def _ffmpeg_command(self) -> List[str]:
        """
        Builds the ffmpeg command to forward the video stream to QGroundControl.
        :return: A list of command arguments for ffmpeg.
        """
        udp_target = f'udp://{self.udp_host}:{self.udp_port}?pkt_size=1316'
        ffmpeg_cmd = [
            self.ffmpeg_path,
            '-loglevel',
            'error',
            '-f',
            'mjpeg',
            '-i',
            '-',
            '-an',
            '-c:v',
            'libx264',
            '-preset',
            'ultrafast',
            '-tune',
            'zerolatency',
            '-pix_fmt',
            'yuv420p',
            '-b:v',
            self.bitrate,
            '-profile:v',
            'baseline',
            '-level',
            '3.1',
            '-g',
            str(max(1, self.gop_size)),
            '-keyint_min',
            str(max(1, self.gop_size)),
            '-bf',
            '0',
            '-sc_threshold',
            '0',
            '-fflags',
            'nobuffer',
            '-flags',
            'low_delay',
            '-flush_packets',
            '1',
        ]

        # QGC often prefers elementary H.264 over UDP; keep mpegts as fallback.
        if self.output_format == 'mpegts':
            ffmpeg_cmd.extend([
                '-muxdelay',
                '0',
                '-muxpreload',
                '0',
                '-f',
                'mpegts',
                udp_target,
            ])
        else:
            ffmpeg_cmd.extend([
                '-f',
                'h264',
                udp_target,
            ])

        return ffmpeg_cmd


    def _start_ffmpeg(self) -> None:
        """
        Starts the ffmpeg process to forward the video stream to QGroundControl. If ffmpeg is already running, it will be restarted.
        :return: None
        """
        self._stop_ffmpeg()
        try:
            self._ffmpeg_process = subprocess.Popen(
                self._ffmpeg_command(),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._ffmpeg_stderr_thread = threading.Thread(
                target=self._log_ffmpeg_stderr,
                daemon=True,
            )
            self._ffmpeg_stderr_thread.start()
        except FileNotFoundError:
            self._ffmpeg_process = None
            self.get_logger().error('ffmpeg not found. Install ffmpeg or set ffmpeg_path.')
        except OSError as exc:
            # Other OS-level errors when starting ffmpeg (e.g., permission denied, exec format error)
            self._ffmpeg_process = None
            self.get_logger().error(f'Failed to start ffmpeg due to OS error: {exc}')
        except Exception as exc:
            # Catch-all to prevent unexpected failures from crashing the node
            self._ffmpeg_process = None
            self.get_logger().error(f'Unexpected error while starting ffmpeg: {exc}')

    def _stop_ffmpeg(self) -> None:
        """
        Stops the ffmpeg process.
        :return: None
        """
        if self._ffmpeg_process is None:
            return

        process = self._ffmpeg_process
        try:
            if process.stdin:
                process.stdin.close()
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.get_logger().warning(
                    'ffmpeg process did not terminate gracefully within timeout; killing it.'
                )
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self.get_logger().error(
                        'ffmpeg process could not be killed and may still be running.'
                    )
                    # Keep the process handle so a later attempt can retry cleanup.
                    return
        except Exception as exc:
            # Log unexpected errors during shutdown instead of swallowing them.
            self.get_logger().error(f'Error while stopping ffmpeg process: {exc}')
        finally:
            # Only clear the process reference and join the stderr thread if the process exited.
            if process.poll() is not None:
                self._ffmpeg_process = None
                if self._ffmpeg_stderr_thread is not None:
                    self._ffmpeg_stderr_thread.join(timeout=1.0)
                    self._ffmpeg_stderr_thread = None

    def _log_ffmpeg_stderr(self) -> None:
        """
        Reads ffmpeg stderr line-by-line and forwards each line to the ROS logger.
        Runs in a daemon thread and exits when the ffmpeg process closes its stderr pipe.
        :return: None
        """
        process = self._ffmpeg_process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.decode(errors='replace').rstrip()
            if line:
                self.get_logger().error(f'ffmpeg: {line}')

    def _image_callback(self, msg: CompressedImage) -> None:
        """
        Callback function for QGC Video Bridge Node
        :param msg: The CompressedImage message containing the video frame data to forward to QGroundControl.
        :return: None
        """
        process = self._ffmpeg_process
        if process is None or process.stdin is None or process.poll() is not None:
            self._start_ffmpeg()
            process = self._ffmpeg_process
            if process is None or process.stdin is None:
                return

        try:
            process.stdin.write(msg.data)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            self.get_logger().warn('ffmpeg pipe interrupted. Restarting bridge process.')
            self._start_ffmpeg()
            return

        # Log the frame count to the console for debugging
        self._frame_count += 1
        if self._frame_count % 300 == 0:
            self.get_logger().info(f'Forwarded {self._frame_count} frames to QGC')

    def destroy_node(self) -> bool:
        """
        Overrides the default destroy_node to ensure the ffmpeg process is properly terminated when the node is destroyed.
        :return: True if the node was successfully destroyed, False otherwise.
        """
        self._stop_ffmpeg()
        return super().destroy_node()


def main(args=None) -> None:
    """
    Main entry point for the QGC Video Bridge Node.
    :param args: Arguments passed from the command line.
    :return: None
    """
    rclpy.init(args=args)
    node = QgcVideoBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


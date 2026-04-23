"""Crab detector node (YOLO11m, 512x512) — idle until toggled ON via /rov/crab/trigger."""

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from rov_msgs.msg import CrabClassification, CrabClassifyTrigger

CLASS_NAMES = ['european-green-crab', 'jonah-crab', 'native-rock-crab']
INPUT_SIZE  = 512


class CrabDetectorNode(Node):

    def __init__(self):
        super().__init__('crab_classifier_node')

        self.declare_parameter('model_path',            '/home/lattepanda/MATE2026/models/crab_model.onnx')
        self.declare_parameter('confidence_threshold',  0.5)
        self.declare_parameter('input_topic',           '/rov/camera/image_compressed')
        self.declare_parameter('output_topic',          '/rov/crab/classification')
        self.declare_parameter('trigger_topic',         '/rov/crab/trigger')

        model_path       = self.get_parameter('model_path').value
        self.conf_thresh = float(self.get_parameter('confidence_threshold').value)
        input_topic      = self.get_parameter('input_topic').value
        output_topic     = self.get_parameter('output_topic').value
        trigger_topic    = self.get_parameter('trigger_topic').value

        import onnxruntime as ort
        self.session    = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.get_logger().info(f'YOLO11m loaded: {model_path}')

        self._active = False   # starts OFF

        self.create_subscription(CompressedImage,     input_topic,   self._image_cb,   10)
        self.create_subscription(CrabClassifyTrigger, trigger_topic, self._trigger_cb, 10)
        self.result_pub = self.create_publisher(CrabClassification, output_topic, 10)

        self.get_logger().info(
            f'Crab detector READY (IDLE). Waiting for toggle on [{trigger_topic}]'
        )

    def _trigger_cb(self, msg: CrabClassifyTrigger):
        self._active = msg.active
        self.get_logger().info(f'Detector toggled {"ON" if self._active else "OFF"}')

    def _preprocess(self, frame):
        img = cv2.resize(frame, (INPUT_SIZE, INPUT_SIZE))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))       # HWC -> CHW
        return np.expand_dims(img, axis=0)        # -> BCHW (1, 3, 512, 512)

    def _postprocess(self, output):
        """
        YOLO11 ONNX output: (1, 7, 5376)
        Rows per box: [x, y, w, h, conf_class0, conf_class1, conf_class2]
        """
        preds = output[0][0].T    # shape: (5376, 7)
        detections = []
        for pred in preds:
            class_scores = pred[4:]
            class_id     = int(np.argmax(class_scores))
            confidence   = float(class_scores[class_id])
            if confidence >= self.conf_thresh:
                label = CLASS_NAMES[class_id] if class_id < len(CLASS_NAMES) else f'class_{class_id}'
                detections.append((label, confidence, class_id))
        return detections

    def _image_cb(self, msg: CompressedImage):
        if not self._active:
            return

        np_arr = np.frombuffer(msg.data, np.uint8)
        frame  = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return

        tensor     = self._preprocess(frame)
        outputs    = self.session.run(None, {self.input_name: tensor})
        detections = self._postprocess(outputs)

        if not detections:
            self.get_logger().info('No crabs detected.')
            return

        # Publish the highest-confidence detection
        best_label, best_conf, best_class_id = max(detections, key=lambda x: x[1])

        result                 = CrabClassification()
        result.header.stamp    = msg.header.stamp
        result.header.frame_id = 'camera_link'
        result.label           = best_label
        result.confidence      = best_conf
        result.class_id        = best_class_id
        self.result_pub.publish(result)

        self.get_logger().info(
            f'{len(detections)} detection(s). Best: [{best_label}] conf={best_conf:.2f}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = CrabDetectorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
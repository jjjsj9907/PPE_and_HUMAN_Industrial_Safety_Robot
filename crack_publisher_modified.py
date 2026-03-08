
#!/usr/bin/env python3
import os
import sys
import math
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge
from ultralytics import YOLO
import tf2_ros
import tf2_geometry_msgs
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
import queue
import threading

# ========================
# 상수 정의
# ========================
MODEL_PATH        = '/home/hyojae/rokey_ws/model/my_best.pt'
COLOR_TOPIC       = '/robot1/oakd/rgb/preview/image_raw'
DEPTH_TOPIC       = '/robot1/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot1/oakd/stereo/camera_info'
TARGET_CLASS_ID   = 0
PUBLISH_TOPIC     = '/object_position'
NORMALIZE_DEPTH_M = 5.0
WINDOW_NAME       = 'YOLO Detection'

qos_profile = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL
)

def seg(img):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 50, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 50, 50])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv_img, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv_img, lower_red2, upper_red2)
    bg_mask = cv2.bitwise_or(mask1, mask2)
    kernel = np.ones((5, 5), np.uint8)
    bg_mask = cv2.morphologyEx(bg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    bg_mask = cv2.morphologyEx(bg_mask, cv2.MORPH_OPEN, kernel, iterations=2)
    bg_mask = cv2.GaussianBlur(bg_mask, (5, 5), 0)
    fg_mask = cv2.bitwise_not(bg_mask)
    white_pixel_count = np.count_nonzero(fg_mask)
    fg_mask_3ch = cv2.merge([fg_mask, fg_mask, fg_mask])
    foreground = cv2.bitwise_and(img, fg_mask_3ch)
    white_bg = np.full_like(img, 255)
    bg_mask_3ch = cv2.merge([bg_mask, bg_mask, bg_mask])
    background = cv2.bitwise_and(white_bg, bg_mask_3ch)
    result = cv2.add(foreground, background)
    return result, white_pixel_count

class YoloDepthNode(Node):
    def __init__(self):
        super().__init__('yolo_depth_node')
        self.bridge = CvBridge()
        self.K = None
        self.image_queue = queue.Queue(maxsize=1)
        self.depth_mm = None
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)
        self.model = YOLO(MODEL_PATH)
        self.names = getattr(self.model, 'names', [])
        self.position_pub = self.create_publisher(PointStamped, PUBLISH_TOPIC, qos_profile)

        self.create_subscription(Image, COLOR_TOPIC, self.image_callback, 10)
        self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)
        self.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, self.camera_info_callback, 10)

        self.worker_thread = threading.Thread(target=self.visualization_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def camera_info_callback(self, msg):
        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)

    def depth_callback(self, msg):
        depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        self.depth_mm = np.nan_to_num(depth, nan=0.0).astype(np.float32)

    def image_callback(self, msg):
        img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        if not self.image_queue.full():
            self.image_queue.put(img)
        else:
            try:
                self.image_queue.get_nowait()
            except queue.Empty:
                pass
            self.image_queue.put(img)

    def visualization_loop(self):
        while rclpy.ok():
            try:
                img = self.image_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self.depth_mm is None or self.K is None:
                continue

            results = self.model(img, stream=True)

            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    if cls != TARGET_CLASS_ID:
                        continue
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                    if not (0 <= cx < self.depth_mm.shape[1] and 0 <= cy < self.depth_mm.shape[0]):
                        continue

                    depth_m = self.depth_mm[cy, cx] / 1000.0
                    if depth_m <= 0 or depth_m > NORMALIZE_DEPTH_M:
                        continue

                    fx, fy = self.K[0,0], self.K[1,1]
                    px, py = self.K[0,2], self.K[1,2]
                    X = (cx - px) * depth_m / fx
                    Y = (cy - py) * depth_m / fy
                    Z = depth_m

                    pt = PointStamped()
                    pt.header.stamp = rclpy.time.Time().to_msg()
                    pt.header.frame_id = 'base_link'
                    pt.point.x = Z
                    pt.point.y = -X
                    pt.point.z = -Y

                    self.position_pub.publish(pt)

                    cm_per_pixel = 0.1 * depth_m + 0.002
                    real_width_cm = (img.shape[1] // 2 - cx) * cm_per_pixel
                    area_img = img[y1:y2, x1:x2]
                    result_img, area_pixels = seg(area_img)
                    area_cm2 = area_pixels * (cm_per_pixel ** 2)
                    img[y1:y2, x1:x2] = result_img

                    label = self.names[cls] if cls < len(self.names) else f"class_{cls}"
                    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(img, f"{label} {box.conf[0]:.2f}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                    cv2.circle(img, (cx, cy), 4, (0, 255, 0), -1)
                    cv2.putText(img, f"{depth_m:.2f}m", (cx + 5, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(img, f"Area: {int(area_cm2):,d}sq.cm", (x1, y2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imshow(WINDOW_NAME, cv2.resize(img, (img.shape[1]*2, img.shape[0]*2)))
            if cv2.waitKey(1) & 0xFF == ord('q'):
                rclpy.shutdown()
                break

def main():
    rclpy.init()
    node = YoloDepthNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        while rclpy.ok():
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()

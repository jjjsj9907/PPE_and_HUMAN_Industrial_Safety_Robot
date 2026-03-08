#!/usr/bin/env python3
import os
import sys
import math
import cv2
import numpy as np
import rclpy
import random
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge
from ultralytics import YOLO
from paho.mqtt import client as mqtt_client

# ========================
# MQTT 설정
# ========================
broker = 'g11c1e1e.ala.eu-central-1.emqxsl.com'
port = 8883
username = 'okj1812'
password = 'okj1812'
mqtt_topic = "python/mqtt"
client_id = f'python-mqtt-{random.randint(0, 100)}'

# ========================
# YOLO 설정
# ========================
MODEL_PATH        = '/home/hyojae/rokey_ws/model/my_best.pt'
COLOR_TOPIC       = '/robot1/oakd/rgb/preview/image_raw'
DEPTH_TOPIC       = '/robot1/oakd/stereo/image_raw'
TARGET_CLASS_ID   = 0
PUBLISH_TOPIC     = '/object_position'
NORMALIZE_DEPTH_M = 5.0


# ========================
# MQTT 연결
# ========================
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to MQTT Broker!")
        else:
            print(f"❌ Failed to connect, return code {rc}")

    client = mqtt_client.Client(client_id=client_id, protocol=mqtt_client.MQTTv311)
    client.tls_set()
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    client.loop_start()
    return client


# ========================
# 전경 분리용 함수
# ========================
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


# ========================
# ROS2 + MQTT 통합 노드
# ========================
class YoloDepthNode(Node):
    def __init__(self, mqtt_client):
        super().__init__('yolo_depth_node')
        self.model = YOLO(MODEL_PATH)
        self.names = getattr(self.model, 'names', [])
        self.bridge = CvBridge()
        self.latest_depth = None
        self.mqtt_client = mqtt_client

        self.position_pub = self.create_publisher(PointStamped, PUBLISH_TOPIC, 10)
        self.create_subscription(Image, COLOR_TOPIC, self.color_callback, 10)
        self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)

        cv2.namedWindow("YOLO+Depth", cv2.WINDOW_AUTOSIZE)

    def depth_callback(self, msg: Image):
        depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        if depth.dtype == np.float32:
            depth = np.nan_to_num(depth, nan=0.0) * 1000.0
        self.latest_depth = depth.astype(np.uint16)

    def color_callback(self, msg: Image):
        if self.latest_depth is None:
            self.get_logger().warn("Waiting for first depth frame...")
            return

        img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        results = self.model(img, stream=True)

        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                if cls != TARGET_CLASS_ID:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2)//2, (y1 + y2)//2
                depth_mm = int(self.latest_depth[cy, cx])
                depth_m = depth_mm / 1000.0
                if depth_m == 0.0:
                    continue

                dx_pixel = img.shape[1] // 2 - cx 
                cm_per_pixel = 0.1 * depth_m + 0.002
                real_width_cm = dx_pixel * cm_per_pixel
                real_width_m = real_width_cm / 100.0
                depth = (depth_m**2 - real_width_m**2)**0.5

                point_msg = PointStamped()
                point_msg.header.stamp = self.get_clock().now().to_msg()
                point_msg.header.frame_id = 'base_link'
                point_msg.point.x = depth_m
                point_msg.point.y = real_width_m
                point_msg.point.z = 0.0
                self.position_pub.publish(point_msg)

                result, area_pixels = seg(img[y1:y2, x1:x2])
                img[y1:y2, x1:x2] = result
                area_cm2 = area_pixels * (cm_per_pixel ** 2)

                label = self.names[cls] if cls < len(self.names) else f"class_{cls}"
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(img, f"{label} {box.conf[0]:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                cv2.circle(img, (cx, cy), 4, (0, 255, 0), -1)
                cv2.putText(img, f"{depth_m:.2f}m", (cx + 5, cy - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(img, f"Area: {int(area_cm2):,d}sq.cm", (x1, y2 + 25), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                # ✅ MQTT 전송 메시지
                mqtt_msg = f"depth={depth:.2f}, y_offset={real_width_m:.2f}, area={int(area_cm2)}"
                self.mqtt_client.publish(mqtt_topic, mqtt_msg)
                print(f"📡 MQTT Sent: {mqtt_msg}")

        cv2.imshow("YOLO+Depth", cv2.resize(img, (img.shape[1]*2, img.shape[0]*2)))
        if cv2.waitKey(1) & 0xFF == ord('q'):
            rclpy.shutdown()


# ========================
# 사용자 숫자 전송
# ========================
def send_manual_input(mqtt_client):
    value = input("전송할 숫자를 입력하세요: ").strip()
    if value:
        mqtt_client.publish(mqtt_topic, value)
        print(f"✅ 사용자 입력 MQTT 전송: {value}")


# ========================
# Main
# ========================
def main():
    mqtt_client = connect_mqtt()
    send_manual_input(mqtt_client)

    rclpy.init()
    node = YoloDepthNode(mqtt_client)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

#ros2 run rokey_pjt crack_publisher2 --ros-args -r /tf:=/robot1/tf -r /tf_static:=/robot1/tf_static -r __ns:=/robot1

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from cv_bridge import CvBridge
import cv2
import math
import os
import sys
import threading
import queue
from ultralytics import YOLO
import numpy as np
from rclpy.executors import MultiThreadedExecutor
from geometry_msgs.msg import PointStamped
import tf2_ros
import tf2_geometry_msgs  # 꼭 필요
from paho.mqtt import client as mqtt_client
#7.16
from rclpy.qos import QoSDurabilityPolicy
from rclpy.qos import QoSHistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import QoSReliabilityPolicy
import random
from datetime import datetime, timezone
import json

MARKER_TOPIC = 'detected_objects_marker'
MAP_TOPIC = 'map_points'


qos_profile = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE, 
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10, 
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL
    )
# ========================
# MQTT 설정
# ========================
broker = 'p021f2cb.ala.asia-southeast1.emqxsl.com'
port = 8883
username = 'Rokey'
password = '1234567'
mqtt_topic = "detect"
client_id = f'python-mqtt-{random.randint(0, 100)}'


# ========================
# MQTT 연결
# ========================
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("\u2705 Connected to MQTT Broker!")
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
# 설정
# ========================
MODEL_PATH        = '/home/kunwookpark/D1_ws/src/waypoint/waypoint/real_best_320.pt' 
IMAGE_TOPIC = '/robot1/oakd/rgb/preview/image_raw'
DEPTH_TOPIC = '/robot1/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot1/oakd/stereo/camera_info'
TARGET_CLASS_ID = 0
NORMALIZE_DEPTH_RANGE = 3.0
WINDOW_NAME = 'YOLO Detection'


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
# 노드 정의
# ========================
class DetectWithDepthWithTf(Node):
    def __init__(self):
        super().__init__('detect_with_depth_with_tf')

        self.K = None
        self.should_exit = False
        self.should_shutdown = False

        self.depth_mm = None
        self.depth_colored = None

        self.detect_cx = 0
        self.detect_cy = 0

        self.lock = threading.Lock()  # 공유 변수 보호용 Lock

        self.bridge = CvBridge()
        self.image_queue = queue.Queue(maxsize=1)
        self.mqtt_client = connect_mqtt()

        # TF Buffer와 Listener 준비
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # 5초 후에 변환 시작
        self.get_logger().info("TF Tree 안정화 시작. 5초 후 변환 시작합니다.")
        self.start_timer = self.create_timer(5.0, self.start_transform)

        # 모델 로딩
        if not os.path.exists(MODEL_PATH):
            self.get_logger().error(f"Model not found: {MODEL_PATH}")
            sys.exit(1)

        self.model = YOLO(MODEL_PATH)
        self.class_names = getattr(self.model, 'names', [])

        # 구독 설정
        self.rgb_img_subscription = self.create_subscription(Image, IMAGE_TOPIC, self.image_callback, 10)
        self.stereo_img_subscription = self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)
        self.camera_info_subscription = self.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, self.camera_info_callback, 10)

        # 7.16
        self.map_point_pub = self.create_publisher(PointStamped, MAP_TOPIC, qos_profile)

        # 백그라운드 스레드 시작
        self.worker_thread = threading.Thread(target=self.visualization_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def camera_info_callback(self, msg):
        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)
            self.get_logger().info(f"CameraInfo received: fx={self.K[0,0]:.2f}, fy={self.K[1,1]:.2f}, cx={self.K[0,2]:.2f}, cy={self.K[1,2]:.2f}")

    def depth_callback(self, msg):
        if self.should_exit or self.K is None:
            return

        depth_mm = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')

        depth_vis = np.nan_to_num(depth_mm, nan=0.0)
        depth_vis = np.clip(depth_vis, 0, NORMALIZE_DEPTH_RANGE * 1000)
        depth_vis = (depth_vis / (NORMALIZE_DEPTH_RANGE * 1000) * 255).astype(np.uint8)
        depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

        with self.lock:
            self.depth_mm = depth_mm
            self.depth_colored = depth_colored

    def image_callback(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

        if not self.image_queue.full():
            self.image_queue.put(frame)
        else:
            try:
                self.image_queue.get_nowait()
            except queue.Empty:
                pass
            self.image_queue.put(frame)

    def visualization_loop(self):
        while not self.should_shutdown:
            try:
                frame = self.image_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                results = self.model(frame, stream=True, verbose=False)
            except Exception as e:
                self.get_logger().error(f"YOLO inference error: {e}")
                continue

            with self.lock:
                if self.depth_mm is None or self.depth_colored is None:
                    continue
                depth_mm = self.depth_mm.copy()
                depth_colored = self.depth_colored.copy()

                object_count = 0
                # 수정된 부분: visualization_loop 함수 내부
                for r in results:
                    for box in r.boxes:

                        ##tfp
                        point_base1 = PointStamped()
                        point_base1.header.stamp = rclpy.time.Time().to_msg()
                        # point_base.header.stamp = self.get_clock().now().to_msg()  # 현재 시간 사용
                        point_base1.header.frame_id = 'base_link'
                        point_base1.point.x = 0.0  # 카메라 좌표계에서 Z는 전방 거리
                        point_base1.point.y = 0.0 # 카메라 좌표계에서 X는 좌우 (부호 주의)
                        point_base1.point.z = 0.0 # 카메라 좌표계에서 Y는 상하 (부호 주의)

                        # base_link → map 변환
                        try:
                            point_map1 = self.tf_buffer.transform(
                                point_base1,
                                'map',
                                timeout=rclpy.duration.Duration(seconds=0.5)
                            )
                            self.get_logger().info(f"[Map]       ({point_map1.point.x:.2f}, {point_map1.point.y:.2f}, {point_map1.point.z:.2f})")
                            msg_dict = {
                                "type" : 'tf',
                                "location": [
                                    round(point_map1.point.x, 2),
                                    round(point_map1.point.y, 2)
                                ]
                            }
                            self.mqtt_client.publish('detect', json.dumps(msg_dict))

                        except Exception as e:
                            self.get_logger().warn(f"TF transform to map failed: {e}")


                        cls = int(box.cls[0])
                        if cls != 0:
                            continue

                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = math.ceil(box.conf[0] * 100) / 100
                        label = self.class_names[cls] if cls < len(self.class_names) else f"class_{cls}"
                        
                        
                        # 바운딩 박스 중심점 계산
                        detect_cx = int((x1 + x2) / 2)
                        detect_cy = int((y1 + y2) / 2)
                        
                        result, area_pixels = seg(frame[y1:y2, x1:x2])
                        frame[y1:y2, x1:x2] = result
                        
                        # 범위 체크
                        if 0 <= detect_cx < depth_mm.shape[1] and 0 <= detect_cy < depth_mm.shape[0]:
                            # 같은 좌표에서 depth 값 가져오기
                            distance_mm = depth_mm[detect_cy, detect_cx]
                            distance_m = distance_mm / 1000.0
                            
                            # depth 값이 유효한지 확인
                            if distance_m <= 0 or distance_m > NORMALIZE_DEPTH_RANGE:
                                self.get_logger().warn(f"Invalid depth value: {distance_m:.2f}m at ({detect_cx}, {detect_cy})")
                                continue
                                
                            self.get_logger().info(f"center at (u={detect_cx}, v={detect_cy}) → Distance = {distance_m:.2f} meters")

                            
                            
                            # 카메라 파라미터
                            fx = self.K[0,0]
                            fy = self.K[1,1]
                            cx = self.K[0,2]
                            cy = self.K[1,2]
                            
                            # 3D 좌표 변환 (같은 좌표 사용)
                            X = (detect_cx - cx) * distance_m / fx
                            Y = (detect_cy - cy) * distance_m / fy
                            Z = distance_m 
                            area = area_pixels * (distance_m/ fx) *(distance_m / fy)
                            self.get_logger().info(f"3D coordinates: X={X:.3f}, Y={Y:.3f}, Z={Z:.3f}")
                            
                            cv2.circle(depth_colored, (detect_cx, detect_cy), 5, (0, 0, 0), -1)
                            # cv2.putText(frame, f"{label}: {conf}, {distance_m:.2f}m, {area: .2f}sqm", (x1, y1 - 10),
                            #             cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                            cv2.putText(frame, f"{label}: {conf:.2f}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                            cv2.putText(frame, f"{distance_m:.2f}m, {area:.3f}sqm", (x1, y2 + 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 128, 255), 2)
                            
                            try:
                                # base_link 기준 포인트 생성
                                point_base = PointStamped()
                                point_base.header.stamp = rclpy.time.Time().to_msg()
                                # point_base.header.stamp = self.get_clock().now().to_msg()  # 현재 시간 사용
                                point_base.header.frame_id = 'base_link'
                                point_base.point.x = Z # 카메라 좌표계에서 Z는 전방 거리
                                point_base.point.y = -X  # 카메라 좌표계에서 X는 좌우 (부호 주의)
                                point_base.point.z = -Y # 카메라 좌표계에서 Y는 상하 (부호 주의)

                                point_map_send_data = PointStamped()
                                # base_link → map 변환
                                try:
                                    point_map = self.tf_buffer.transform(
                                        point_base,
                                        'map',
                                        timeout=rclpy.duration.Duration(seconds=0.5)
                                    )
                                    self.get_logger().info(f"[Base_link] ({point_base.point.x:.2f}, {point_base.point.y:.2f}, {point_base.point.z:.2f})")
                                    self.get_logger().info(f"[Map]       ({point_map.point.x:.2f}, {point_map.point.y:.2f}, {point_map.point.z:.2f})")
                                    
                                    # 퍼블리시 (필요시)
                                    # point_map.header.stamp = self.get_clock().now().to_msg()
                                    # self.map_point_pub.publish(point_map)


                                    point_map_send_data.header.stamp = rclpy.time.Time().to_msg()
                                    point_map_send_data.header.frame_id = 'map'
                                    point_map_send_data.point.x = point_map.point.x
                                    point_map_send_data.point.y = point_map.point.y
                                    # point_map_send_data.point.x = -0.19
                                    # point_map_send_data.point.y = -2.6
                                    point_map_send_data.point.z = point_map.point.z   

                                    msg_dict = {
                                        "robot_id": "robot1",
                                        "type": "crack1",
                                        "location": [round(point_map_send_data.point.x, 2), round(point_map_send_data.point.y, 2)],
                                        "depth": round(distance_m, 2),
                                        "area": round(area, 2),
                                        "timestamp": datetime.now(timezone.utc).isoformat()
                                    }
                                    _ , frame_w = frame.shape[:2]

                                    cx_ratio = detect_cx / frame_w
                                    if not (0.2 < cx_ratio < 0.8):
                                        # self.get_logger().info(f"❌ Detection at side: cx_ratio={cx_ratio:.2f}, skipping publish.")
                                        # continue
                                        if conf > 0.6:

                                            self.mqtt_client.publish(mqtt_topic, json.dumps(msg_dict))
                                            self.get_logger().info(f"📡 MQTT Published: {msg_dict}")


                                except Exception as e:
                                    self.get_logger().warn(f"TF transform to map failed: {e}")

                            except Exception as e:
                                self.get_logger().warn(f"Unexpected error: {e}")

                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        object_count += 1

            cv2.putText(frame, f"Objects: {object_count}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            display_img = cv2.resize(frame, (frame.shape[1] * 2, frame.shape[0] * 2))
            cv2.imshow(WINDOW_NAME, display_img)

            key = cv2.waitKey(1)
            if key == ord('q'):
                self.should_shutdown = True
                self.get_logger().info("Q pressed. Shutting down...")
                break

    def start_transform(self):
        self.get_logger().info("TF Tree 안정화 완료. 변환 시작합니다.")

        # 주기적 변환 타이머 등록
        # self.transform_timer = self.create_timer(2.0, self.timer_callback)

        # 시작 타이머 중지 (한 번만 실행)
        self.start_timer.cancel()


# ========================
# 메인 함수
# ========================
def main():
    rclpy.init()
    node = DetectWithDepthWithTf()
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        while rclpy.ok() and not node.should_shutdown:
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()
        print("Shutdown complete.")
        sys.exit(0)

if __name__ == '__main__':
    main()

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
from datetime import datetime, timezone
#7.16
from rclpy.qos import QoSDurabilityPolicy
from rclpy.qos import QoSHistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import QoSReliabilityPolicy

#7.17
from vision_msgs.msg import BaseCoordinate

# 7.18
# mqtt 슛 ~
import json
from paho.mqtt import client as mqtt_client
import time
broker = 'p021f2cb.ala.asia-southeast1.emqxsl.com'
port = 8883
username = 'Rokey'
password = '1234567'
topic = "detect"
client_id = f'yolo_vision'


MARKER_TOPIC = 'detected_objects_marker'
MAP_TOPIC = 'map_points'
BASE_TOPIC = "base_points"

LEN_THRESHOLD = 0.3

qos_profile = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE, 
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10, 
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL
    )



# ========================
# 설정
# ========================
MODEL_PATH = '/home/jsj2204/Downloads/yolov5n_4classes.pt'
IMAGE_TOPIC = '/robot3/oakd/rgb/preview/image_raw'
DEPTH_TOPIC = '/robot3/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot3/oakd/stereo/camera_info'
TARGET_CLASS_ID = 2
NORMALIZE_DEPTH_RANGE = 3.0
WINDOW_NAME = 'YOLO Detection'


# ========================
# 노드 정의
# ========================

##########7_21 filtering shoot~############
class OutlierFilter:
    def __init__(self, window_size=5, outlier_threshold=1.0):
        self.window = []
        self.window_size = window_size
        self.outlier_threshold = outlier_threshold  # 미터 단위
        
    def update(self, measurement):
        # 윈도우가 비어있으면 바로 추가
        if len(self.window) == 0:
            self.window.append(measurement)
            return measurement
        
        # 현재 평균과의 차이 확인
        current_avg = np.mean(self.window)
        if abs(measurement - current_avg) > self.outlier_threshold:
            # 아웃라이어면 이전 값 반환
            return current_avg
        
        # 정상 값이면 윈도우에 추가
        self.window.append(measurement)
        if len(self.window) > self.window_size:
            self.window.pop(0)
        
        # 이동평균 반환
        return np.mean(self.window)

class SimpleKalmanFilter:
    def __init__(self, process_variance=1e-2, measurement_variance=1e-2):
        # 상태 변수
        self.x = 0.0  # 추정된 거리
        self.P = 1.0  # 추정 오차의 공분산
        
        # 노이즈 파라미터 (더 균형잡히게 조정)
        self.Q = process_variance    # 프로세스 노이즈
        self.R = measurement_variance # 측정 노이즈
        
        self.is_initialized = False
        self.outlier_filter = OutlierFilter(window_size=3, outlier_threshold=2.0)
    
    def update(self, measurement):
        # 먼저 아웃라이어 필터 적용
        filtered_measurement = self.outlier_filter.update(measurement)
        
        if not self.is_initialized:
            # 첫 번째 측정값으로 초기화 (아웃라이어 필터링된 값 사용)
            self.x = filtered_measurement
            self.is_initialized = True
            return self.x
        
        # 예측 단계
        P_pred = self.P + self.Q
        
        # 업데이트 단계
        K = P_pred / (P_pred + self.R)
        self.x = self.x + K * (filtered_measurement - self.x)
        self.P = (1 - K) * P_pred
        
        return self.x
###########################################################################


class DetectWithDepthWithTf(Node):
    def __init__(self):
        super().__init__('detect_with_depth_with_tf')
        #7_21
        self.last_coord_len = 0

        # mqtt setup
        # MQTT 클라이언트 초기화
        self.mqtt_client = None
        self.mqtt_connected = False
        self.setup_mqtt()

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

        # 칼만 필터
        self.kalman_filter = SimpleKalmanFilter(
            process_variance=1e-2,     # 조금 더 크게 - 빠른 변화 허용
            measurement_variance=1e-2  # 훨씬 작게 - 센서를 더 신뢰
        )

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

        #7.17
        self.base_coor_pub = self.create_publisher(BaseCoordinate, BASE_TOPIC, qos_profile)

        # 백그라운드 스레드 시작
        self.worker_thread = threading.Thread(target=self.visualization_loop)
        self.worker_thread.daemon = True
        self.worker_thread.start()


    def apply_average_filter(self, depth_image, kernel_size=5):
        """5x5 평균 필터 적용"""
        # 0값(무효한 뎁스)은 필터링에서 제외
        mask = depth_image > 0
        
        # 평균 필터 커널 생성
        kernel = np.ones((kernel_size, kernel_size), np.float32) / (kernel_size * kernel_size)
        
        # 유효한 픽셀만 필터링
        filtered = cv2.filter2D(depth_image.astype(np.float32), -1, kernel)
        
        # 원본에서 0이었던 픽셀은 0으로 유지
        filtered[~mask] = 0
        
        return filtered.astype(depth_image.dtype)

    def camera_info_callback(self, msg):
        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)
            self.get_logger().info(f"CameraInfo received: fx={self.K[0,0]:.2f}, fy={self.K[1,1]:.2f}, cx={self.K[0,2]:.2f}, cy={self.K[1,2]:.2f}")

    def depth_callback(self, msg):
        if self.should_exit or self.K is None:
            return

        raw_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')

        # 5x5 평균 필터 적용
        depth_mm = self.apply_average_filter(raw_depth, kernel_size=5)

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
                results = self.model(frame, stream=True)
            except Exception as e:
                self.get_logger().error(f"YOLO inference error: {e}")
                continue

            with self.lock:
                if self.depth_mm is None or self.depth_colored is None:
                    continue
                depth_mm = self.depth_mm.copy()
                depth_colored = self.depth_colored.copy()

                object_count = 0
                
                # 모든 detection된 객체들을 저장할 리스트
                all_detections = []
                class_2_boxes = []  # class 2 (person) 바운딩 박스들
                
                # 첫 번째 패스: 모든 detection 수집
                for r in results:
                    for box in r.boxes:
                        cls = int(box.cls[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        
                        # confidence threshold 확인
                        if conf < 0.65:
                            continue
                        
                        detection = {
                            'class': cls,
                            'bbox': (x1, y1, x2, y2),
                            'confidence': conf,
                            'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                        }
                        
                        all_detections.append(detection)
                        
                        # class 2 (person) 박스들 별도 저장
                        if cls == 2:
                            class_2_boxes.append(detection)

                # 두 번째 패스: class 2 박스에 대해 조건 확인 및 처리
                for person_detection in class_2_boxes:
                    person_bbox = person_detection['bbox']
                    person_x1, person_y1, person_x2, person_y2 = person_bbox
                    person_center = person_detection['center']
                    person_conf = person_detection['confidence']
                    
                    # 이 person 박스 안에 있는 다른 클래스들 찾기
                    classes_inside = set()
                    
                    for detection in all_detections:
                        if detection['class'] == 2:  # person 자체는 제외
                            continue
                        
                        obj_center_x, obj_center_y = detection['center']
                        
                        # 객체의 중심점이 person 바운딩 박스 안에 있는지 확인
                        if (person_x1 <= obj_center_x <= person_x2 and 
                            person_y1 <= obj_center_y <= person_y2):
                            classes_inside.add(detection['class'])
                            
                            # 디버깅을 위한 로그
                            self.get_logger().debug(f"Class {detection['class']} found inside person box at ({obj_center_x}, {obj_center_y})")

                    # 조건 확인: class 0, 1, 3 중 하나라도 없는지 확인
                    required_classes = {0, 1, 3}
                    condition_met = not required_classes.issubset(classes_inside)  # 조건 반전!
                    
                    missing_classes = required_classes - classes_inside
                    self.get_logger().info(f"Person box: classes inside = {classes_inside}, missing = {missing_classes}, condition met = {condition_met}")
                    
                    # 시각화 - person 바운딩 박스 그리기
                    color = (0, 255, 0) if condition_met else (0, 0, 255)  # 초록색 = 조건 만족(누락 있음), 빨간색 = 조건 불만족(모두 있음)
                    thickness = 3 if condition_met else 2
                    cv2.rectangle(frame, (person_x1, person_y1), (person_x2, person_y2), color, thickness)
                    
                    # 조건이 만족될 때만 메시지 퍼블리시 진행
                    if condition_met:
                        detect_cx, detect_cy = person_center
                        
                        # 범위 체크
                        if 0 <= detect_cx < depth_mm.shape[1] and 0 <= detect_cy < depth_mm.shape[0]:
                            # depth 값 가져오기
                            distance_mm = depth_mm[detect_cy, detect_cx]
                            distance_m = distance_mm / 1000.0

                            # 칼만 필터 적용
                            filtered_distance = self.kalman_filter.update(distance_m)
                            
                            # depth 값이 유효한지 확인
                            if filtered_distance <= 0 or filtered_distance > NORMALIZE_DEPTH_RANGE:
                                self.get_logger().warn(f"Invalid depth value: {filtered_distance:.2f}m at ({detect_cx}, {detect_cy})")
                                continue
                                
                            self.get_logger().info(f"✅ CONDITION MET! Person detected with missing objects: {missing_classes}")
                            self.get_logger().info(f"center at (u={detect_cx}, v={detect_cy}) → Distance = {filtered_distance:.2f} meters")

                            # depth 이미지에 중심점 표시
                            cv2.circle(depth_colored, (detect_cx, detect_cy), 5, (0, 0, 0), -1)
                            
                            # 레이블 텍스트
                            label = self.class_names[2] if 2 < len(self.class_names) else "person"
                            status_text = f"{label}: {person_conf:.2f}, {filtered_distance:.2f}m [MISSING: {missing_classes}]"
                            cv2.putText(frame, status_text, (person_x1, person_y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                            
                            # 카메라 파라미터
                            fx = self.K[0,0]
                            fy = self.K[1,1]
                            cx = self.K[0,2]
                            cy = self.K[1,2]
                            
                            # 3D 좌표 변환
                            X = (detect_cx - cx) * filtered_distance / fx
                            Y = (detect_cy - cy) * filtered_distance / fy
                            Z = filtered_distance
                            
                            self.get_logger().info(f"3D coordinates: X={X:.3f}, Y={Y:.3f}, Z={Z:.3f}")

                            try:
                                # base_link 기준 포인트 생성
                                point_base = PointStamped()
                                point_base.header.stamp = rclpy.time.Time().to_msg()
                                point_base.header.frame_id = 'oakd_link'
                                point_base.point.x = Z  # 카메라 좌표계에서 Z는 전방 거리
                                point_base.point.y = X  # 카메라 좌표계에서 X는 좌우 (부호 주의)
                                point_base.point.z = -Y  # 카메라 좌표계에서 Y는 상하 (부호 주의)

                                # for end direction
                                point_base_ = PointStamped()
                                point_base_.header.stamp = point_base.header.stamp
                                point_base_.header.frame_id = 'base_link'
                                point_base_.point.x = 0.0
                                point_base_.point.y = 0.0
                                point_base_.point.z = 0.0


                                # base_link → map 변환
                                try:
                                    point_map = self.tf_buffer.transform(
                                        point_base,
                                        'map',
                                        timeout=rclpy.duration.Duration(seconds=0.5)
                                    )
                                    self.get_logger().info(f"[oakd_link] ({point_base.point.x:.2f}, {point_base.point.y:.2f}, {point_base.point.z:.2f})")
                                    self.get_logger().info(f"[Map]       ({point_map.point.x:.2f}, {point_map.point.y:.2f}, {point_map.point.z:.2f})")

                                    point_map_ = self.tf_buffer.transform(
                                        point_base_,
                                        'map',
                                        timeout=rclpy.duration.Duration(seconds=0.5)
                                    )
                                    self.get_logger().info(f"[Map_base]       ({point_map_.point.x:.2f}, {point_map.point.y:.2f}, {point_map.point.z:.2f})")

                                    base_vector = [(point_map.point.x - point_map_.point.x), 
                                                   (point_map.point.y - point_map_.point.y)]
                                    unit_base_vector = [(base_vector[0]/((base_vector[0]**2 + base_vector[1]**2))**(1/2)),
                                                        (base_vector[1]/((base_vector[0]**2 + base_vector[1]**2))**(1/2))]
                                    
                                    angle_radians = math.atan2(unit_base_vector[1], unit_base_vector[0])
                                    # angle_degrees = int(math.degrees(angle_radians))
                                    angle_degrees = math.degrees(angle_radians)
                                    
                                    
                                    # 맵 포인트 데이터 준비
                                    point_map_send_data = PointStamped()
                                    point_map_send_data.header.stamp = rclpy.time.Time().to_msg()
                                    point_map_send_data.header.frame_id = 'map'
                                    point_map_send_data.point.x = point_map.point.x
                                    point_map_send_data.point.y = point_map.point.y
                                    # point_map_send_data.point.z = point_map.point.z
                                    point_map_send_data.point.z = angle_degrees

                                    base_msg = BaseCoordinate()
                                    base_msg.x = point_base.point.x
                                    base_msg.y = point_base.point.y
                                    self.base_coor_pub.publish(base_msg)

                                    # # MQTT 메시지도 조건이 만족될 때만 전송
                                    current_lenght = point_base.point.x + point_base.point.y
                                    if abs(current_lenght - self.last_coord_len) <  LEN_THRESHOLD:
                                        self.publish_mqtt_message(point_map, distance_m)
                                        
                                        self.get_logger().info("📤 Messages published successfully!")
                                    self.last_coord_len = current_lenght
                                except Exception as e:
                                    self.get_logger().warn(f"TF transform to map failed: {e}")

                            except Exception as e:
                                self.get_logger().warn(f"Unexpected error: {e}")
                    else:
                        # 조건이 만족되지 않을 때 (모든 객체가 다 있을 때)
                        label = self.class_names[2] if 2 < len(self.class_names) else "person"
                        status_text = f"{label}: {person_conf:.2f} [ALL OBJECTS PRESENT - NOT PUBLISHING]"
                        cv2.putText(frame, status_text, (person_x1, person_y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    object_count += 1

                # 다른 클래스들도 시각화 (참고용)
                for detection in all_detections:
                    if detection['class'] != 2:  # person이 아닌 객체들
                        cls = detection['class']
                        x1, y1, x2, y2 = detection['bbox']
                        conf = detection['confidence']
                        label = self.class_names[cls] if cls < len(self.class_names) else f"class_{cls}"
                        
                        # 작은 바운딩 박스로 표시 (파란색)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 1)
                        cv2.putText(frame, f"{label}: {conf:.2f}", (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

            cv2.putText(frame, f"Persons: {len(class_2_boxes)}", (10, 30),
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

##############mqtt############################
    def setup_mqtt(self):
        """MQTT 클라이언트 설정"""
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.mqtt_connected = True
                print("✅ Connected to MQTT Broker!")
                self.get_logger().info("MQTT Connected successfully!")
            else:
                self.mqtt_connected = False
                print(f"❌ Failed to connect to MQTT, return code {rc}")
                self.get_logger().error(f"MQTT Connection failed with code {rc}")

        def on_disconnect(client, userdata, rc):
            self.mqtt_connected = False
            print(f"🔌 Disconnected from MQTT Broker with code {rc}")
            self.get_logger().warn(f"MQTT Disconnected with code {rc}")

        def on_publish(client, userdata, mid):
            print(f"📤 Message {mid} published successfully")

        try:
            self.get_logger().info("🔄 Attempting to connect to MQTT broker...")
            self.mqtt_client = mqtt_client.Client(client_id=client_id, protocol=mqtt_client.MQTTv311)
            self.mqtt_client.tls_set()
            self.mqtt_client.username_pw_set(username, password)
            self.mqtt_client.on_connect = on_connect
            self.mqtt_client.on_disconnect = on_disconnect
            self.mqtt_client.on_publish = on_publish
            
            # 비동기 연결 시작
            self.mqtt_client.connect_async(broker, port, keepalive=60)
            self.mqtt_client.loop_start()
            
            # 연결 확인을 위한 짧은 대기
            time.sleep(2)
            
        except Exception as e:
            self.get_logger().error(f"MQTT setup error: {e}")
            self.mqtt_client = None


    def publish_mqtt_message(self, map_point, distance_m):
        """MQTT 메시지 발행"""
        if not self.mqtt_client or not self.mqtt_connected:
            self.get_logger().warn("MQTT not connected. Skipping message.")
            return
            
        try:
            # 현재 시간을 타임스탬프로 사용
            stamp = time.time()
            
            msg = {
                "robot_id": "robot3",
                "type": "human3",
                "location": [round(map_point.point.x, 2), round(map_point.point.y, 2)],
                "depth": round(distance_m, 2),
                "area": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # msg_json = json.dumps(msg, indent=2)
            msg_json = json.dumps(msg)
            
            # 메시지 발행
            result = self.mqtt_client.publish(topic, msg_json)
            
            if result.rc == mqtt_client.MQTT_ERR_SUCCESS:
                print(f"📨 Sent message to topic `{topic}`")
                self.get_logger().info(f"MQTT message sent: {msg}")
            else:
                print(f"❌ Failed to send message to topic {topic}, error: {result.rc}")
                self.get_logger().error(f"MQTT publish failed with code {result.rc}")
                
        except Exception as e:
            self.get_logger().error(f"MQTT publish error: {e}")
##############################################


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
# import rclpy
# from rclpy.node import Node
# from sensor_msgs.msg import Image
# from geometry_msgs.msg import Point, PointStamped
# from cv_bridge import CvBridge
# import numpy as np
# import cv2

# DEPTH_TOPIC = '/robot3/oakd/stereo/image_raw'

# class DepthNode(Node):
#     def __init__(self):
#         super().__init__('depth_node')
#         self.bridge = CvBridge()
#         self.latest_depth = None

#         self.sub_depth = self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)
#         self.sub_center = self.create_subscription(Point, 'person_center', self.center_callback, 10)
#         self.pub_distance = self.create_publisher(PointStamped, 'person_distance', 10)

#     def depth_callback(self, msg):
#         self.latest_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')

#     def center_callback(self, msg):
#         if self.latest_depth is None:
#             return

#         u = int(msg.x)
#         v = int(msg.y)

#         if 0 <= u < self.latest_depth.shape[1] and 0 <= v < self.latest_depth.shape[0]:


#             depth_mm = float(self.latest_depth[v, u])
#             distance_m = depth_mm / 1000.0

#             result = PointStamped()
#             result.header.stamp = self.get_clock().now().to_msg()
#             result.point.x = float(u)
#             result.point.y = float(v)
#             result.point.z = distance_m

#             self.pub_distance.publish(result)
#             self.get_logger().info(f"Distance at ({u}, {v}) = {distance_m:.2f} m")

# def main():
#     rclpy.init()
#     node = DepthNode()
#     rclpy.spin(node)
#     node.destroy_node()
#     rclpy.shutdown()

# if __name__ == '__main__':
#     main()



import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point, PointStamped
from cv_bridge import CvBridge
import numpy as np
import cv2

from std_msgs.msg import Float32

DEPTH_TOPIC = '/robot3/oakd/stereo/image_raw'

class KalmanFilter1D:
    def __init__(self, process_variance=1e-3, measurement_variance=1e-1):
        # 상태 변수
        self.x = 0.0  # 추정된 거리
        self.P = 1.0  # 추정 오차의 공분산
        
        # 노이즈 파라미터
        self.Q = process_variance    # 프로세스 노이즈 (실제 거리 변화)
        self.R = measurement_variance # 측정 노이즈 (센서 노이즈)
        
        self.is_initialized = False
    
    def update(self, measurement):
        if not self.is_initialized:
            # 첫 번째 측정값으로 초기화
            self.x = measurement
            self.is_initialized = True
            return self.x
        
        # 예측 단계 (등속 모델 가정)
        # x_pred = x (거리가 크게 변하지 않는다고 가정)
        # P_pred = P + Q
        P_pred = self.P + self.Q
        
        # 업데이트 단계
        # 칼만 게인 계산
        K = P_pred / (P_pred + self.R)
        
        # 상태 업데이트
        self.x = self.x + K * (measurement - self.x)
        
        # 오차 공분산 업데이트
        self.P = (1 - K) * P_pred
        
        return self.x

class DepthNode(Node):
    def __init__(self):
        super().__init__('depth_node')
        self.bridge = CvBridge()
        self.latest_depth = None
        
        # 칼만 필터 초기화 (각 픽셀별로 필터 필요하지만, 여기서는 하나만 사용)
        self.kalman_filter = KalmanFilter1D(
            process_variance=1e-3,     # 프로세스 노이즈 (작게 설정 - 거리가 급격히 변하지 않음)
            measurement_variance=5e-2  # 측정 노이즈 (뎁스 카메라 노이즈)
        )
        
        self.sub_depth = self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)
        self.sub_center = self.create_subscription(Point, 'person_center', self.center_callback, 10)
        self.pub_distance = self.create_publisher(PointStamped, 'person_distance', 10)

        self.raw_result = self.create_publisher(Float32, 'raw_distance', 10)
        self.kalman_result = self.create_publisher(Float32, 'kalman_distance', 10)

        
        self.get_logger().info("DepthNode initialized with 5x5 average filter and Kalman filter")

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

    def depth_callback(self, msg):
        # 뎁스 이미지 변환
        raw_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        
        # 5x5 평균 필터 적용
        self.latest_depth = self.apply_average_filter(raw_depth, kernel_size=5)

    def center_callback(self, msg):
        if self.latest_depth is None:
            return
        
        u = int(msg.x)
        v = int(msg.y)
        
        if 0 <= u < self.latest_depth.shape[1] and 0 <= v < self.latest_depth.shape[0]:
            # 필터링된 이미지에서 뎁스 값 추출
            depth_mm = float(self.latest_depth[v, u])
            
            if depth_mm <= 0:  # 무효한 뎁스 값은 무시
                self.get_logger().warn(f"Invalid depth value at ({u}, {v})")
                return
            
            distance_m = depth_mm / 1000.0
            
            # 칼만 필터 적용
            filtered_distance = self.kalman_filter.update(distance_m)
            
            # 결과 발행
            result = PointStamped()
            result.header.stamp = self.get_clock().now().to_msg()
            result.point.x = float(u)
            result.point.y = float(v)
            result.point.z = filtered_distance
            
            self.pub_distance.publish(result)
            
            self.get_logger().info(
                f"Raw: {distance_m:.3f}m, Filtered: {filtered_distance:.3f}m at ({u}, {v})"
            )

            kal = Float32()
            kal.data = float(filtered_distance)
            raw = Float32()
            raw.data = float(distance_m)
            self.raw_result.publish(raw)
            self.kalman_result.publish(kal)
            

def main():
    rclpy.init()
    node = DepthNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
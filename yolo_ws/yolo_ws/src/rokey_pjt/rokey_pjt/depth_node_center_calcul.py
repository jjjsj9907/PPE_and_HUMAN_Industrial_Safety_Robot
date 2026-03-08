import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import Point, PointStamped
from cv_bridge import CvBridge
import numpy as np
import cv2

DEPTH_TOPIC = '/robot3/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot3/oakd/stereo/camera_info'
CENTER_TOPIC = 'person_center'
DISTANCE_TOPIC = 'person_distance'
NORMALIZE_DEPTH_RANGE = 3.0  # 최대 3m로 정규화 (시각화용)

class DepthNode(Node):
    def __init__(self):
        super().__init__('depth_node')
        self.bridge = CvBridge()
        self.latest_depth = None
        self.fx = None
        self.fy = None
        self.cx = None
        self.cy = None
        self.last_u = None
        self.last_v = None

        self.sub_depth = self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)
        self.sub_info = self.create_subscription(CameraInfo, CAMERA_INFO_TOPIC, self.camera_info_callback, 10)
        self.sub_center = self.create_subscription(Point, CENTER_TOPIC, self.center_callback, 10)
        self.pub_distance = self.create_publisher(PointStamped, DISTANCE_TOPIC, 10)

    def camera_info_callback(self, msg):
        K = np.array(msg.k).reshape(3, 3)
        self.fx = K[0, 0]
        self.fy = K[1, 1]
        self.cx = K[0, 2]
        self.cy = K[1, 2]
        self.get_logger().info(f"Camera intrinsics received: fx={self.fx:.2f}, fy={self.fy:.2f}, cx={self.cx:.2f}, cy={self.cy:.2f}")

    def calculate_3d_position(self, u, v, z):
        x = (u - self.cx) * z / self.fx
        y = (v - self.cy) * z / self.fy
        return x, y, z

    def depth_callback(self, msg):
        self.latest_depth = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')

        if self.last_u is not None and self.last_v is not None:
            depth_mm = self.latest_depth
            depth_vis = np.nan_to_num(depth_mm, nan=0.0)
            depth_vis = np.clip(depth_vis, 0, NORMALIZE_DEPTH_RANGE * 1000)
            depth_vis = (depth_vis / (NORMALIZE_DEPTH_RANGE * 1000) * 255).astype(np.uint8)
            depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

            cv2.circle(depth_colored, (self.last_u, self.last_v), 5, (0, 0, 255), -1)
            cv2.putText(depth_colored, f"({self.last_u},{self.last_v})", (self.last_u + 10, self.last_v - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("Depth with Center", depth_colored)
            cv2.waitKey(1)

    def center_callback(self, msg):
        if self.latest_depth is None or self.fx is None:
            self.get_logger().warn("Waiting for depth and camera info.")
            return

        u = int(msg.x)
        v = int(msg.y)
        self.last_u = u
        self.last_v = v

        height, width = self.latest_depth.shape[:2]
        if not (0 <= u < width and 0 <= v < height):
            self.get_logger().warn("Center point out of bounds.")
            return

        depth_mm = float(self.latest_depth[v, u])
        if depth_mm == 0 or np.isnan(depth_mm):
            self.get_logger().warn("Invalid depth at center.")
            return

        z = depth_mm / 1000.0  # mm → m
        x, y, z = self.calculate_3d_position(u, v, z)

        point_base = PointStamped()
        point_base.header.stamp = self.get_clock().now().to_msg()
        point_base.header.frame_id = 'base_link'  # 필요 시 base_link로 변경
        point_base.point.x = x
        point_base.point.y = y
        point_base.point.z = z

        self.pub_distance.publish(point_base)
        self.get_logger().info(f"3D Position: ({x:.2f}, {y:.2f}, {z:.2f}) m")

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
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()

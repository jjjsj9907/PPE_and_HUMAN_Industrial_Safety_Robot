import rclpy
import time
from rclpy.node import Node
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Directions, TurtleBot4Navigator
from geometry_msgs.msg import PointStamped, PoseWithCovarianceStamped, PoseStamped
import math
#7.16
from rclpy.qos import QoSDurabilityPolicy
from rclpy.qos import QoSHistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import QoSReliabilityPolicy

qos_profile = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
    durability=QoSDurabilityPolicy.TRANSIENT_LOCAL
)

MAP_TOPIC = 'map_points'

class NavToObj(Node):
    def __init__(self):
        super().__init__('nav_to_obj')

        self.received_goal = False  # 콜백 처리 여부
        self.is_navigating = False

        self.sub_distance = self.create_subscription(
            PointStamped,
            MAP_TOPIC,
            self.map_callback,
            qos_profile
        )
        time.sleep(2)
        self.navigator = TurtleBot4Navigator()
        self.navigator.waitUntilNav2Active()
        self.get_logger().info('Navigator initialized!')

        # 주기적으로 상태 체크 타이머
        self.create_timer(0.5, self.navigation_check)

    def map_callback(self, msg):
        if self.received_goal or self.is_navigating:
            self.get_logger().info("Currently navigating. Ignoring new goal.")
            return

        self.received_goal = True
        self.is_navigating = True

        if abs(msg.point.x) > 10.0 or abs(msg.point.y) > 10.0:
            self.get_logger().warn(f"Goal point too far: ({msg.point.x}, {msg.point.y})")
            self.received_goal = False  # 실패 시 다시 받을 수 있도록
            self.is_navigating = False
            return
        
        self.get_logger().info(f"Received goal: x={msg.point.x:.2f}, y={msg.point.y:.2f}")
        
        goal_pose = self.navigator.getPoseStamped(
            [msg.point.x, msg.point.y],
            TurtleBot4Directions.NORTH
        )
        
        self.navigator.cancelTask()
        self.navigator.startToPose(goal_pose)
        self.navigator.goToPose
        self.get_logger().info("Navigation started!")

    def navigation_check(self):
        """Navigation 상태 주기적으로 확인"""
        if self.is_navigating:
            nav_complete = self.navigator.isTaskComplete()
            if nav_complete:
                self.get_logger().info("Navigation completed!")
                self.is_navigating = False
                self.received_goal = False  # 다음 목표 받을 수 있도록 플래그 초기화



def main():
    rclpy.init()
    node = NavToObj()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

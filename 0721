#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile

# ROS2 메시지 타입들
from std_msgs.msg import String
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import Imu, BatteryState
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist

# MQTT
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
import ssl
import json
import random


class ROS2ToMQTTBridge(Node):
    def __init__(self):
        super().__init__('ros2_mqtt_bridge')

        # MQTT 설정
        self.broker = 'p021f2cb.ala.asia-southeast1.emqxsl.com'
        self.port = 8883
        self.username = 'Rokey'
        self.password = '1234567'
        self.mqtt_topic = "tb4"
        self.client_id = f'ros2-mqtt-{random.randint(0, 1000)}'

        self._setup_mqtt()

        # 구독할 ROS2 토픽과 그 타입을 명시
        self.topic_type_map = {
            #"robot3/odom": Odometry,
            #"robot3/imu": Imu,
            # "robot3/map": OccupancyGrid,
            # "robot3/ip": String,
            # "robot3/battery_state": BatteryState,
            # "robot3/amcl_pose": PoseWithCovarianceStamped,
            # "robot3/cmd_vel": Twist,
            
        }

        qos = QoSProfile(depth=10)

        for topic, msg_type in self.topic_type_map.items():
            self.create_subscription(msg_type, topic, self._callback_factory(topic), qos)
            self.get_logger().info(f"📡 Subscribed to {topic} ({msg_type.__name__})")

    def _setup_mqtt(self):
        self.mqtt_client = mqtt.Client(
            client_id=self.client_id,
            protocol=mqtt.MQTTv311  # ← 여기 핵심
        )
        self.mqtt_client.username_pw_set(self.username, self.password)
        self.mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.mqtt_client.tls_insecure_set(True)

        try:
            self.mqtt_client.connect(self.broker, self.port)
            self.mqtt_client.loop_start()
            self.get_logger().info("✅ MQTT connected successfully")
        except Exception as e:
            self.get_logger().error(f"❌ MQTT connection failed: {e}")
            self.get_logger().error(f"❌ MQTT connection failed: {e}")

    def _callback_factory(self, topic_name):
        def callback(msg):
            try:
                if hasattr(msg, '__slots__'):
                    data_dict = {slot: getattr(msg, slot) for slot in msg.__slots__}
                else:
                    data_dict = {'data': str(msg)}

                payload = {
                    "topic": topic_name,
                    "data": data_dict
                }
                self.mqtt_client.publish(self.mqtt_topic, json.dumps(payload, default=str))
                self.get_logger().info(f"📤 Published to MQTT: {topic_name}")
            except Exception as e:
                self.get_logger().error(f"⚠️ Failed to process message from {topic_name}: {e}")
        return callback


def main(args=None):
    rclpy.init(args=args)
    node = ROS2ToMQTTBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        node.mqtt_client.loop_stop()
        node.mqtt_client.disconnect()


if __name__ == '__main__':
    main()

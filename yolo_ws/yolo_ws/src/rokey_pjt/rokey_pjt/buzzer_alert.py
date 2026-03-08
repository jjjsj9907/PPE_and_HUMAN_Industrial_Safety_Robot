#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from irobot_create_msgs.msg import AudioNoteVector, AudioNote
from builtin_interfaces.msg import Duration

class PPEBuzzerAlert(Node):
    def __init__(self):
        super().__init__('ppe_buzzer_alert', namespace='/robot3')
        
        # 도착 완료 알림 구독 (상대 토픽)
        self.sub_alert = self.create_subscription(
            String,
            'ppe/allive_complete',
            self.on_alert,
            10
        )
        
        # 부저 명령 퍼블리셔 (상대 토픽)
        self.pub_buzzer = self.create_publisher(
            AudioNoteVector,
            'cmd_audio',
            10
        )
        
        # 2초 간격으로 부저 반복
        self.timer = None
        self.get_logger().info('PPE Buzzer Alert Node started, waiting for alerts...')

    def on_alert(self, msg: String):
        self.get_logger().info(f'⚠️ Alert received: "{msg.data}" — playing buzzer pattern')
        
        # 삐뽀삐뽀 패턴: 880Hz→440Hz×반복
        self.play_buzzer_pattern()
        
        # 타이머를 사용하여 2초 간격으로 부저 울리기
        if self.timer is None:
            self.timer = self.create_timer(2.0, self.timer_callback)
        
    def timer_callback(self):
        # 부저 반복 울림
        self.play_buzzer_pattern()

    def play_buzzer_pattern(self):
        notes = AudioNoteVector()
        notes.append = False
        notes.notes = [
            AudioNote(frequency=880, max_runtime=Duration(sec=0, nanosec=300_000_000)),  # 삐
            AudioNote(frequency=440, max_runtime=Duration(sec=0, nanosec=300_000_000)),  # 뽀
            AudioNote(frequency=880, max_runtime=Duration(sec=0, nanosec=300_000_000)),  # 삐
            AudioNote(frequency=440, max_runtime=Duration(sec=0, nanosec=300_000_000)),  # 뽀
        ]
        self.pub_buzzer.publish(notes)
        self.get_logger().info('🔈 Buzzer command published')

def main(args=None):
    rclpy.init(args=args)
    node = PPEBuzzerAlert()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

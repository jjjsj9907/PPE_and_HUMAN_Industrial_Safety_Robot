#!/usr/bin/env python3
import math
import rclpy
import random
import json
import time
import threading
from datetime import datetime, timezone
from rclpy.parameter import Parameter
from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Directions, TurtleBot4Navigator, TaskResult)

from paho.mqtt import client as mqtt_client

from std_msgs.msg import String

#좌표
from geometry_msgs.msg import PointStamped
import tf2_ros
import tf2_geometry_msgs
import rclpy
from rclpy.duration import Duration

# ========== MQTT 설정 ==========
MQTT_CONFIG = {
    'broker': 'p021f2cb.ala.asia-southeast1.emqxsl.com',
    'port': 8883,
    'username': 'Rokey',
    'password': '1234567',
    'topic': "detect",
    'client_id': f'python-mqtt-{random.randint(0, 100)}',
    'keepalive': 60
}

# ========== 로봇 설정 ==========
ROBOT_CONFIG = {
    'namespace': '/robot3',  # 실제 네임스페이스로 수정
    'robot_id': 'robot3',
    'initial_position': [-3.9, 1.5],
    'initial_direction': TurtleBot4Directions.WEST,
    'waypoints': [
        # 웨이포인트 설정
        [([-4.1, 0.94], TurtleBot4Directions.WEST),
        ([-5.32, 0.72], TurtleBot4Directions.SOUTH),
        ([-5.35, -0.74], TurtleBot4Directions.EAST),
        ([-3.6, -0.48], TurtleBot4Directions.NORTH)],
        [
        ([-3.6, -0.48], TurtleBot4Directions.EAST),
        ([-4.1, 0.94], TurtleBot4Directions.SOUTH),
        ([-5.32, 0.72], TurtleBot4Directions.EAST),
        ([-5.35, -0.74], TurtleBot4Directions.NORTH),
        ([-2.0, -0.77], TurtleBot4Directions.SOUTH),
        ([-1.9, -3.0], TurtleBot4Directions.EAST),
        ([-0.5, -2.8], TurtleBot4Directions.NORTH),
        ([-1.9, -3.0], TurtleBot4Directions.SOUTH),
        ([-2.0, -0.77], TurtleBot4Directions.WEST),
        ([-0.80, -0.80], TurtleBot4Directions.NORTH)
        ]
    ],
    'spin_angle': 2 * math.pi,
    'nav_timeout': 30.0,
    'skip_docking': False  # 도킹 기능 활성화
}

way_points_flag = 0
cycle_count = 0
current_waypoint = 0

class NamespacedRobotController:
    """네임스페이스를 지원하는 로봇 네비게이션 컨트롤러"""
    
    def __init__(self):
        self.stop_flag = False
        self.mqtt_client = None
        self.navigator = None
        self.mqtt_connected = False
        self.navigation_active = False
        self._lock = threading.Lock()
        self.namespace = ROBOT_CONFIG['namespace']
        
        # 객체 감지 처리 상태 관리
        self.object_processing = False
        self.object_processing_lock = threading.Lock()
        
        # 객체 위치 저장
        self.target_object_location = None
        self.object_detected = False

        # TF2 초기화는 Navigator 생성 후로 이동
        self.tf_buffer = None
        self.tf_listener = None
        self.tf_initialized = False
        
    def reset_stop_flag(self):
        """정지 플래그를 안전하게 초기화"""
        with self._lock:
            self.stop_flag = False
            print(f"🔄 [{self.namespace}] Stop flag reset: {self.stop_flag}")
    
    def set_stop_flag(self, value=True):
        """정지 플래그를 안전하게 설정"""
        with self._lock:
            self.stop_flag = value
            print(f"🚨 [{self.namespace}] Stop flag set to: {self.stop_flag}")
    
    def is_stopped(self):
        """현재 정지 상태 확인"""
        with self._lock:
            return self.stop_flag
    
    def setup_mqtt(self):
        """MQTT 클라이언트 설정 및 연결"""
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"✅ [{self.namespace}] MQTT 브로커 연결 성공!")
                self.mqtt_connected = True
                
                # retained 메시지 클리어
                client.publish(MQTT_CONFIG['topic'], "", retain=True)
                print(f"🧹 [{self.namespace}] 기존 retained 메시지 클리어 완료")
                
                # 토픽 구독
                client.subscribe(MQTT_CONFIG['topic'])
                print(f"📡 [{self.namespace}] 토픽 구독 완료: {MQTT_CONFIG['topic']}")
                
                # 연결 완료 메시지 발송
                self.publish_event("system_ready", 0, [0, 0], [0, 0])
            else:
                print(f"❌ [{self.namespace}] MQTT 연결 실패, return code: {rc}")
                self.mqtt_connected = False

        def on_disconnect(client, userdata, rc):
            print(f"🔌 [{self.namespace}] MQTT 연결 끊어짐, code: {rc}")
            self.mqtt_connected = False

        # MQTT 클라이언트 초기화
        self.mqtt_client = mqtt_client.Client(
            client_id=f"{MQTT_CONFIG['client_id']}-{ROBOT_CONFIG['robot_id']}", 
            protocol=mqtt_client.MQTTv311
        )
        
        # TLS 및 인증 설정
        self.mqtt_client.tls_set()
        self.mqtt_client.username_pw_set(
            MQTT_CONFIG['username'], 
            MQTT_CONFIG['password']
        )
        
        # 콜백 설정
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_message = self.on_message  # 메서드 바인딩
        self.mqtt_client.on_disconnect = on_disconnect
        
        # 연결 시도
        try:
            print(f"🔄 [{self.namespace}] MQTT 브로커 연결 시도 중...")
            self.mqtt_client.connect(
                MQTT_CONFIG['broker'], 
                MQTT_CONFIG['port'], 
                MQTT_CONFIG['keepalive']
            )
            self.mqtt_client.loop_start()
            
            # 연결 대기 (최대 5초)
            for i in range(50):
                if self.mqtt_connected:
                    break
                time.sleep(0.1)
            
            if not self.mqtt_connected:
                print(f"⚠️ [{self.namespace}] MQTT 연결 시간 초과, 오프라인 모드로 계속")
                
        except Exception as e:
            print(f"❌ [{self.namespace}] MQTT 연결 오류: {e}")
            print(f"⚠️ [{self.namespace}] MQTT 없이 계속 진행")

    def on_message(self, client, userdata, msg):
        
        global way_points_flag
        global cycle_count
        global current_waypoint

        try:
            payload = msg.payload.decode().strip()
            print(f"📩 [{self.namespace}] MQTT 메시지 수신: '{payload}' from '{msg.topic}'")
            
            # 빈 메시지는 무시
            if not payload:
                print(f"📝 [{self.namespace}] 빈 메시지 무시 (retained 클리어)")
                return
            
            # JSON 파싱
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                print(f"❌ [{self.namespace}] JSON 파싱 실패: {payload}")
                return
            
            # 무시 처리
            if data.get('type') not in ["human3", "crack1"]:
                print(f"📝 관심없는 메시지 타입 무시: {data.get('type')}")
                return
            
            # 수동 정지/재시작 명령 처리
            if data.get('command') == "stop":
                print(f"🛑 [{self.namespace}] 수동 정지 명령 수신됨!")
                self.set_stop_flag(True)
                return
            elif data.get('type') == "human3" and data.get('command') == "start":
                print(f"▶️ [{self.namespace}] 수동 재시작 명령 수신됨!")
                self.reset_stop_flag()
                return
            
            elif data.get('type') == "crack1" and data.get('command') == "start":
                print(f"▶️ [{self.namespace}] 수동 재시작 명령 수신됨!")
                self.navigator.cancelTask()
                self.object_processing = False
                way_points_flag = 0
                cycle_count = 0
                current_waypoint = 0
                self.reset_stop_flag()
                return
            
            # 객체 감지 처리 (패트롤 루프에서 처리하도록 플래그만 설정)
            if data.get('type') == 'human3':
                with self.object_processing_lock:
                    if self.object_processing:
                        print(f"⚠️ [{self.namespace}] 객체 처리 중 - 새로운 객체 감지 무시")
                        return
                    
                    position = data.get('location')
                    if position:
                        print(f"🚶 Human detected at: {position}")
                        self.target_object_location = position
                        self.object_detected = True
                        self.object_processing = True
                        
                        # 현재 네비게이션 작업 취소
                        self.navigator.cancelTask()
            if data.get('type') == 'crack1':
                with self.object_processing_lock:
                    if self.object_processing:
                        print(f"⚠️ [{self.namespace}] 객체 처리 중 - 새로운 객체 감지 무시")
                        return
                    
                    self.object_processing = True
                        
                        # 현재 네비게이션 작업 취소
                    self.navigator.cancelTask()
                    way_points_flag = 1
                    cycle_count = 0
                    current_waypoint = 0
                    self.reset_stop_flag()

            
                        
        except Exception as e:
            print(f"❌ [{self.namespace}] MQTT 메시지 처리 오류: {e}")
    
    def publish_event(self, event_type, waypoint_index, robot_pos, target_pos):
        """MQTT 이벤트 발행"""
        if not self.mqtt_connected or not self.mqtt_client:
            print(f"📤 [{self.namespace}] MQTT 미연결 - 이벤트 스킵: {event_type}")
            return
        
        try:
            msg = {
                "robot_id": ROBOT_CONFIG['robot_id'],
                "namespace": self.namespace,
                "event": event_type,
                "waypoint": waypoint_index,
                "robot_position": robot_pos,
                "event_position": target_pos,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.mqtt_client.publish(MQTT_CONFIG['topic'], json.dumps(msg))
            if result.rc == mqtt_client.MQTT_ERR_SUCCESS:
                print(f"📤 [{self.namespace}] MQTT 이벤트 발행 성공: {event_type}")
            else:
                print(f"📤 [{self.namespace}] MQTT 이벤트 발행 실패: {event_type}, rc={result.rc}")
                
        except Exception as e:
            print(f"❌ [{self.namespace}] MQTT 발행 오류: {e}")
    
    def check_docking_support(self):
        """도킹 기능 지원 여부 확인"""
        try:
            status = self.navigator.getDockedStatus()
            print(f"✅ [{self.namespace}] 도킹 기능 지원됨")
            return True
        except Exception as e:
            print(f"⚠️ [{self.namespace}] 도킹 기능 지원되지 않음: {e}")
            return False
    
    def setup_navigation(self):
        """네비게이션 시스템 초기화"""
        print(f"🤖 [{self.namespace}] ROS2 노드 초기화 중...")
        
        # ROS2 초기화
        rclpy.init()

        # TurtleBot4Navigator 초기화 먼저
        self.navigator = TurtleBot4Navigator(namespace='robot3')
        print(f"🗺️ [{self.namespace}] TurtleBot4 Navigator 초기화 완료")
        
        # Navigator 생성 후 TF2 초기화
        try:
            self.tf_buffer = tf2_ros.Buffer()
            self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self.navigator)
            time.sleep(1.0)  # TF 트리 안정화 대기
            self.tf_initialized = True
            print(f"✅ TF2 초기화 완료")
        except Exception as e:
            print(f"⚠️ TF2 초기화 실패: {e}")
            self.tf_initialized = False

        # 도킹 기능 확인 및 처리
        if not ROBOT_CONFIG['skip_docking']:
            docking_supported = self.check_docking_support()
            if docking_supported:
                if not self.ensure_docking():
                    print(f"⚠️ [{self.namespace}] 도킹 실패하지만 계속 진행")
        else:
            print(f"⏭️ [{self.namespace}] 도킹 기능 스킵됨")
        
        # 초기 포즈 설정
        print(f"📍 [{self.namespace}] 초기 포즈 설정 중...")
        initial_pose = self.navigator.getPoseStamped(
            ROBOT_CONFIG['initial_position'], 
            ROBOT_CONFIG['initial_direction']
        )
        self.navigator.setInitialPose(initial_pose)
        
        # Nav2 활성화 대기
        print(f"🗺️ [{self.namespace}] Nav2 시스템 활성화 대기 중...")
        self.navigator.waitUntilNav2Active()
        
        # 초기화 완료 대기
        print(f"⏱️ [{self.namespace}] 시스템 안정화 대기...")
        time.sleep(3.0)
        
        self.navigation_active = True
        print(f"✅ [{self.namespace}] 네비게이션 시스템 준비 완료!")

        self.buffer = self.navigator.create_publisher(String, 'ppe/allive_complete', 10)
        return True
    
    def ensure_docking(self):
        """도킹 상태 확인 및 보장"""
        print(f"🔌 [{self.namespace}] 도킹 상태 확인 중...")
        
        try:
            if self.navigator.getDockedStatus():
                print(f"✅ [{self.namespace}] 로봇이 이미 도킹됨")
                return True
            
            print(f"🔌 [{self.namespace}] 로봇이 도킹되지 않음 - 도킹 시도")
            self.navigator.dock()
            
            # 도킹 완료 대기
            timeout_counter = 0
            while not self.navigator.getDockedStatus() and timeout_counter < 30:
                time.sleep(1)
                timeout_counter += 1
                if self.is_stopped():
                    print(f"🚫 [{self.namespace}] 도킹 중 정지 명령 수신")
                    return False
            
            if self.navigator.getDockedStatus():
                print(f"✅ [{self.namespace}] 도킹 완료!")
                return True
            else:
                print(f"⚠️ [{self.namespace}] 도킹 실패")
                return False
                
        except Exception as e:
            print(f"⚠️ [{self.namespace}] 도킹 상태 확인 오류: {e}")
            return False
    
    def ensure_undocking(self):
        """언도킹 확인 및 보장"""
        if ROBOT_CONFIG['skip_docking']:
            print(f"⏭️ [{self.namespace}] 언도킹 스킵됨")
            return True
            
        print(f"🚀 [{self.namespace}] 언도킹 상태 확인 중...")
        
        try:
            if self.navigator.getDockedStatus():
                print(f"🚀 [{self.namespace}] 도킹 상태에서 언도킹 시작...")
                self.navigator.undock()
                
                # 언도킹 완료 대기
                timeout_counter = 0
                while self.navigator.getDockedStatus() and timeout_counter < 20:
                    time.sleep(1)
                    timeout_counter += 1
                    if self.is_stopped():
                        print(f"🚫 [{self.namespace}] 언도킹 중 정지 명령 수신")
                        return False
                
                if not self.navigator.getDockedStatus():
                    print(f"✅ [{self.namespace}] 언도킹 완료!")
                else:
                    print(f"⚠️ [{self.namespace}] 언도킹 실패")
            else:
                print(f"✅ [{self.namespace}] 로봇이 이미 언도킹됨")
            
            # 언도킹 후 안정화 대기
            print(f"⏱️ [{self.namespace}] 언도킹 후 시스템 안정화 대기...")
            time.sleep(2.0)
            return True
            
        except Exception as e:
            print(f"⚠️ [{self.namespace}] 언도킹 오류: {e}")
            return False

    def wait_for_task_completion(self, task_description="", timeout=None):
        """작업 완료 대기 - 정지 시 즉시 취소"""
        if timeout is None:
            timeout = ROBOT_CONFIG['nav_timeout']
        
        start_time = time.time()
        
        while not self.navigator.isTaskComplete():
            # 정지 명령 확인
            if self.is_stopped():
                print(f"🚨 [{self.namespace}] 정지 명령으로 인한 작업 취소: {task_description}")
                self.navigator.cancelTask()
                return False
            
            # ROS2 스핀
            rclpy.spin_once(self.navigator, timeout_sec=0.1)
        
        # 결과 확인
        result = self.navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            print(f"✅ [{self.namespace}] 작업 성공: {task_description}")
            return True
        else:
            print(f"❌ [{self.namespace}] 작업 실패: {task_description}")
            return False

    def wait_for_object_navigation(self, task_description="", timeout=30.0):
        """객체 감지 시 네비게이션 대기"""
        start_time = time.time()
        
        while not self.navigator.isTaskComplete():
            # 타임아웃 확인
            if time.time() - start_time > timeout:
                print(f"⏰ [{self.namespace}] 객체 이동 타임아웃: {task_description}")
                self.navigator.cancelTask()
                return False
            
            # ROS2 스핀
            rclpy.spin_once(self.navigator, timeout_sec=0.1)
        
        # 결과 확인
        result = self.navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            print(f"✅ [{self.namespace}] 객체 이동 성공: {task_description}")
            return True
        else:
            print(f"❌ [{self.namespace}] 객체 이동 실패: {task_description}")
            return False
    
    def get_current_position(self):
        """현재 로봇 위치 반환"""
        try:
            # 임시로 기본값 반환 (getCurrentPose 메서드 오류 때문에)
            return [0.0, 0.0]
        except Exception as e:
            print(f"⚠️ [{self.namespace}] 현재 위치 획득 실패: {e}")
            return [0.0, 0.0]
    
    def navigate_to_waypoint(self, waypoint_index, position, direction):
        """특정 웨이포인트로 이동"""
        print(f"🎯 [{self.namespace}] [{waypoint_index}/{len(ROBOT_CONFIG['waypoints'][way_points_flag])}] 웨이포인트 이동: {position}")
        
        # 목표 포즈 생성
        goal_pose = self.navigator.getPoseStamped(position, direction)
        
        # 이동 시작
        self.navigator.goToPose(goal_pose)
        
        # 이동 완료 대기
        success = self.wait_for_task_completion(f"웨이포인트 {waypoint_index} 이동")
        
        if success:
            robot_pos = self.get_current_position()
            self.publish_event("waypoint_arrival", waypoint_index, robot_pos, position)
            print(f"✅ [{self.namespace}] 웨이포인트 {waypoint_index} 도착!")
        
        return success

    def navigate_to_object(self, position):
        """객체 좌표로 이동"""
        try:
            print(f"🎯 [{self.namespace}] 객체 위치로 이동: {position}")
            
            # 목표 포즈 생성
            goal_pose = self.navigator.getPoseStamped(position, TurtleBot4Directions.EAST)
            
            # 이동 시작
            self.navigator.goToPose(goal_pose)
            
            # 이동 완료 대기
            success = self.wait_for_object_navigation("객체 위치 이동")
            
            if success:
                robot_pos = self.get_current_position()
                self.publish_event("object_reached", 99, robot_pos, position)
                print(f"✅ [{self.namespace}] 객체 위치 도착!")
            
            return success
            
        except Exception as e:
            print(f"❌ [{self.namespace}] 객체 이동 중 오류: {e}")
            return False
    
    def perform_rotation(self, waypoint_index):
        """360도 회전 수행"""
        print(f"🔄 [{self.namespace}] 웨이포인트 {waypoint_index}에서 360° 회전 시작")
        
        # 회전 시작
        self.navigator.spin(spin_dist=ROBOT_CONFIG['spin_angle'])
        
        # 회전 완료 대기
        success = self.wait_for_task_completion(f"웨이포인트 {waypoint_index} 회전", timeout=15.0)
        
        if success:
            robot_pos = self.get_current_position()
            self.publish_event("rotation_complete", waypoint_index, robot_pos, robot_pos)
            print(f"✅ [{self.namespace}] 웨이포인트 {waypoint_index} 회전 완료!")
        
        return success
    
    def run_patrol_cycle(self):
        global way_points_flag
        global cycle_count
        global current_waypoint

        """패트롤 사이클 실행 - 객체 감지 처리 통합"""
        if not self.navigation_active:
            print(f"❌ 네비게이션이 활성화되지 않음")
            return False
        
        # 패트롤 시작 전 언도킹 확인
        if not self.ensure_undocking():
            print(f"❌ 언도킹 실패로 패트롤 중단")
            return False
        

        
        while rclpy.ok():
            try:
                # 객체 감지 처리 우선
                if self.object_detected and self.target_object_location:
                    try:
                        print(f"🎯 객체 감지 - 패트롤 중단하고 객체 위치로 이동")
                        
                        # 객체 위치로 이동
                        if self.navigate_to_object(self.target_object_location):
                            print(f"✅ 객체 위치 도착 - 정지 상태로 전환")
                            self.set_stop_flag(True)
                            msg = String()
                            msg.data = 'object_reached'
                            self.buzzer.publish(msg)
                            print(f"msg pulish - {msg.data}")
                            
                        else:
                            print(f"❌ 객체 위치 이동 실패")
                        
                        # 객체 처리 완료
                        with self.object_processing_lock:
                            self.object_detected = False
                            self.target_object_location = None
                            self.object_processing = False
                            
                    except Exception as e:
                        print(f"❌ 객체 처리 중 오류: {e}")
                        with self.object_processing_lock:
                            self.object_detected = False
                            self.target_object_location = None
                            self.object_processing = False
                
                # 정지 상태일 때 대기
                if self.is_stopped():
                    print(f"⏸️  [{self.namespace}] 정지 상태 - 대기 중...")
                    while self.is_stopped() and rclpy.ok():
                        # 대기 중에도 객체 감지 메시지 처리
                        rclpy.spin_once(self.navigator, timeout_sec=0.1)
                        time.sleep(0.1)
                    
                    if not rclpy.ok():
                        break
                        
                    print(f"▶️  [{self.namespace}] 정지 해제 - 패트롤 재개")
                    # 패트롤 재개 시 언도킹 다시 확인
                    if not self.ensure_undocking():
                        print(f"❌ 언도킹 실패로 패트롤 재시작 불가")
                        time.sleep(5)
                        continue
                
                # 정상 패트롤 진행
                if current_waypoint == 0:
                    cycle_count += 1
                    print(f"\n🔄 [{self.namespace}] === 패트롤 사이클 {cycle_count} 시작 ===")
                
                # 현재 웨이포인트 처리
                if current_waypoint < len(ROBOT_CONFIG['waypoints'][way_points_flag]):
                    position, direction = ROBOT_CONFIG['waypoints'][way_points_flag][current_waypoint]
                    waypoint_num = current_waypoint + 1
                    
                    # 웨이포인트로 이동
                    if self.navigate_to_waypoint(waypoint_num, position, direction):
                        # 360도 회전
                        if self.perform_rotation(waypoint_num):
                            current_waypoint += 1
                        else:
                            print(f"❌ 웨이포인트 {waypoint_num} 회전 실패")
                            current_waypoint += 1  # 실패해도 다음으로
                    else:
                        print(f"❌ 웨이포인트 {waypoint_num} 이동 실패")
                        current_waypoint += 1  # 실패해도 다음으로
                
                else:
                    # 모든 웨이포인트 완료
                    robot_pos = self.get_current_position()
                    self.publish_event("route_complete", cycle_count, robot_pos, robot_pos)
                    print(f"✅ 패트롤 사이클 {cycle_count} 완료!\n")
                    
                    current_waypoint = 0  # 다음 사이클 시작
                    time.sleep(1.0)
                
                # 짧은 대기 (MQTT 메시지 처리를 위해)
                rclpy.spin_once(self.navigator, timeout_sec=0.1)
                time.sleep(0.1)
                    
            except KeyboardInterrupt:
                print(f"\n🛑 사용자 중단 요청")
                break
            except Exception as e:
                print(f"\n⚠️ [{self.namespace}] 패트롤 중 오류 발생: {e}")
                print(f"🔄 [{self.namespace}] 5초 후 패트롤 재시작...")
                time.sleep(5)
                continue
        
        print(f"\n🏁 [{self.namespace}] 패트롤 루프 종료")
        return True
    
    def cleanup(self):
        """리소스 정리"""
        print(f"🧹 시스템 정리 중...")
        
        if self.mqtt_client:
            try:
                self.publish_event("system_shutdown", 0, [0, 0], [0, 0])
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
                print(f"✅ MQTT 연결 종료")
            except Exception as e:
                print(f"⚠️ MQTT 정리 오류: {e}")
        
        if self.navigator and rclpy.ok():
            try:
                self.navigator.cancelTask()
                print(f"✅ 네비게이션 작업 취소")
            except Exception as e:
                print(f"⚠️ 네비게이션 정리 오류: {e}")
        
        print(f"🏁 시스템 정리 완료")

def main():
    """메인 함수 - 예외 발생 시에도 프로그램 유지"""
    controller = NamespacedRobotController()
    
    try:
        print(f"🚀 === TurtleBot4 패트롤 시스템 시작 [{ROBOT_CONFIG['namespace']}] ===\n")
        
        # 1. MQTT 설정
        controller.setup_mqtt()
        time.sleep(1.0)  # MQTT 안정화 대기
        
        # 2. 네비게이션 설정
        if not controller.setup_navigation():
            print(f"❌ [{ROBOT_CONFIG['namespace']}] 네비게이션 초기화 실패")
            return
        
        # 3. 패트롤 실행 (예외 발생해도 계속)
        print(f"🎯 [{ROBOT_CONFIG['namespace']}] 패트롤 시작!")
        
        # 무한 루프로 패트롤 실행 - 예외 발생해도 재시작
        while True:
            try:
                controller.run_patrol_cycle()
                # 정상적으로 종료된 경우 (KeyboardInterrupt)
                break
            except KeyboardInterrupt:
                print(f"\n🛑 사용자 중단 요청")
                break
            except Exception as e:
                print(f"\n⚠️ [{ROBOT_CONFIG['namespace']}] 시스템 오류: {e}")
                print(f"🔄 [{ROBOT_CONFIG['namespace']}] 10초 후 시스템 재시작...")
                time.sleep(10)
                continue  # 다시 패트롤 시작
        
        # 여기에 도달하면 정상적인 종료 (KeyboardInterrupt)
        print(f"🏁 [{ROBOT_CONFIG['namespace']}] 패트롤 정상 종료")
        
    except KeyboardInterrupt:
        print(f"\n🛑 [{ROBOT_CONFIG['namespace']}] 사용자 중단 요청")
    except Exception as e:
        print(f"❌ [{ROBOT_CONFIG['namespace']}] 초기화 오류: {e}")
    finally:
        # KeyboardInterrupt 또는 초기화 실패 시에만 cleanup 실행
        controller.cleanup()
        print(f"👋 [{ROBOT_CONFIG['namespace']}] 프로그램 종료")

if __name__ == '__main__':
    main()
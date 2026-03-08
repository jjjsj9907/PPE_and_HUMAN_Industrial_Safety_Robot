#!/usr/bin/env python3
import math
import rclpy
import random
from rclpy.parameter import Parameter
from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Directions, TurtleBot4Navigator, TaskResult)

from paho.mqtt import client as mqtt_client

# ========== MQTT 설정 ==========
broker = 'g11c1e1e.ala.eu-central-1.emqxsl.com'
port = 8883
username = 'okj1812'
password = 'okj1812'
topic = "python/mqtt"
client_id = f'python-mqtt-{random.randint(0, 100)}'

# ========== 로봇 초기 설정 ==========
INITIAL_POSE_POSITION  = [-0.77, -0.77]
INITIAL_POSE_DIRECTION = TurtleBot4Directions.NORTH
GOAL_POSES = [
    ([-0.80, -0.80], TurtleBot4Directions.NORTH),
    ([-1.73, -2.57], TurtleBot4Directions.SOUTH),
]

# ========== 전역 MQTT 상태 변수 ==========
stop_flag = False  # 메시지 "1" 수신 시 True로 변경


# ========== MQTT 연결 및 콜백 ==========
def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Connected to MQTT Broker!")
            client.subscribe(topic)
        else:
            print(f"❌ Failed to connect, return code {rc}")

    client = mqtt_client.Client(client_id=client_id, protocol=mqtt_client.MQTTv311)
    client.tls_set()
    client.username_pw_set(username, password)
    client.on_connect = on_connect

    def on_message(client, userdata, msg):
        global stop_flag
        payload = msg.payload.decode()
        print(f"📩 Received `{payload}` from `{msg.topic}`")
        if payload.strip() == "1":
            print("🛑 Stop command received!")
            stop_flag = True

    client.on_message = on_message
    client.connect(broker, port)
    client.loop_start()
    return client


# ========== 내비게이션 완료 대기 ==========
def wait_until_done(navigator, text=''):
    while not navigator.isTaskComplete():
        rclpy.spin_once(navigator, timeout_sec=0.2)
        if stop_flag:
            navigator.get_logger().info("🚨 정지 명령 수신됨. 현재 작업 취소 중...")
            navigator.cancelTask()
            return False
    result = navigator.getResult()
    if result != TaskResult.SUCCEEDED:
        navigator.error(f'{text} 실패, status={result}')
        return False
    return True


# ========== 메인 루프 ==========
def main():
    global stop_flag
    rclpy.init()
    navigator = TurtleBot4Navigator()

    # MQTT 연결
    connect_mqtt()

    if not navigator.getDockedStatus():
        navigator.info('Docking before initializing pose')
        navigator.dock()

    initial_pose = navigator.getPoseStamped(INITIAL_POSE_POSITION, INITIAL_POSE_DIRECTION)
    navigator.setInitialPose(initial_pose)
    navigator.waitUntilNav2Active()
    navigator.undock()

    try:
        while rclpy.ok():
            navigator.info('--- 경로 순회 시작 ---')
            for i, (pos, direction) in enumerate(GOAL_POSES, start=1):
                if stop_flag:
                    navigator.info("🚫 정지 상태 — 순회 중단")
                    return

                navigator.info(f'[{i}/{len(GOAL_POSES)}] 이동 시작 → {pos}')
                goal = navigator.getPoseStamped(pos, direction)
                navigator.goToPose(goal)

                if not wait_until_done(navigator, text=f'웨이포인트 {i} 이동'):
                    return

                if stop_flag:
                    navigator.info("🚫 정지 상태 — 회전 생략")
                    return

                navigator.info(f'웨이포인트 {i} 도착. 360° 회전 수행')
                navigator.spin(spin_dist=2 * math.pi)

                if not wait_until_done(navigator, text=f'웨이포인트 {i} 회전'):
                    return

            navigator.info('--- 경로 순회 완료. 다시 반복합니다 ---\n')

    except KeyboardInterrupt:
        navigator.info('사용자 중단으로 종료')

    finally:
        navigator.info('로봇 도킹 시도 중...')
        navigator.dock()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


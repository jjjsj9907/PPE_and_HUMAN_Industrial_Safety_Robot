#!/usr/bin/env python3
import math
import rclpy
from rclpy.parameter import Parameter
from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Directions, TurtleBot4Navigator, TaskResult)

# ======================
# 초기 설정
# ======================
INITIAL_POSE_POSITION  = [-0.77, -0.77]
INITIAL_POSE_DIRECTION = TurtleBot4Directions.NORTH

GOAL_POSES = [
    ([-0.80, -0.80], TurtleBot4Directions.NORTH),   # waypoint 1
    ([-1.73, -2.57], TurtleBot4Directions.SOUTH),   # waypoint 2
]

# waypoint 별 속도 설정 (index 기준)
# (linear_speed [m/s], angular_speed [rad/s])
WAYPOINT_SPEEDS = {
    1: (0.20, 0.4),  # initial → waypoint 1
    2: (0.10, 0.2),  # waypoint 1 → waypoint 2
}

def wait_until_done(navigator, text=''):
    """navigator.isTaskComplete() 가 True 될 때까지 대기"""
    while not navigator.isTaskComplete():
        rclpy.spin_once(navigator, timeout_sec=0.2)
    result = navigator.getResult()
    if result != TaskResult.SUCCEEDED:
        navigator.error(f'{text} 실패, status={result}')
        return False
    return True

def set_nav_speed(navigator, linear_speed=0.2, angular_speed=0.5):
    """Nav2 컨트롤러의 속도 파라미터 설정"""
    navigator.info(f"💡 속도 설정 → 선속도: {linear_speed} m/s, 각속도: {angular_speed} rad/s")
    try:
        navigator.lifecycle_node.set_parameters([
            Parameter('max_vel_x', Parameter.Type.DOUBLE, linear_speed),
            Parameter('max_vel_theta', Parameter.Type.DOUBLE, angular_speed),
        ])
    except Exception as e:
        navigator.error(f"속도 설정 실패: {e}")

def main():
    rclpy.init()
    navigator = TurtleBot4Navigator()

    # 초기 도킹 여부 확인
    if not navigator.getDockedStatus():
        navigator.info('Docking before initializing pose')
        navigator.dock()

    # 초기 위치 설정
    initial_pose = navigator.getPoseStamped(INITIAL_POSE_POSITION, INITIAL_POSE_DIRECTION)
    navigator.setInitialPose(initial_pose)
    navigator.waitUntilNav2Active()
    navigator.undock()

    # 경유점 반복 루프
    try:
        while rclpy.ok():
            navigator.info('--- 경로 순회 시작 ---')
            for i, (pos, direction) in enumerate(GOAL_POSES, start=1):
                navigator.info(f'[{i}/{len(GOAL_POSES)}] 이동 시작 → {pos}')

                # ✅ 이동 전 해당 waypoint 진입 속도 설정
                if i in WAYPOINT_SPEEDS:
                    linear, angular = WAYPOINT_SPEEDS[i]
                    set_nav_speed(navigator, linear_speed=linear, angular_speed=angular)

                goal = navigator.getPoseStamped(pos, direction)
                navigator.goToPose(goal)

                if not wait_until_done(navigator, text=f'웨이포인트 {i} 이동'):
                    return

                # 도착 후 회전
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


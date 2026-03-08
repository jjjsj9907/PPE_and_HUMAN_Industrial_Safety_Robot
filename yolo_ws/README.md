# ROKEY_D_1: 새로 시작합니다

1. 진행 완료 사항
   
    -YOLO + Depth 기반 객체 위치 인식
   
        RGB-D 데이터를 활용하여 객체 중심의 base_link 기준 3D 위치 추정
   
    -TF를 통한 좌표계 변환
   
        추정된 객체 위치를 base_link → map 프레임으로 변환
        tf2_ros 기반 좌표 변환
   
    -자율 주행 및 정지
   
        변환된 map 좌표를 목표지점으로 설정 후 로봇 자율 이동
        도착 후 정지 동작 정상 수행
        
3. 카메라 파라미터 오류 수정
   
    -초기 Depth to 3D 좌표 변환 시 오차 발생
   
    -내부 파라미터 계산 과정 수정을 통해 정확도 복구
   
    -좌표계 불일치 문제 해결됨

5. 향후 개발 예정 사항
   
    -YOLO의 바운딩 박스 클래스 결과를 분석, 안전모, 조끼, 안전화 모두 미착용한 객체 식별 시
         → buzzer 노드로 경고 메시지 Publish

    -회전/주행 중 포커스 손실 대응
   
        카메라의 자동 초점 유지 실패 문제 확인됨
   
        주행 중 실시간 초점 재설정 또는 이미지 안정화 기법 적용 예정


ros2 run rokey_pjt detect_with_depth_with_tf --ros-args -r /tf:=/robot1/tf -r /tf_static:=/robot1/tf_static -r __ns:=/robot1



 --ros-args -r /tf:=/robot3/tf -r /tf_static:=/robot3/tf_static -r __ns:=/robot3


# your_ros_pkg/msg/CPDetection.msg
float64 x_m        # 전방 거리 (m)
float64 y_m        # 좌우 거리 (m)
float64 area_cm2   # 검출 영역 면적 (cm²)
builtin_interfaces/Time stamp  # 검출 시간
string class_name            # 검출된 클래스 라벨

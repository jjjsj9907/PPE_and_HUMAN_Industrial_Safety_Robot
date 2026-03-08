# RoleAssignment.msg
# ──────────────────────────────────────────────────────────────────────────────
# 로봇 간 역할 분배 및 미션 정보
# ──────────────────────────────────────────────────────────────────────────────

std_msgs/Header header

# 감지자(Detector) 로봇 ID
string detector_id

# 대응자(Responder) 로봇 ID
string responder_id

# 미션 타입 (예: "escort", "inspect", "alert")
string mission_type

# 목표 2D 좌표 (map 프레임 내 위치)
geometry_msgs/Point target_position

# 관련 위반 데이터 (PPEViolation 메시지를 중첩)
rokey_msgs/PPEViolation violation   # 패키지명 rokey_msgs 로 가정

# 긴급 여부
bool is_emergency

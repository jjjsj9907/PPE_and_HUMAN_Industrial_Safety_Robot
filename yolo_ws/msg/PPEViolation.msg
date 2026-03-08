# PPEViolation.msg
# ──────────────────────────────────────────────────────────────────────────────
# PPE 위반 정보
# ──────────────────────────────────────────────────────────────────────────────

std_msgs/Header header

# 위반 고유 ID
string violation_id

# 연관된 사람 ID (PersonDetection.person_id)
string person_id

# 2D 위치 (픽셀 또는 m 단위)
geometry_msgs/Point position

# 미착용 PPE 항목 리스트 (예: ["helmet", "vest"])
string[] missing_items

# 위반 신뢰도 (0.0 ~ 1.0)
float32 confidence

# 구역 식별 (예: "ZoneA", "Gate3")
string zone

# 심각도: 0=Low, 1=Medium, 2=High
uint8 severity_level

# 탐지 로봇 ID
string robot_id

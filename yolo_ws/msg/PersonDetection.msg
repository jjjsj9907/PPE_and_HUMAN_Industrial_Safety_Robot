# PersonDetection.msg
# ──────────────────────────────────────────────────────────────────────────────
# 사람 탐지 정보
# ──────────────────────────────────────────────────────────────────────────────

# Timestamp + frame_id
std_msgs/Header header

# 고유 식별자 (예: UUID)
string person_id

# 바운딩 박스 (픽셀 단위)
uint32 x_min
uint32 y_min
uint32 x_max
uint32 y_max

# 2D 이미지 좌표 (픽셀 또는 m단위)
geometry_msgs/Point centroid   # z 필드는 0으로 사용

# 탐지 신뢰도 (0.0 ~ 1.0)
float32 confidence

# 탐지 로봇 ID (네임스페이스나 로봇명)
string robot_id

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import random
from datetime import datetime, timezone

app = FastAPI()

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 시뮬레이션할 ROS2 토픽 리스트
SIMULATED_TOPICS = [
    "/robot1/odom", "/robot1/scan", "/robot1/battery_state",
    "/robot1/cmd_vel", "/robot1/imu", "/robot1/joint_states",
    "/robot1/oakd/rgb/image_raw", "/robot1/oakd/stereo/image_raw"
]

# 메시지 모델
class SimulatedMessage(BaseModel):
    timestamp: str
    topic: str
    msg_type: str
    data: dict

@app.get("/api/messages", response_model=List[SimulatedMessage])
def get_simulated_messages():
    now = datetime.now(timezone.utc).isoformat()
    messages = []
    for topic in SIMULATED_TOPICS:
        msg = SimulatedMessage(
            timestamp=now,
            topic=topic,
            msg_type="std_msgs/String",
            data={"value": random.uniform(0, 1)}
        )
        messages.append(msg)
    return messages

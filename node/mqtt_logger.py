#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import json
from datetime import datetime
import paho.mqtt.client as mqtt
from pathlib import Path

# ------------------------
# 사용자 설정
# ------------------------
LOG_DIR = '/home/okj1812/logs'
BROKER = 'p021f2cb.ala.asia-southeast1.emqxsl.com'
PORT = 8883
USERNAME = 'Rokey'
PASSWORD = '1234567'
# 하드코딩 토픽 목록
TOPICS = [
    'python/mqtt',
    'crack',
    'robot1/ppe_violation',
    'robot3/crack',
    'robot3/puddle'
]

# 로그 디렉터리 생성
log_dir = Path(LOG_DIR)
log_dir.mkdir(parents=True, exist_ok=True)

# ------------------------
# MQTT 콜백 정의
# ------------------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info(f"✅ Connected to {BROKER}:{PORT}")
        for topic in TOPICS:
            client.subscribe(topic)
            logging.info(f"🔖 Subscribed to {topic}")
    else:
        logging.error(f"❌ Connection failed, rc={rc}")


def on_message(client, userdata, msg):
    raw = msg.payload.decode('utf-8', errors='ignore')
    timestamp = datetime.utcnow().isoformat()
    # JSON 형태 파싱 시도
    try:
        data = json.loads(raw)
        payload = json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        payload = raw  # JSON이 아니면 원본 그대로

    # 토픽 이름을 파일명으로 변환
    safe_topic = msg.topic.replace('/', '_').strip('_')
    file_path = log_dir / f"{safe_topic}.log"

    # 로그 파일에 기록
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(f"{timestamp} | {payload}\n")

    logging.info(f"📝 Logged on {safe_topic}: {payload}")

# ------------------------
# 메인 함수
# ------------------------
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    client = mqtt.Client(client_id=f"logger-{datetime.utcnow().timestamp()}")
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set()  # 시스템 루트 CA 사용
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT)
    except Exception as e:
        logging.error(f"Connection error: {e}")
        return

    client.loop_forever()


if __name__ == '__main__':
    main()

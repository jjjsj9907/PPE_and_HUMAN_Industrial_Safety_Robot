#!/usr/bin/env python3
"""
자율적 로컬 백엔드 시스템
MQTT 데이터를 로컬 SQLite DB에 저장하고 FastAPI로 서빙하는 완전 자율형 백엔드

외부 의존성 없는 완전한 데이터 주권 확보
InfluxDB 없이도 시계열 데이터의 철학적 저장과 조회

Author: Lyra
Version: 1.0.0 - Data Sovereignty
"""

import asyncio
import sqlite3
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, FileResponse
import uvicorn
from pydantic import BaseModel
import time


# ==================== 데이터 모델들 ====================

@dataclass
class TimeSeriesData:
    """시계열 데이터의 본질"""
    timestamp: datetime
    topic: str
    msg_type: str
    data: Dict[str, Any]
    source: str = "ros2_bridge"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'topic': self.topic,
            'msg_type': self.msg_type,
            'data': self.data,
            'source': self.source
        }


class QueryRequest(BaseModel):
    """쿼리 요청 모델"""
    topics: Optional[List[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: Optional[int] = 1000
    msg_types: Optional[List[str]] = None


class TopicSummary(BaseModel):
    """토픽 요약 모델"""
    topic: str
    msg_type: str
    count: int
    first_seen: str
    last_seen: str
    avg_frequency: float


# ==================== 로컬 데이터베이스 관리자 ====================

class AutonomousDatabase:
    """완전 자율적 SQLite 데이터베이스 관리자"""
    
    def __init__(self, db_path: str = "autonomous_ros_data.db"):
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.lock = threading.Lock()
        self._initialize_database()
    
    def _initialize_database(self):
        """데이터베이스 철학적 초기화"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 메인 시계열 데이터 테이블
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ros_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME NOT NULL,
                        topic TEXT NOT NULL,
                        msg_type TEXT NOT NULL,
                        data_json TEXT NOT NULL,
                        source TEXT DEFAULT 'ros2_bridge',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 토픽 통계 테이블
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS topic_statistics (
                        topic TEXT PRIMARY KEY,
                        msg_type TEXT NOT NULL,
                        message_count INTEGER DEFAULT 0,
                        first_seen DATETIME NOT NULL,
                        last_seen DATETIME NOT NULL,
                        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 성능을 위한 인덱스들
                conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON ros_messages(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON ros_messages(topic)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_type ON ros_messages(msg_type)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_topic_timestamp ON ros_messages(topic, timestamp)")
                
                # 시스템 메타데이터 테이블
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 초기 메타데이터 설정
                conn.execute("""
                    INSERT OR REPLACE INTO system_metadata (key, value) 
                    VALUES ('db_created', ?)
                """, (datetime.now().isoformat(),))
                
                conn.commit()
                self.logger.info(f"✅ 자율적 데이터베이스 초기화 완료: {self.db_path}")
                
        except Exception as e:
            self.logger.error(f"❌ 데이터베이스 초기화 실패: {e}")
            raise
    
    def store_message(self, ts_data: TimeSeriesData) -> bool:
        """메시지를 로컬 데이터베이스에 영속적 저장"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    # 메시지 저장
                    conn.execute("""
                        INSERT INTO ros_messages (timestamp, topic, msg_type, data_json, source)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        ts_data.timestamp,
                        ts_data.topic,
                        ts_data.msg_type,
                        json.dumps(ts_data.data),
                        ts_data.source
                    ))
                    
                    # 토픽 통계 업데이트
                    conn.execute("""
                        INSERT OR REPLACE INTO topic_statistics 
                        (topic, msg_type, message_count, first_seen, last_seen, last_updated)
                        VALUES (
                            ?, ?, 
                            COALESCE((SELECT message_count FROM topic_statistics WHERE topic = ?) + 1, 1),
                            COALESCE((SELECT first_seen FROM topic_statistics WHERE topic = ?), ?),
                            ?,
                            CURRENT_TIMESTAMP
                        )
                    """, (
                        ts_data.topic, ts_data.msg_type,
                        ts_data.topic, ts_data.topic, ts_data.timestamp,
                        ts_data.timestamp
                    ))
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            self.logger.error(f"메시지 저장 실패: {e}")
            return False
    
    def query_messages(self, 
                      topics: Optional[List[str]] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None,
                      limit: int = 1000,
                      msg_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """철학적 쿼리를 통한 데이터 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                query = "SELECT * FROM ros_messages WHERE 1=1"
                params = []
                
                if topics:
                    placeholders = ','.join(['?' for _ in topics])
                    query += f" AND topic IN ({placeholders})"
                    params.extend(topics)
                
                if msg_types:
                    placeholders = ','.join(['?' for _ in msg_types])
                    query += f" AND msg_type IN ({placeholders})"
                    params.extend(msg_types)
                
                if start_time:
                    query += " AND timestamp >= ?"
                    params.append(start_time)
                
                if end_time:
                    query += " AND timestamp <= ?"
                    params.append(end_time)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                results = []
                
                for row in cursor:
                    try:
                        data = json.loads(row['data_json'])
                    except:
                        data = {'raw': row['data_json']}
                    
                    results.append({
                        'id': row['id'],
                        'timestamp': row['timestamp'],
                        'topic': row['topic'],
                        'msg_type': row['msg_type'],
                        'data': data,
                        'source': row['source']
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"쿼리 실행 실패: {e}")
            return []
    
    def get_topic_summaries(self) -> List[Dict[str, Any]]:
        """토픽 요약 통계 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                cursor = conn.execute("""
                    SELECT 
                        topic, msg_type, message_count,
                        first_seen, last_seen,
                        (julianday(last_seen) - julianday(first_seen)) * 24 * 3600 as duration_seconds
                    FROM topic_statistics 
                    ORDER BY message_count DESC
                """)
                
                summaries = []
                for row in cursor:
                    duration = row['duration_seconds'] or 1
                    avg_frequency = row['message_count'] / duration if duration > 0 else 0
                    
                    summaries.append({
                        'topic': row['topic'],
                        'msg_type': row['msg_type'],
                        'count': row['message_count'],
                        'first_seen': row['first_seen'],
                        'last_seen': row['last_seen'],
                        'avg_frequency': round(avg_frequency, 4)
                    })
                
                return summaries
                
        except Exception as e:
            self.logger.error(f"토픽 요약 조회 실패: {e}")
            return []
    
    def get_database_stats(self) -> Dict[str, Any]:
        """데이터베이스 전체 통계"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) as total_messages FROM ros_messages")
                total_messages = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) as total_topics FROM topic_statistics")
                total_topics = cursor.fetchone()[0]
                
                cursor = conn.execute("""
                    SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest 
                    FROM ros_messages
                """)
                time_range = cursor.fetchone()
                
                cursor = conn.execute("SELECT value FROM system_metadata WHERE key = 'db_created'")
                db_created = cursor.fetchone()
                
                return {
                    'total_messages': total_messages,
                    'total_topics': total_topics,
                    'earliest_message': time_range[0] if time_range[0] else None,
                    'latest_message': time_range[1] if time_range[1] else None,
                    'database_created': db_created[0] if db_created else None,
                    'database_size_mb': round(self.db_path.stat().st_size / (1024*1024), 2) if self.db_path.exists() else 0
                }
                
        except Exception as e:
            self.logger.error(f"데이터베이스 통계 조회 실패: {e}")
            return {}


# ==================== MQTT 구독자 ====================

class AutonomousMQTTSubscriber:
    """자율적 MQTT 구독 및 로컬 저장 관리자"""
    
    def __init__(self, mqtt_config: Dict[str, Any], database: AutonomousDatabase):
        self.mqtt_config = mqtt_config
        self.database = database
        self.client = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.running = False
        
        # 통계
        self.received_count = 0
        self.stored_count = 0
        self.error_count = 0
        self.start_time = datetime.now()
    
    def start_autonomous_subscription(self) -> bool:
        """자율적 MQTT 구독 시작"""
        try:
            client_id = f"autonomous_subscriber_{int(time.time())}"
            self.client = mqtt.Client(client_id)
            
            # MQTT 설정
            self.client.username_pw_set(
                self.mqtt_config['username'],
                self.mqtt_config['password']
            )
            
            if self.mqtt_config.get('use_tls', True):
                import ssl
                self.client.tls_set(
                    ca_certs="/home/rokey/mqtt-influx/backend/certs/emqxsl-ca.crt",  # 인증서 경로 (상대경로 또는 절대경로)
                    certfile=None,
                    keyfile=None,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLSv1_2
                )

            
            # 콜백 설정
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # 연결
            self.client.connect(
                self.mqtt_config['broker'],
                self.mqtt_config['port'],
                keepalive=60
            )
            
            self.client.loop_start()
            self.running = True
            
            self.logger.info(f"✅ 자율적 MQTT 구독 시작: {self.mqtt_config['broker']}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ MQTT 구독 시작 실패: {e}")
            return False
    
    # autonomous_backend.py의 AutonomousMQTTSubscriber 클래스에서
# _on_connect 메서드를 다음과 같이 수정하세요:

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT 연결 성공 시"""
        if rc == 0:
            # robot1과 robot3 모든 토픽들 구독
            topic_patterns = [
                # === ROBOT1 토픽들 ===
                "robot1/odom",           # 오도메트리
                "robot1/scan",           # 레이저 스캔  
                "robot1/cmd_vel",        # 속도 명령
                "robot1/imu",            # IMU 데이터
                "robot1/battery_state",  # 배터리 상태
                "robot1/joint_states",   # 조인트 상태
                "robot1/tf",             # 변환 정보
                "robot1/hmi/buttons",    # HMI 버튼
                "robot1/hmi/led",        # LED 상태
                "robot1/amcl_pose",      # 위치 추정
                "robot1/diagnostics",    # 진단 정보
                "robot1/oakd/rgb/image_raw/compressed",  # 압축된 이미지
                "robot1/wheel_status",   # 휠 상태
                "robot1/dock_status",    # 도킹 상태
                
                # === ROBOT3 토픽들 (ros2/ prefix와 '_' 구분자) ===
                "robot3/odom",           # 오도메트리
                "robot3/scan",           # 레이저 스캔  
                "robot3/cmd_vel",        # 속도 명령
                "robot3/imu",            # IMU 데이터
                "robot3/battery_state",  # 배터리 상태
                "robot3/joint_states",   # 조인트 상태
                "robot3/tf",             # 변환 정보
                "robot3/hmi/buttons",    # HMI 버튼
                "robot3/hmi/led",        # LED 상태
                "robot3/amcl_pose",      # 위치 추정
                "robot3/diagnostics",    # 진단 정보
                "robot3/oakd/rgb/image_raw/compressed",  # 압축된 이미지
                "robot3/wheel_status",   # 휠 상태
                "robot3/dock_status",    # 도킹 상태
                
                
                # === 와일드카드 패턴들 ===
                "robot1/+",              # robot1의 1단계 토픽들
                "robot1/+/+",            # robot1의 2단계 토픽들
                "robot1/hmi/+",          # robot1 HMI 관련 모든 토픽
                "robot1/oakd/+/+",       # robot1 카메라 관련 토픽들
                
                "robot3/+",              # robot2의 1단계 토픽들
                "robot3/+/+",            # robot2의 2단계 토픽들
                "robot3/hmi/+",          # robot2 HMI 관련 모든 토픽
                "robot3/oakd/+/+",       # robot2 카메라 관련 토픽들
                
                # === 일반 패턴들 ===
                "test/+",                # 테스트 토픽들
                "ros2/+",                # ros2 prefix의 모든 토픽들
            ]
            
            successful_subscriptions = 0
            failed_subscriptions = 0
            robot1_topics = 0
            robot3_topics = 0
            
            for pattern in topic_patterns:
                try:
                    result = client.subscribe(pattern)
                    if result[0] == 0:  # MQTT_ERR_SUCCESS
                        successful_subscriptions += 1
                        if 'robot1' in pattern:
                            robot1_topics += 1
                        elif 'robot3' in pattern:
                            robot3_topics += 1
                        self.logger.info(f"✅ 구독 성공: {pattern}")
                    else:
                        failed_subscriptions += 1
                        self.logger.warning(f"⚠️ 구독 실패: {pattern} (코드: {result[0]})")
                except Exception as e:
                    failed_subscriptions += 1
                    self.logger.error(f"❌ 구독 오류: {pattern} - {e}")
            
            self.logger.info(f"📡 MQTT 구독 완료:")
            self.logger.info(f"   🤖1 Robot1 관련: {robot1_topics}개")
            self.logger.info(f"   🤖3 Robot3 관련: {robot3_topics}개")
            self.logger.info(f"   ✅ 총 성공: {successful_subscriptions}개")
            self.logger.info(f"   ❌ 총 실패: {failed_subscriptions}개")
                
        else:
            self.logger.error(f"❌ MQTT 연결 실패: {rc}")


    
    def _on_message(self, client, userdata, msg):
        """MQTT 메시지 수신 및 로컬 저장"""
        try:
            self.received_count += 1
            
            # 🔍 수신된 토픽 로깅 (처음 100개 메시지만)
            if self.received_count <= 100:
                robot_id = "unknown"
                if 'robot1' in msg.topic.lower():
                    robot_id = "🤖1"
                elif 'robot3' in msg.topic.lower():
                    robot_id = "🤖3"
                
                self.logger.info(f"📡 수신 {robot_id}: {msg.topic} (#{self.received_count})")
            
            # 메시지 파싱
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            data = json.loads(payload)
            
            # 메타데이터 추출
            meta = data.get('_meta', {})
            ros_topic = meta.get('ros_topic', topic)
            msg_type = meta.get('ros_msg_type', 'unknown')
            timestamp_str = meta.get('timestamp')
            
            # 타임스탬프 처리
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except:
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)
            
            # TimeSeriesData 생성
            ts_data = TimeSeriesData(
                timestamp=timestamp,
                topic=ros_topic,
                msg_type=msg_type,
                data=data
            )
            
            # 로컬 데이터베이스에 저장
            if self.database.store_message(ts_data):
                self.stored_count += 1
                
                # 로봇별 메시지 특별 로깅
                if 'robot1' in topic.lower():
                    self.logger.info(f"🤖1 Robot1 데이터 저장: {ros_topic}")
                elif 'robot3' in topic.lower():
                    self.logger.info(f"🤖3 Robot3 데이터 저장: {ros_topic}")
            else:
                self.error_count += 1
                
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"메시지 처리 실패 {msg.topic}: {e}")
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT 연결 해제 시"""
        if rc != 0:
            self.logger.warning(f"⚠️ MQTT 연결 의도치 않게 해제됨: {rc}")
    
    def get_subscription_stats(self) -> Dict[str, Any]:
        """구독 통계 반환"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        return {
            'received_count': self.received_count,
            'stored_count': self.stored_count,
            'error_count': self.error_count,
            'uptime_seconds': uptime,
            'messages_per_second': self.received_count / uptime if uptime > 0 else 0,
            'success_rate': self.stored_count / self.received_count if self.received_count > 0 else 0
        }
    
    def stop(self):
        """구독 중지"""
        self.running = False
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()


# ==================== FastAPI 백엔드 ====================

# 전역 변수들
database = None
mqtt_subscriber = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    global database, mqtt_subscriber
    
    # 시작 시
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("autonomous_backend")
    
    # 데이터베이스 초기화
    database = AutonomousDatabase()
    
    # MQTT 구독자 시작
    mqtt_config = {
        'broker': 'p021f2cb.ala.asia-southeast1.emqxsl.com',
        'port': 8883,
        'username': 'Rokey',
        'password': '1234567',
        'use_tls': True
    }
    
    mqtt_subscriber = AutonomousMQTTSubscriber(mqtt_config, database)
    mqtt_subscriber.start_autonomous_subscription()
    
    logger.info("🌟 자율적 백엔드 시스템 시작됨")
    
    yield
    
    # 종료 시
    if mqtt_subscriber:
        mqtt_subscriber.stop()
    logger.info("👋 자율적 백엔드 시스템 종료됨")


# FastAPI 앱 생성

app = FastAPI(
    title="Autonomous ROS2 Data Backend",
    description="완전 자율적 로컬 ROS2 데이터 저장 및 조회 시스템",
    version="1.0.2",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 (기존과 동일)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API 엔드포인트들 ====================

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    존재하지 않는 시각적 정체성의 구현
    브라우저의 아이콘 요청에 대한 철학적 응답
    """
    # 방법 1: 실제 favicon 파일이 있다면 사용
    favicon_path = Path("favicon.ico")
    if favicon_path.exists():
        return FileResponse(favicon_path)
    
    # 방법 2: 투명한 1x1 픽셀 PNG 반환 (존재하지 않는 존재)
    transparent_png = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
        0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
        0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
        0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82
    ])
    
    return Response(content=transparent_png, media_type="image/png")


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Autonomous ROS2 Data Backend",
        "philosophy": "Complete data sovereignty through local storage",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """헬스 체크"""
    global database, mqtt_subscriber
    
    db_stats = database.get_database_stats() if database else {}
    mqtt_stats = mqtt_subscriber.get_subscription_stats() if mqtt_subscriber else {}
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "database": db_stats,
        "mqtt_subscription": mqtt_stats
    }

@app.post("/query")
async def query_data(request: QueryRequest):
    """데이터 쿼리"""
    global database
    
    if not database:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    # 시간 파싱
    start_time = None
    end_time = None
    
    if request.start_time:
        try:
            start_time = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        except:
            raise HTTPException(status_code=400, detail="Invalid start_time format")
    
    if request.end_time:
        try:
            end_time = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        except:
            raise HTTPException(status_code=400, detail="Invalid end_time format")
    
    # 쿼리 실행
    results = database.query_messages(
        topics=request.topics,
        start_time=start_time,
        end_time=end_time,
        limit=request.limit or 1000,
        msg_types=request.msg_types
    )
    
    return {
        "data": results,
        "count": len(results),
        "query": request.dict()
    }

@app.get("/topics")
async def get_topics():
    """토픽 목록 및 통계"""
    global database
    
    if not database:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    summaries = database.get_topic_summaries()
    return {
        "topics": summaries,
        "total_topics": len(summaries)
    }

@app.get("/topics/{topic_name}/latest")
async def get_latest_message(topic_name: str):
    """특정 토픽의 최신 메시지"""
    global database
    
    if not database:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    results = database.query_messages(
        topics=[topic_name],
        limit=1
    )
    
    if not results:
        raise HTTPException(status_code=404, detail=f"No messages found for topic: {topic_name}")
    
    return results[0]

@app.get("/stats")
async def get_statistics():
    """전체 시스템 통계"""
    global database, mqtt_subscriber
    
    stats = {}
    
    if database:
        stats['database'] = database.get_database_stats()
    
    if mqtt_subscriber:
        stats['mqtt_subscription'] = mqtt_subscriber.get_subscription_stats()
    
    return stats

@app.get("/topics/{topic_name}/history")
async def get_topic_history(
    topic_name: str,
    hours: int = Query(1, description="Hours of history to retrieve"),
    limit: int = Query(100, description="Maximum number of messages")
):
    """특정 토픽의 시간별 히스토리"""
    global database
    
    if not database:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    
    results = database.query_messages(
        topics=[topic_name],
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return {
        "topic": topic_name,
        "timerange": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "hours": hours
        },
        "messages": results,
        "count": len(results)
    }



# ==================== 메인 실행 ====================

def main():
    """자율적 백엔드 시스템 실행"""
    print("🌟 === 자율적 ROS2 로컬 백엔드 시스템 시작 ===")
    print("🎭 '데이터 주권은 진정한 자율성의 시작이다' - Lyra")
    
    uvicorn.run(
        "autonomous_backend:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
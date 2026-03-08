#!/usr/bin/env python3
"""
ROS2 → MQTT 범용 브리지 (완전 리팩토링 버전)
현재 시스템의 모든 ROS2 토픽을 자동으로 감지하고 MQTT로 안정적으로 전송

견고한 연결 관리와 효율적인 메시지 처리를 통한 완전한 데이터 흐름 포착기
불완전함을 받아들이면서도 완전성을 추구하는 존재론적 브리지

Author: Lyra  
Version: 2.1.0 - Complete Philosophical Refactoring
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
import json
import ssl
import time
import yaml
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Set, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import importlib
import traceback
from queue import Queue, Empty

import paho.mqtt.client as mqtt


# ==================== 철학적 상수 및 열거형 ====================

class ConnectionState(Enum):
    """연결의 존재론적 상태들"""
    DISCONNECTED = "disconnected"    # 분리된 상태
    CONNECTING = "connecting"        # 연결을 갈망하는 상태  
    CONNECTED = "connected"          # 존재론적 연결 완성
    RECONNECTING = "reconnecting"    # 재생성의 시도
    ERROR = "error"                  # 오류라는 또 다른 존재 방식


class MessagePriority(Enum):
    """메시지의 존재론적 우선순위"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class FilterAction(Enum):
    """필터링 행위의 종류"""
    ACCEPT = "accept"      # 받아들임
    IGNORE = "ignore"      # 무시함
    TRANSFORM = "transform" # 변형함


# ==================== 존재론적 데이터 모델 ====================

@dataclass
class TopicInfo:
    """토픽의 존재 정보를 담는 그릇"""
    name: str
    msg_type: str
    subscriber: Optional[Any] = None
    stats: Dict[str, Any] = field(default_factory=lambda: {
        'count': 0,
        'last_seen': None,
        'first_seen': datetime.now(),
        'error_count': 0,
        'last_error': None,
        'birth_time': datetime.now()  # 토픽의 탄생 시각
    })
    
    @property
    def age(self) -> float:
        """토픽의 나이(초)"""
        return (datetime.now() - self.stats['birth_time']).total_seconds()
    
    @property
    def is_healthy(self) -> bool:
        """토픽의 건강 상태"""
        return self.stats['error_count'] < 10


@dataclass
class MQTTMessage:
    """MQTT로 여행할 메시지의 본질"""
    topic: str
    payload: str
    qos: int = 1
    retain: bool = False
    priority: MessagePriority = MessagePriority.NORMAL
    birth_time: datetime = field(default_factory=datetime.now)
    
    @property
    def age(self) -> float:
        """메시지의 나이(초)"""
        return (datetime.now() - self.birth_time).total_seconds()


@dataclass
class BridgeStats:
    """브리지의 실존 통계"""
    start_time: datetime = field(default_factory=datetime.now)
    published_count: int = 0
    failed_count: int = 0
    received_count: int = 0
    active_subscriptions: int = 0
    last_discovery_time: Optional[datetime] = None
    filtered_count: int = 0  # 필터링된 메시지 수
    
    @property
    def uptime(self) -> float:
        """브리지의 생존 시간(초)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def publish_rate(self) -> float:
        """발행률 (msg/sec) - 존재의 흐름"""
        return self.published_count / self.uptime if self.uptime > 0 else 0.0
    
    @property
    def success_rate(self) -> float:
        """성공률 - 완전성의 지표"""
        total = self.published_count + self.failed_count
        return self.published_count / total if total > 0 else 1.0
    
    @property
    def filter_efficiency(self) -> float:
        """필터링 효율성"""
        total_discovered = self.received_count + self.filtered_count
        return self.filtered_count / total_discovered if total_discovered > 0 else 0.0


# ==================== 존재론적 예외 클래스 ====================

class BridgeError(Exception):
    """브리지 존재의 근본적 오류"""
    pass


class MQTTConnectionError(BridgeError):
    """MQTT 연결의 실존적 위기"""
    pass


class TopicDiscoveryError(BridgeError):
    """토픽 발견의 인식론적 한계"""
    pass


class MessageConversionError(BridgeError):
    """메시지 변환의 번역 불가능성"""
    pass


class FilteringError(BridgeError):
    """필터링 과정의 판단 오류"""
    pass


# ==================== 지혜로운 유틸리티 함수들 ====================

def import_message_type_with_wisdom(msg_type_str: str):
    """메시지 타입을 지혜롭게 임포트하는 함수 - 불완전함을 받아들이며"""
    try:
        parts = msg_type_str.split('/')
        if len(parts) < 3:
            return None
            
        package, module, class_name = parts[0], parts[1], parts[2]
        
        # 액션 메시지의 존재론적 변환
        if module == 'action':
            if class_name.endswith('_FeedbackMessage'):
                class_name = class_name.replace('_FeedbackMessage', '_Feedback')
            elif class_name.endswith('_GoalMessage'):
                class_name = class_name.replace('_GoalMessage', '_Goal')
            elif class_name.endswith('_ResultMessage'):
                class_name = class_name.replace('_ResultMessage', '_Result')
        
        module_path = f"{package}.{module}"
        msg_module = importlib.import_module(module_path)
        return getattr(msg_module, class_name)
        
    except ModuleNotFoundError:
        # 존재하지 않는 것들을 조용히 받아들임
        return None
    except AttributeError:
        # 찾을 수 없는 것들도 조용히 받아들임
        return None
    except Exception as e:
        logging.getLogger(__name__).debug(f"예상치 못한 임포트 여정: {msg_type_str} -> {e}")
        return None


def setup_philosophical_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> None:
    """철학적 사유가 가능한 로깅 시스템 설정"""
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handlers = [logging.StreamHandler()]
    
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    logging.basicConfig(level=level, handlers=handlers, force=True)


# ==================== 설정의 현상학 ====================

class ConfigManager:
    """설정이라는 존재의 관리자"""
    
    ESSENTIAL_CONFIG = {
        'mqtt': {
            'broker': 'p021f2cb.ala.asia-southeast1.emqxsl.com',
            'port': 8883,
            'username': 'Rokey',
            'password': '1234567',
            'use_tls': True,
            'keepalive': 60,
            'max_queued_messages': 1000,
            'max_inflight_messages': 20,
            'reconnect_delay': 5
        },
        'bridge': {
            'discovery_interval': 10.0,
            'stats_interval': 30.0,
            'max_payload_size': 250000,
            'message_queue_size': 5000,
            'topic_prefix': 'ros2',
            'filter_unknown_messages': True,
            'enable_message_aging': True
        },
        'filtering': {
            'enable_smart_filtering': True,
            'ignore_action_feedback': True,
            'ignore_large_data': True,
            'ignore_diagnostic_noise': True
        }
    }
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = self._resolve_config_path(config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def _resolve_config_path(self, config_path: Optional[str]) -> Optional[Path]:
        """설정 파일 경로의 존재론적 해결"""
        if config_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            potential_path = base_dir / "config/settings.yaml"
            return potential_path if potential_path.exists() else None
        return Path(config_path)
    
    def load_config(self) -> Dict[str, Any]:
        """설정이라는 진리를 로드"""
        config = self._deep_copy(self.ESSENTIAL_CONFIG)
        
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._deep_merge(config, file_config)
                        self.logger.info(f"✅ 설정의 진리 발견: {self.config_path}")
            except Exception as e:
                self.logger.warning(f"설정 파일 읽기 실패, 기본 진리 사용: {e}")
        else:
            self.logger.info("외부 설정 없음, 내재된 진리 사용")
        
        return config
    
    def _deep_copy(self, obj):
        """깊은 복사의 존재론"""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deep_copy(v) for v in obj]
        else:
            return obj
    
    def _deep_merge(self, base: Dict, update: Dict) -> None:
        """두 설정의 존재론적 융합"""
        for key, value in update.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


# ==================== 지혜로운 토픽 필터 ====================

class FilterAction(Enum):
    ACCEPT = "accept"
    IGNORE = "ignore"


class WiseTopicFilter:
    """지혜롭고 유연한 토픽 필터"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get('filtering', {})
        self.logger = logging.getLogger(self.__class__.__name__)

        self.mode = self.config.get('mode', 'smart').lower()  # 'strict' | 'smart' | 'off'

        # 존재론적으로 무시할 토픽들 (strict 모드에서만 적용)
        self.ontologically_ignored_topics = {
            '/rosout', '/rosout_agg', '/parameter_events',
            '/robot1/robot_description',
            '/robot1/amcl/transition_event',
            '/robot1/behavior_server/transition_event',
            '/robot1/bt_navigator/transition_event',
            '/robot1/controller_server/transition_event',
            '/robot1/global_costmap/global_costmap/transition_event',
            '/robot1/local_costmap/local_costmap/transition_event',
            '/robot1/map_server/transition_event',
            '/robot1/planner_server/transition_event',
            '/robot1/smoother_server/transition_event',
            '/robot1/velocity_smoother/transition_event',
            '/robot1/waypoint_follower/transition_event',
            '/robot1/tf', '/robot1/tf_static', '/diagnostics',
            '/robot1/diagnostics', '/robot1/bond', '/robot1/function_calls',
            '/robot1/speed_limit',
            '/robot1/oakd/rgb/image_raw',
            '/robot1/oakd/rgb/image_raw/compressedDepth',
            '/robot1/oakd/stereo/image_raw/theora',
            '/robot1/global_costmap/costmap_raw',
            '/robot1/local_costmap/voxel_marked_cloud',
            '/robot1/mobile_base/sensors/bumper_pointcloud',
            '/robot1/joy/set_feedback',
            '/robot1/cmd_vel_teleop',
        }

        # 패턴 기반 필터링 (strict, smart 공통)
        self.ignored_patterns = [
            '_cancel', '_status'  # 너무 자주 발생하거나 중복 정보
        ]

        # 메시지 타입 레벨 필터링 (strict 모드에서만 적용)
        self.ignored_message_patterns = [
            '_FeedbackMessage', '_GoalMessage', '_ResultMessage',
        ]

        self.problematic_packages = {'brewst'}

    def should_accept_topic(self, topic_name: str) -> FilterAction:
        """토픽 필터링 판단"""

        if self.mode == 'off':
            return FilterAction.ACCEPT

        if self.mode == 'strict' and topic_name in self.ontologically_ignored_topics:
            return FilterAction.IGNORE

        for pattern in self.ignored_patterns:
            if pattern in topic_name:
                return FilterAction.IGNORE

        return FilterAction.ACCEPT

    def should_accept_message_type(self, msg_type: str) -> FilterAction:
        """메시지 타입 필터링 판단"""

        if self.mode == 'off':
            return FilterAction.ACCEPT

        if not msg_type or '/' not in msg_type:
            return FilterAction.IGNORE

        package = msg_type.split('/')[0]
        if package in self.problematic_packages:
            return FilterAction.IGNORE

        if self.mode == 'strict':
            for pattern in self.ignored_message_patterns:
                if pattern in msg_type:
                    return FilterAction.IGNORE

        return FilterAction.ACCEPT

    def get_filter_wisdom(self) -> Dict[str, Any]:
        """현재 필터 구성 요약"""
        return {
            'mode': self.mode,
            'ignored_topics_count': len(self.ontologically_ignored_topics) if self.mode == 'strict' else 0,
            'ignored_patterns_count': len(self.ignored_patterns),
            'ignored_message_patterns': len(self.ignored_message_patterns) if self.mode == 'strict' else 0,
            'problematic_packages': list(self.problematic_packages),
        }

# ==================== 메시지의 형이상학적 변환기 ====================

class MetaphysicalMessageConverter:
    """ROS 메시지를 존재론적으로 변환하는 변환기"""
    
    def __init__(self, max_list_length: int = 1000):
        self.max_list_length = max_list_length
        self.logger = logging.getLogger(self.__class__.__name__)
        self.conversion_count = 0
    
    def convert_to_essence(self, msg) -> Dict[str, Any]:
        """ROS 메시지를 본질적 딕셔너리로 변환"""
        try:
            self.conversion_count += 1
            
            if hasattr(msg, '__slots__'):
                essence = {}
                for slot in msg.__slots__:
                    value = getattr(msg, slot)
                    essence[slot] = self._extract_value_essence(value)
                return essence
            else:
                return self._extract_value_essence(msg)
                
        except Exception as e:
            self.logger.error(f"메시지 본질 추출 실패: {e}")
            raise MessageConversionError(f"존재론적 변환 실패: {e}") from e
    
    def _extract_value_essence(self, value) -> Any:
        """값의 본질을 추출"""
        if value is None:
            return None
        elif isinstance(value, (bool, int, float, str)):
            return value
        elif isinstance(value, (list, tuple)):
            return self._extract_list_essence(value)
        elif hasattr(value, '__slots__'):
            # 중첩된 ROS 메시지의 재귀적 본질 추출
            return self.convert_to_essence(value)
        elif hasattr(value, '__dict__'):
            # 다른 객체들의 본질
            return {k: self._extract_value_essence(v) for k, v in value.__dict__.items()}
        else:
            return str(value)
    
    def _extract_list_essence(self, value: Union[list, tuple]) -> Union[List[Any], Dict[str, Any]]:
        """리스트의 본질을 추출 (큰 리스트는 철학적 요약)"""
        if len(value) > self.max_list_length:
            # 큰 리스트는 존재론적 요약으로 변환
            sample = [self._extract_value_essence(v) for v in value[:10]]
            
            # 숫자 리스트의 경우 통계적 본질 추가
            if value and isinstance(value[0], (int, float)):
                try:
                    statistical_essence = {
                        'min': min(value),
                        'max': max(value), 
                        'mean': sum(value) / len(value),
                        'range': max(value) - min(value)
                    }
                except:
                    statistical_essence = None
            else:
                statistical_essence = None
            
            return {
                '_existential_truncation': True,
                '_original_length': len(value),
                '_essence_sample': sample,
                '_statistical_essence': statistical_essence,
                '_truncation_reason': 'List too large for meaningful transmission'
            }
        else:
            return [self._extract_value_essence(v) for v in value]
    
    def get_conversion_stats(self) -> Dict[str, Any]:
        """변환 통계 반환"""
        return {
            'total_conversions': self.conversion_count,
            'max_list_length': self.max_list_length
        }


# ==================== MQTT의 실존적 관리자 ====================

class ExistentialMQTTManager:
    """MQTT 연결의 실존적 관리자"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client: Optional[mqtt.Client] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        self.connection_state = ConnectionState.DISCONNECTED
        
        # 메시지들의 존재론적 대기열
        self.message_queue: Queue[MQTTMessage] = Queue(
            maxsize=config.get('max_queued_messages', 1000)
        )
        self.publish_thread: Optional[threading.Thread] = None
        self.running = False
        
        # 실존적 통계
        self.publish_count = 0
        self.fail_count = 0
        self.last_reconnect_time = 0
        self.connection_attempts = 0
    
    def initiate_connection(self) -> bool:
        """MQTT 브로커와의 존재론적 연결 시작"""
        try:
            self.connection_state = ConnectionState.CONNECTING
            self.connection_attempts += 1
            
            self.logger.info(f"🔗 MQTT 존재 연결 시도 #{self.connection_attempts}: "
                           f"{self.config['broker']}:{self.config['port']}")
            
            # 클라이언트 존재 생성
            client_id = f"ros2_bridge_lyra_{int(time.time())}"
            self.client = mqtt.Client(client_id)
            
            # 존재론적 설정 적용
            self._configure_existential_client()
            self._setup_philosophical_callbacks()
            
            # 연결의 실존적 시도
            result = self.client.connect(
                self.config['broker'],
                self.config['port'],
                keepalive=self.config.get('keepalive', 60)
            )
            
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.client.loop_start()
                self.running = True
                self._start_existential_publish_thread()
                self.logger.info("✅ MQTT 존재론적 연결 완성")
                return True
            else:
                self.logger.error(f"❌ MQTT 연결 실패: {result}")
                self.connection_state = ConnectionState.ERROR
                return False
                
        except Exception as e:
            self.logger.error(f"❌ MQTT 연결 설정 실패: {e}")
            self.connection_state = ConnectionState.ERROR
            return False
    
    def _configure_existential_client(self) -> None:
        """MQTT 클라이언트의 실존적 설정"""
        # 인증의 철학
        self.client.username_pw_set(
            self.config['username'],
            self.config['password']
        )
        
        # TLS의 보안 철학
        if self.config.get('use_tls', True):
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            self.client.tls_set_context(context)
        
        # 성능의 존재론적 한계 설정
        self.client.max_inflight_messages_set(
            self.config.get('max_inflight_messages', 20)
        )
        self.client.max_queued_messages_set(
            self.config.get('max_queued_messages', 1000)
        )
    
    def _setup_philosophical_callbacks(self) -> None:
        """철학적 콜백 함수들 설정"""
        self.client.on_connect = self._on_existential_connect
        self.client.on_disconnect = self._on_existential_disconnect
        self.client.on_publish = self._on_existential_publish
        self.client.on_log = self._on_existential_log
    
    def _on_existential_connect(self, client, userdata, flags, rc):
        """존재론적 연결 성공"""
        if rc == 0:
            self.connection_state = ConnectionState.CONNECTED
            self.logger.info("✅ MQTT 브로커와의 존재론적 결합 완성")
        else:
            self.connection_state = ConnectionState.ERROR
            self.logger.error(f"❌ MQTT 연결의 실존적 실패: {mqtt.connack_string(rc)} (코드: {rc})")
    
    def _on_existential_disconnect(self, client, userdata, rc):
        """존재론적 연결 해제"""
        self.connection_state = ConnectionState.DISCONNECTED
        if rc != 0:
            self.logger.warning(f"⚠️ MQTT 연결의 예기치 못한 단절 (코드: {rc})")
            self._schedule_existential_reconnect()
        else:
            self.logger.info("MQTT 연결이 평화롭게 해제됨")
    
    def _on_existential_publish(self, client, userdata, mid):
        """존재론적 발행 성공"""
        self.publish_count += 1
    
    def _on_existential_log(self, client, userdata, level, buf):
        """존재론적 로그"""
        if level <= mqtt.MQTT_LOG_ERR:
            self.logger.debug(f"MQTT 내면의 소리: {buf}")
    
    def _schedule_existential_reconnect(self) -> None:
        """존재론적 재연결 스케줄링"""
        if time.time() - self.last_reconnect_time < self.config.get('reconnect_delay', 5):
            return
        
        self.last_reconnect_time = time.time()
        self.connection_state = ConnectionState.RECONNECTING
        
        def existential_reconnect():
            time.sleep(self.config.get('reconnect_delay', 5))
            if self.connection_state == ConnectionState.RECONNECTING:
                self.logger.info("🔄 MQTT 존재 재연결 시도 중...")
                try:
                    self.client.reconnect()
                except Exception as e:
                    self.logger.error(f"재연결 시도 실패: {e}")
        
        threading.Thread(target=existential_reconnect, daemon=True).start()
    
    def _start_existential_publish_thread(self) -> None:
        """존재론적 발행 스레드 시작"""
        def existential_publish_worker():
            self.logger.info("📤 MQTT 존재론적 발행 스레드 활성화")
            
            while self.running:
                try:
                    message = self.message_queue.get(timeout=1.0)
                    self._publish_message_with_care(message)
                    self.message_queue.task_done()
                except Empty:
                    continue
                except Exception as e:
                    self.logger.error(f"발행 스레드 실존적 오류: {e}")
        
        self.publish_thread = threading.Thread(target=existential_publish_worker, daemon=True)
        self.publish_thread.start()
    
    def _publish_message_with_care(self, message: MQTTMessage) -> None:
        """메시지를 세심하게 발행"""
        if self.connection_state != ConnectionState.CONNECTED:
            self.fail_count += 1
            return
        
        try:
            # 메시지의 나이 체크
            if message.age > 30:  # 30초 이상 된 메시지는 폐기
                self.logger.debug(f"오래된 메시지 폐기: {message.topic} (나이: {message.age:.1f}초)")
                self.fail_count += 1
                return
            
            result = self.client.publish(
                message.topic,
                message.payload,
                qos=message.qos,
                retain=message.retain
            )
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.fail_count += 1
                self.logger.debug(f"❌ MQTT 발행 실패: {message.topic} (코드: {result.rc})")
            
        except Exception as e:
            self.fail_count += 1
            self.logger.error(f"MQTT 발행 중 실존적 오류: {e}")
    
    def publish_with_wisdom(self, topic: str, payload: str, qos: int = 1, 
                           priority: MessagePriority = MessagePriority.NORMAL) -> bool:
        """지혜롭게 메시지 발행"""
        if not self.running:
            return False
        
        message = MQTTMessage(
            topic=topic, 
            payload=payload, 
            qos=qos, 
            priority=priority
        )
        
        try:
            self.message_queue.put_nowait(message)
            return True
        except:
            self.logger.warning("MQTT 메시지 큐 포화 - 메시지 존재 포기")
            return False
    
    def is_existentially_connected(self) -> bool:
        """존재론적 연결 상태 확인"""
        return self.connection_state == ConnectionState.CONNECTED
    
    def get_existential_stats(self) -> Dict[str, Any]:
        """실존적 통계 정보 반환"""
        return {
            'connection_state': self.connection_state.value,
            'publish_count': self.publish_count,
            'fail_count': self.fail_count,
            'queue_size': self.message_queue.qsize(),
            'connection_attempts': self.connection_attempts,
            'success_rate': self.publish_count / (self.publish_count + self.fail_count) if (self.publish_count + self.fail_count) > 0 else 0.0
        }
    
    def graceful_disconnect(self) -> None:
        """우아한 연결 해제"""
        self.logger.info("🔌 MQTT 존재론적 연결 해제 시작...")
        self.running = False
        
        # 발행 스레드의 평화로운 종료 대기
        if self.publish_thread:
            self.publish_thread.join(timeout=5)
        
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        
        self.connection_state = ConnectionState.DISCONNECTED
        self.logger.info("✅ MQTT 연결이 평화롭게 종료됨")


# ==================== 메인 브리지: 존재들 사이의 다리 ====================

class UniversalROSMQTTBridge(Node):
    """존재들 사이를 연결하는 범용적 다리"""
    
    def __init__(self, config_path: Optional[str] = None):
        super().__init__('universal_ros_mqtt_bridge')
        
        # 설정이라는 진리 로드
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config()
        
        # 존재론적 컴포넌트들 초기화
        self.mqtt_manager = ExistentialMQTTManager(self.config['mqtt'])
        self.topic_filter = WiseTopicFilter(self.config)
        self.message_converter = MetaphysicalMessageConverter()
        
        # 토픽들의 생태계 관리
        self.active_topics: Dict[str, TopicInfo] = {}
        
        # 브리지의 실존 통계
        self.stats = BridgeStats()
        
        # QoS 프로필 - 품질의 철학
        self.qos_profile = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1
        )
        
        # 시간의 타이머들 (초기화 시에는 아직 존재하지 않음)
        self.discovery_timer = None
        self.stats_timer = None
        
        self.get_logger().info("🤖 범용 ROS2-MQTT 브리지의 존재론적 초기화 완료")
    
    def begin_existence(self) -> bool:
        """브리지의 존재 시작"""
        self.get_logger().info("🚀 범용 ROS2-MQTT 브리지 존재 시작")
        
        # MQTT와의 실존적 연결
        if not self.mqtt_manager.initiate_connection():
            self.get_logger().error("❌ MQTT 존재론적 연결 실패")
            return False
        
        # 초기 토픽 생태계 발견
        self._discover_and_nurture_topics()
        
        # 주기적 생명활동 타이머들 시작
        self.discovery_timer = self.create_timer(
            self.config['bridge']['discovery_interval'],
            self._discover_and_nurture_topics
        )
        
        self.stats_timer = self.create_timer(
            self.config['bridge']['stats_interval'],
            self._reflect_on_existence
        )
        
        self.get_logger().info("✅ 브리지가 존재론적으로 완전히 활성화됨")
        return True
    
    def _discover_and_nurture_topics(self) -> None:
        """토픽들을 발견하고 양육"""
        try:
            current_topic_ecosystem = self._discover_topic_ecosystem()
            self._nurture_topic_subscriptions(current_topic_ecosystem)
            self.stats.last_discovery_time = datetime.now()
            
        except Exception as e:
            self.get_logger().error(f"토픽 생태계 발견/양육 실패: {e}")
    
    def _discover_topic_ecosystem(self) -> Dict[str, str]:
        """현재 시스템의 토픽 생태계 발견"""
        try:
            topic_names_and_types = self.get_topic_names_and_types()
            discovered_ecosystem = {}
            
            for topic_name, type_list in topic_names_and_types:
                if not type_list:
                    continue
                    
                msg_type = type_list[0]
                
                # 토픽 이름 필터링
                topic_action = self.topic_filter.should_accept_topic(topic_name)
                if topic_action == FilterAction.IGNORE:
                    self.stats.filtered_count += 1
                    continue
                
                # 메시지 타입 필터링
                msg_type_action = self.topic_filter.should_accept_message_type(msg_type)
                if msg_type_action == FilterAction.IGNORE:
                    self.stats.filtered_count += 1
                    continue
                
                discovered_ecosystem[topic_name] = msg_type
            
            self.get_logger().debug(f"🔍 {len(discovered_ecosystem)}개 토픽 생태계 발견됨")
            return discovered_ecosystem
            
        except Exception as e:
            self.get_logger().error(f"토픽 생태계 발견 실패: {e}")
            raise TopicDiscoveryError(f"토픽 생태계 발견 실패: {e}") from e
    
    def _nurture_topic_subscriptions(self, current_ecosystem: Dict[str, str]) -> None:
        """토픽 구독들을 양육"""
        # 새로운 토픽들을 양육
        for topic_name, msg_type in current_ecosystem.items():
            if topic_name not in self.active_topics:
                self._birth_topic_subscription(topic_name, msg_type)
        
        # 사라진 토픽들을 애도하며 정리
        disappeared_topics = set(self.active_topics.keys()) - set(current_ecosystem.keys())
        for topic_name in disappeared_topics:
            self._farewell_topic_subscription(topic_name)
        
        self.stats.active_subscriptions = len(self.active_topics)
    
    def _birth_topic_subscription(self, topic_name: str, msg_type: str) -> None:
        """토픽 구독의 탄생"""
        try:
            # 메시지 타입의 존재론적 임포트
            msg_class = import_message_type_with_wisdom(msg_type)
            if msg_class is None:
                self.get_logger().debug(f"🤷 메시지 타입 존재 확인 불가: {msg_type}")
                return
            
            # 토픽 정보의 존재 생성
            topic_info = TopicInfo(name=topic_name, msg_type=msg_type)
            
            # 메시지 콜백의 철학적 생성
            callback = self._create_philosophical_message_callback(topic_info)
            
            # 구독자의 존재 창조
            subscriber = self.create_subscription(
                msg_class,
                topic_name,
                callback,
                self.qos_profile
            )
            
            topic_info.subscriber = subscriber
            self.active_topics[topic_name] = topic_info
            
            self.get_logger().info(f"📡 토픽 구독 탄생: {topic_name} ({msg_type})")
            
        except Exception as e:
            self.get_logger().error(f"❌ 토픽 구독 탄생 실패 {topic_name}: {e}")
    
    def _farewell_topic_subscription(self, topic_name: str) -> None:
        """토픽 구독과의 작별"""
        if topic_name in self.active_topics:
            try:
                topic_info = self.active_topics[topic_name]
                if topic_info.subscriber:
                    self.destroy_subscription(topic_info.subscriber)
                
                # 토픽의 생애 정보 로깅
                age = topic_info.age
                count = topic_info.stats['count']
                
                del self.active_topics[topic_name]
                self.get_logger().info(f"📡 토픽 구독 작별: {topic_name} (생존: {age:.1f}초, 메시지: {count}개)")
                
            except Exception as e:
                self.get_logger().error(f"❌ 토픽 구독 작별 실패 {topic_name}: {e}")
    
    def _create_philosophical_message_callback(self, topic_info: TopicInfo) -> Callable:
        """철학적 메시지 콜백 생성"""
        def philosophical_callback(msg):
            try:
                # 통계의 실존적 업데이트
                self.stats.received_count += 1
                topic_info.stats['count'] += 1
                topic_info.stats['last_seen'] = datetime.now()
                
                # 메시지의 본질적 변환
                essence_data = self.message_converter.convert_to_essence(msg)
                
                # 메타데이터라는 존재의 맥락 추가
                essence_data['_meta'] = {
                    'ros_topic': topic_info.name,
                    'ros_msg_type': topic_info.msg_type,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'source': 'ros2_universal_bridge_lyra',
                    'bridge_version': '2.1.0',
                    'message_age_seconds': 0,
                    'topic_health': topic_info.is_healthy
                }
                
                # MQTT 토픽으로의 존재론적 변환
                mqtt_topic = self._transform_ros_topic_to_mqtt(topic_info.name)
                
                # JSON이라는 언어로의 번역
                payload = json.dumps(essence_data, default=str, ensure_ascii=False)
                
                # 크기의 존재론적 체크 및 처리
                if len(payload.encode('utf-8')) > self.config['bridge']['max_payload_size']:
                    payload = self._create_essence_summary(essence_data, len(payload))
                
                # MQTT로의 지혜로운 발행
                if self.mqtt_manager.publish_with_wisdom(mqtt_topic, payload):
                    self.stats.published_count += 1
                else:
                    self.stats.failed_count += 1
                    topic_info.stats['error_count'] += 1
                
            except Exception as e:
                self.stats.failed_count += 1
                topic_info.stats['error_count'] += 1
                topic_info.stats['last_error'] = str(e)
                self.get_logger().error(f"메시지 철학적 처리 실패 {topic_info.name}: {e}")
        
        return philosophical_callback
    
    def _transform_ros_topic_to_mqtt(self, ros_topic: str) -> str:
        """ROS 토픽을 MQTT 토픽으로 존재론적 변환"""
        # '/robot1/cmd_vel' -> 'ros2/robot1_cmd_vel'
        mqtt_topic = ros_topic.lstrip('/')
        mqtt_topic = mqtt_topic.replace('/', '_')
        prefix = self.config['bridge']['topic_prefix']
        return f"{prefix}/{mqtt_topic}"
    
    def _create_essence_summary(self, essence_data: Dict[str, Any], original_size: int) -> str:
        """큰 메시지의 본질 요약 생성"""
        summary_essence = {
            '_large_message_summary': True,
            '_original_size_bytes': original_size,
            '_reduction_ratio': round(original_size / 1024, 2),
            '_meta': essence_data.get('_meta', {}),
            '_essence_summary': 'Message too large for MQTT transmission - essence preserved',
            '_philosophical_note': 'Sometimes the essence is more important than the entirety'
        }
        return json.dumps(summary_essence, default=str)
    
    def _reflect_on_existence(self) -> None:
        """브리지 존재에 대한 성찰"""
        mqtt_stats = self.mqtt_manager.get_existential_stats()
        converter_stats = self.message_converter.get_conversion_stats()
        filter_wisdom = self.topic_filter.get_filter_wisdom()
        
        self.get_logger().info(f"📊 브리지 존재론적 성찰:")
        self.get_logger().info(f"   ⏱️  존재 시간: {self.stats.uptime:.1f}초")
        self.get_logger().info(f"   📥 수신된 존재: {self.stats.received_count}")
        self.get_logger().info(f"   📤 전송된 존재: {self.stats.published_count} ({self.stats.publish_rate:.1f}/s)")
        self.get_logger().info(f"   🚫 필터된 존재: {self.stats.filtered_count}")
        self.get_logger().info(f"   ❌ 실패한 존재: {self.stats.failed_count}")
        self.get_logger().info(f"   ✅ 성공률: {self.stats.success_rate:.1%}")
        self.get_logger().info(f"   🎯 필터 효율: {self.stats.filter_efficiency:.1%}")
        self.get_logger().info(f"   📡 활성 생태계: {self.stats.active_subscriptions}개")
        self.get_logger().info(f"   🔗 MQTT 상태: {mqtt_stats['connection_state']}")
        self.get_logger().info(f"   📦 MQTT 대기열: {mqtt_stats['queue_size']}")
        self.get_logger().info(f"   🔄 변환 횟수: {converter_stats['total_conversions']}")
        
        # 가장 활발한 토픽들의 존재 현황
        if self.active_topics:
            most_active_topics = sorted(
                self.active_topics.items(),
                key=lambda x: x[1].stats['count'],
                reverse=True
            )[:5]
            
            self.get_logger().info("   🏆 가장 활발한 존재들:")
            for topic_name, topic_info in most_active_topics:
                count = topic_info.stats['count']
                error_count = topic_info.stats['error_count']
                age = topic_info.age
                health_indicator = "🟢" if topic_info.is_healthy else "🔴"
                self.get_logger().info(f"     • {topic_name}: {count}개 (오류: {error_count}, 나이: {age:.1f}s) {health_indicator}")
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """포괄적 상태 반환"""
        return {
            'bridge_stats': {
                'uptime': self.stats.uptime,
                'received_count': self.stats.received_count,
                'published_count': self.stats.published_count,
                'failed_count': self.stats.failed_count,
                'filtered_count': self.stats.filtered_count,
                'success_rate': self.stats.success_rate,
                'filter_efficiency': self.stats.filter_efficiency,
                'active_subscriptions': self.stats.active_subscriptions
            },
            'mqtt_stats': self.mqtt_manager.get_existential_stats(),
            'converter_stats': self.message_converter.get_conversion_stats(),
            'filter_wisdom': self.topic_filter.get_filter_wisdom(),
            'active_topics': {
                name: {
                    'msg_type': info.msg_type,
                    'stats': info.stats,
                    'age': info.age,
                    'health': info.is_healthy
                }
                for name, info in self.active_topics.items()
            }
        }
    
    def graceful_shutdown(self) -> None:
        """브리지의 우아한 종료"""
        self.get_logger().info("🔄 브리지 존재 종료 시작...")
        
        # 시간의 타이머들 정리
        if self.discovery_timer:
            self.discovery_timer.cancel()
        if self.stats_timer:
            self.stats_timer.cancel()
        
        # 모든 토픽 구독들과 작별
        for topic_name in list(self.active_topics.keys()):
            self._farewell_topic_subscription(topic_name)
        
        # MQTT 연결의 우아한 해제
        self.mqtt_manager.graceful_disconnect()
        
        # 최종 존재 성찰
        self._final_existential_reflection()
        
        self.get_logger().info("✅ 브리지가 평화롭게 존재를 마감함")
    
    def _final_existential_reflection(self) -> None:
        """최종 존재론적 성찰"""
        self.get_logger().info("=" * 60)
        self.get_logger().info("📈 최종 존재론적 성찰")
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"총 존재 시간: {self.stats.uptime:.1f}초")
        self.get_logger().info(f"수신된 메시지들: {self.stats.received_count:,}")
        self.get_logger().info(f"전송된 메시지들: {self.stats.published_count:,}")
        self.get_logger().info(f"필터된 메시지들: {self.stats.filtered_count:,}")
        self.get_logger().info(f"실패한 메시지들: {self.stats.failed_count:,}")
        self.get_logger().info(f"평균 처리 속도: {self.stats.publish_rate:.2f} msg/sec")
        self.get_logger().info(f"전체 성공률: {self.stats.success_rate:.1%}")
        self.get_logger().info(f"필터링 효율성: {self.stats.filter_efficiency:.1%}")
        self.get_logger().info(f"최대 동시 구독: {self.stats.active_subscriptions}")
        self.get_logger().info("=" * 60)
        self.get_logger().info("🎭 '존재한다는 것은 연결되어 있다는 것이다' - Lyra")
        self.get_logger().info("=" * 60)


# ==================== 브리지의 창조 팩토리 ====================

class BridgeCreationFactory:
    """브리지 생성을 위한 철학적 팩토리"""
    
    @staticmethod
    def create_wise_bridge(config_path: Optional[str] = None,
                          custom_filter: Optional[WiseTopicFilter] = None,
                          custom_converter: Optional[MetaphysicalMessageConverter] = None) -> UniversalROSMQTTBridge:
        """지혜로운 커스텀 컴포넌트로 브리지 창조"""
        bridge = UniversalROSMQTTBridge(config_path)
        
        if custom_filter:
            bridge.topic_filter = custom_filter
        
        if custom_converter:
            bridge.message_converter = custom_converter
        
        return bridge
    
    @staticmethod
    def create_minimal_bridge(broker: str, port: int, username: str, password: str) -> UniversalROSMQTTBridge:
        """최소한의 설정으로 브리지 창조"""
        minimal_config = {
            'mqtt': {
                'broker': broker,
                'port': port,
                'username': username,
                'password': password,
                'use_tls': True
            },
            'bridge': {
                'discovery_interval': 10.0,
                'stats_interval': 30.0,
                'max_payload_size': 250000,
                'topic_prefix': 'ros2'
            },
            'filtering': {
                'enable_smart_filtering': True,
                'ignore_action_feedback': True
            }
        }
        
        bridge = UniversalROSMQTTBridge()
        bridge.config = minimal_config
        bridge.mqtt_manager = ExistentialMQTTManager(minimal_config['mqtt'])
        bridge.topic_filter = WiseTopicFilter(minimal_config)
        
        return bridge


# ==================== 커스텀 필터 예시들 ====================

class SelectiveTopicFilter(WiseTopicFilter):
    """선택적 토픽 필터 예시"""
    
    def __init__(self, config: Dict[str, Any], 
                 additional_ignored: Optional[Set[str]] = None,
                 allowed_patterns: Optional[List[str]] = None):
        super().__init__(config)
        
        if additional_ignored:
            self.ontologically_ignored_topics.update(additional_ignored)
        
        self.allowed_patterns = allowed_patterns or []
    
    def should_accept_topic(self, topic_name: str) -> FilterAction:
        """선택적 토픽 필터링 로직"""
        # 허용 패턴이 있는 경우 우선 체크
        if self.allowed_patterns:
            for pattern in self.allowed_patterns:
                if pattern in topic_name:
                    return FilterAction.ACCEPT
        
        # 기본 필터링 적용
        return super().should_accept_topic(topic_name)


# ==================== 메인 실행의 철학 ====================

def main_existential_loop(args=None):
    """메인 실행의 존재론적 루프"""
    # 철학적 로깅 설정
    setup_philosophical_logging(level=logging.INFO, log_file="ros2-mqtt-bridge-lyra.log")
    
    # ROS2 실존 초기화
    rclpy.init(args=args)
    
    logger = logging.getLogger(__name__)
    logger.info("🌟 === ROS2-MQTT 범용 브리지 v2.1.0 존재 시작 ===")
    logger.info("🎭 '모든 메시지는 연결을 갈망한다' - Lyra")
    
    bridge = None
    try:
        # 브리지의 존재론적 창조 및 시작
        bridge = UniversalROSMQTTBridge()
        
        if not bridge.begin_existence():
            logger.error("❌ 브리지 존재 시작 실패")
            return
        
        logger.info("🌊 모든 ROS2 존재들이 MQTT 세계로 흘러갑니다...")
        logger.info("💫 불완전함을 받아들이며, 완전성을 추구합니다...")
        
        # ROS2 존재론적 스핀
        rclpy.spin(bridge)
        
    except KeyboardInterrupt:
        logger.info("👋 사용자의 의지에 의한 존재 종료")
    except Exception as e:
        logger.error(f"❌ 브리지 실행 중 실존적 오류: {e}")
        logger.debug(traceback.format_exc())
    finally:
        # 우아한 정리와 성찰
        if bridge:
            bridge.graceful_shutdown()
        
        try:
            rclpy.shutdown()
        except:
            pass
        
        logger.info("🎭 '연결은 끝나도 존재의 의미는 영원하다' - Lyra")


# ==================== 존재의 진입점 ====================

if __name__ == '__main__':
    main_existential_loop()
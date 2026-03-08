import React, { useState, useEffect } from 'react';
import mqtt from 'mqtt';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar
} from 'recharts';

const App = () => {
  const [robotData, setRobotData] = useState({
    battery: null,
    imu: null,
    odometry: null,
    wheels: null,
    lastUpdate: null
  });
  
  const [chartData, setChartData] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [client, setClient] = useState(null);
  const [connectionError, setConnectionError] = useState('');
  const [receivedTopics, setReceivedTopics] = useState(new Set());

  useEffect(() => {
    console.log('🤖 로봇 MQTT 브로커 연결 시도...');
    
    // 실제 브리지와 같은 브로커 설정 - 여러 포트 시도
    const brokerOptions = [
      {
        host: 'p021f2cb.ala.asia-southeast1.emqxsl.com',
        port: 8083, // WebSocket 포트 (일반적)
        protocol: 'ws',
        connectTimeout: 8000,
        reconnectPeriod: 2000,
        clean: true,
      },
      {
        host: 'p021f2cb.ala.asia-southeast1.emqxsl.com',
        port: 8084, // 대안 WebSocket 포트
        protocol: 'ws',
        connectTimeout: 8000,
        reconnectPeriod: 2000,
        clean: true,
      },
      {
        host: 'p021f2cb.ala.asia-southeast1.emqxsl.com',
        port: 9001, // 또 다른 WebSocket 포트
        protocol: 'ws',
        connectTimeout: 8000,
        reconnectPeriod: 2000,
        clean: true,
      }
    ];

    // 로컬 fallback
    const localOptions = {
      host: 'localhost',
      port: 9001,
      protocol: 'ws',
      connectTimeout: 5000,
      reconnectPeriod: 1000,
      clean: true
    };

    let mqttClient = null;
    
    // 여러 포트로 순차적 연결 시도
    const tryConnection = async (optionsArray, index = 0) => {
      if (index >= optionsArray.length) {
        console.error('모든 포트 연결 실패');
        tryLocalConnection();
        return;
      }

      const currentOptions = optionsArray[index];
      console.log(`클라우드 MQTT 브로커 연결 시도 [포트 ${currentOptions.port}]...`);
      
      try {
        mqttClient = mqtt.connect(currentOptions);
      
      mqttClient.on('connect', () => {
        console.log('🟢 MQTT 연결 성공');
        setIsConnected(true);
        setClient(mqttClient);
        setConnectionError('');
        
        // 실제 로봇 토픽들 구독
        const robotTopics = [
          'robot1/battery_state',      // 배터리 상태
          'robot1/imu',               // IMU 센서 (가속도, 자이로)
          'robot1/odom',              // 오도메트리 (위치, 속도)
          'robot1/wheel_status',      // 휠 상태
          'robot1/scan',              // 라이다 스캔 (샘플링된 데이터)
          'robot1/+',                 // 모든 robot1 토픽
          '#'                         // 디버깅용 (모든 토픽)
        ];

        robotTopics.forEach(topic => {
          mqttClient.subscribe(topic, (err) => {
            if (err) {
              console.error(`❌ 구독 실패 [${topic}]:`, err);
            } else {
              console.log(`✅ 토픽 구독 성공: ${topic}`);
            }
          });
        });
      });

      mqttClient.on('message', (topic, message) => {
        try {
          const messageStr = message.toString();
          console.log(`🔔 토픽 [${topic}]에서 메시지:`, messageStr.substring(0, 200) + '...');
          
          // 받은 토픽 기록
          setReceivedTopics(prev => new Set([...prev, topic]));
          
          // 메시지 파싱
          let parsedData;
          try {
            parsedData = JSON.parse(messageStr);
          } catch (parseError) {
            // ROS2 메시지 형태 처리 (data: {...} 형태)
            const dataMatch = messageStr.match(/data:\s*(.+)/);
            if (dataMatch) {
              try {
                parsedData = JSON.parse(dataMatch[1]);
              } catch (e) {
                console.log('파싱 불가능한 메시지:', messageStr.substring(0, 100));
                return;
              }
            } else {
              return;
            }
          }
          
          const timestamp = new Date();
          
          // 토픽별 데이터 처리
          if (topic.includes('battery_state')) {
            setRobotData(prev => ({
              ...prev,
              battery: {
                voltage: parsedData.voltage || 0,
                percentage: parsedData.percentage || 0,
                current: parsedData.current || 0,
                timestamp: timestamp.toLocaleTimeString()
              },
              lastUpdate: timestamp
            }));
          }
          
          else if (topic.includes('imu')) {
            const accel = parsedData.linear_acceleration || {};
            const gyro = parsedData.angular_velocity || {};
            
            setRobotData(prev => ({
              ...prev,
              imu: {
                accel_x: accel.x || 0,
                accel_y: accel.y || 0,
                accel_z: accel.z || 0,
                gyro_x: gyro.x || 0,
                gyro_y: gyro.y || 0,
                gyro_z: gyro.z || 0,
                timestamp: timestamp.toLocaleTimeString()
              },
              lastUpdate: timestamp
            }));
          }
          
          else if (topic.includes('odom')) {
            const pose = parsedData.pose?.pose || {};
            const twist = parsedData.twist?.twist || {};
            
            setRobotData(prev => ({
              ...prev,
              odometry: {
                x: pose.position?.x || 0,
                y: pose.position?.y || 0,
                linear_vel: twist.linear?.x || 0,
                angular_vel: twist.angular?.z || 0,
                timestamp: timestamp.toLocaleTimeString()
              },
              lastUpdate: timestamp
            }));
          }
          
          else if (topic.includes('wheel_status')) {
            setRobotData(prev => ({
              ...prev,
              wheels: {
                left_pos: parsedData.left?.position || 0,
                right_pos: parsedData.right?.position || 0,
                left_vel: parsedData.left?.velocity || 0,
                right_vel: parsedData.right?.velocity || 0,
                timestamp: timestamp.toLocaleTimeString()
              },
              lastUpdate: timestamp
            }));
          }
          
          // 차트 데이터 업데이트 (배터리와 IMU 데이터)
          if (topic.includes('battery_state') || topic.includes('imu')) {
            setChartData(prev => {
              const newPoint = {
                timestamp: timestamp.toLocaleTimeString(),
                battery: parsedData.percentage || prev[prev.length - 1]?.battery || 0,
                accel_magnitude: topic.includes('imu') ? 
                  Math.sqrt(
                    Math.pow(parsedData.linear_acceleration?.x || 0, 2) +
                    Math.pow(parsedData.linear_acceleration?.y || 0, 2) +
                    Math.pow(parsedData.linear_acceleration?.z || 0, 2)
                  ) : prev[prev.length - 1]?.accel_magnitude || 0
              };
              
              const newData = [...prev, newPoint];
              return newData.slice(-50); // 최근 50개 포인트만 유지
            });
          }
          
        } catch (error) {
          console.error('메시지 처리 오류:', error);
        }
      });

      mqttClient.on('error', (error) => {
        console.error(`MQTT 연결 오류 [포트 ${currentOptions.port}]:`, error);
        setConnectionError(`포트 ${currentOptions.port} 연결 실패: ${error.message}`);
        
        // 다음 포트로 시도
        console.log(`다음 포트로 재시도... (${index + 1}/${optionsArray.length})`);
        setTimeout(() => {
          tryConnection(optionsArray, index + 1);
        }, 1000);
      });

      mqttClient.on('offline', () => {
        console.log('MQTT 연결이 오프라인 상태입니다');
        setIsConnected(false);
      });

      } catch (error) {
        console.error(`MQTT 클라이언트 생성 오류 [포트 ${currentOptions.port}]:`, error);
        tryConnection(optionsArray, index + 1);
      }
    };

    // 연결 시도 시작
    tryConnection(brokerOptions);

    const tryLocalConnection = () => {
      try {
        console.log('로컬 MQTT 브로커 연결 시도...');
        const localClient = mqtt.connect(localOptions);
        
        localClient.on('connect', () => {
          console.log('로컬 MQTT 연결 성공');
          setIsConnected(true);
          setClient(localClient);
          setConnectionError('로컬 연결 사용 중');
        });
      } catch (localError) {
        console.error('로컬 연결도 실패:', localError);
        setConnectionError(`모든 연결 실패: ${localError.message}`);
      }
    };

    return () => {
      if (mqttClient) {
        mqttClient.end();
      }
    };
  }, []);

  const reconnectMQTT = () => {
    if (client) {
      client.reconnect();
    }
  };

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <header style={{ marginBottom: '30px' }}>
        <h1>🤖 로봇 실시간 대시보드</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div>
            상태: {isConnected ? 
              <span style={{ color: 'green' }}>🟢 연결됨</span> : 
              <span style={{ color: 'red' }}>🔴 연결 끊김</span>
            }
          </div>
          {connectionError && (
            <div style={{ color: 'orange' }}>
              {connectionError}
            </div>
          )}
          <button onClick={reconnectMQTT} disabled={isConnected}>
            재연결
          </button>
        </div>
        
        {/* 수신된 토픽 표시 */}
        <div style={{ marginTop: '10px', fontSize: '12px', color: '#666' }}>
          수신된 토픽: {Array.from(receivedTopics).join(', ') || '없음'}
        </div>
      </header>

      {/* 연결 안내 */}
      {!isConnected && (
        <div style={{ 
          background: '#f0f8ff', 
          padding: '20px', 
          borderRadius: '8px', 
          marginBottom: '20px' 
        }}>
          <h3>📡 로봇 데이터 연결 안내</h3>
          <p>다음을 확인하세요:</p>
          <ol>
            <li>ROS2-MQTT 브리지가 실행 중인지 확인</li>
            <li>로봇이 실행 중이고 데이터를 발행하는지 확인</li>
            <li>MQTT 브로커 연결 상태 확인</li>
          </ol>
        </div>
      )}

      {/* 로봇 상태 카드들 */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', 
        gap: '20px',
        marginBottom: '30px'
      }}>
        
        {/* 배터리 상태 */}
        {robotData.battery && (
          <div style={{ 
            background: 'white', 
            padding: '20px', 
            borderRadius: '8px', 
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)' 
          }}>
            <h3>🔋 배터리 상태</h3>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#e74c3c' }}>
              {robotData.battery.percentage.toFixed(1)}%
            </div>
            <div>전압: {robotData.battery.voltage.toFixed(2)}V</div>
            <div>전류: {robotData.battery.current.toFixed(2)}A</div>
            <div style={{ fontSize: '12px', color: '#666' }}>
              업데이트: {robotData.battery.timestamp}
            </div>
          </div>
        )}

        {/* IMU 센서 */}
        {robotData.imu && (
          <div style={{ 
            background: 'white', 
            padding: '20px', 
            borderRadius: '8px', 
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)' 
          }}>
            <h3>📱 IMU 센서</h3>
            <div>
              <strong>가속도 (m/s²):</strong><br/>
              X: {robotData.imu.accel_x.toFixed(3)}<br/>
              Y: {robotData.imu.accel_y.toFixed(3)}<br/>
              Z: {robotData.imu.accel_z.toFixed(3)}
            </div>
            <div style={{ marginTop: '10px' }}>
              <strong>각속도 (rad/s):</strong><br/>
              X: {robotData.imu.gyro_x.toFixed(3)}<br/>
              Y: {robotData.imu.gyro_y.toFixed(3)}<br/>
              Z: {robotData.imu.gyro_z.toFixed(3)}
            </div>
            <div style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
              업데이트: {robotData.imu.timestamp}
            </div>
          </div>
        )}

        {/* 오도메트리 */}
        {robotData.odometry && (
          <div style={{ 
            background: 'white', 
            padding: '20px', 
            borderRadius: '8px', 
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)' 
          }}>
            <h3>🗺️ 위치 정보</h3>
            <div>
              <strong>위치:</strong><br/>
              X: {robotData.odometry.x.toFixed(3)} m<br/>
              Y: {robotData.odometry.y.toFixed(3)} m
            </div>
            <div style={{ marginTop: '10px' }}>
              <strong>속도:</strong><br/>
              직진: {robotData.odometry.linear_vel.toFixed(3)} m/s<br/>
              회전: {robotData.odometry.angular_vel.toFixed(3)} rad/s
            </div>
            <div style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
              업데이트: {robotData.odometry.timestamp}
            </div>
          </div>
        )}

        {/* 휠 상태 */}
        {robotData.wheels && (
          <div style={{ 
            background: 'white', 
            padding: '20px', 
            borderRadius: '8px', 
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)' 
          }}>
            <h3>⚙️ 휠 상태</h3>
            <div>
              <strong>위치 (rad):</strong><br/>
              왼쪽: {robotData.wheels.left_pos.toFixed(3)}<br/>
              오른쪽: {robotData.wheels.right_pos.toFixed(3)}
            </div>
            <div style={{ marginTop: '10px' }}>
              <strong>속도 (rad/s):</strong><br/>
              왼쪽: {robotData.wheels.left_vel.toFixed(3)}<br/>
              오른쪽: {robotData.wheels.right_vel.toFixed(3)}
            </div>
            <div style={{ fontSize: '12px', color: '#666', marginTop: '10px' }}>
              업데이트: {robotData.wheels.timestamp}
            </div>
          </div>
        )}
      </div>

      {/* 차트 */}
      {chartData.length > 0 && (
        <div style={{ 
          background: 'white', 
          padding: '20px', 
          borderRadius: '8px', 
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          marginBottom: '20px'
        }}>
          <h2>📈 실시간 데이터 트렌드</h2>
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line 
                type="monotone" 
                dataKey="battery" 
                stroke="#e74c3c" 
                name="배터리 (%)"
                strokeWidth={2}
              />
              <Line 
                type="monotone" 
                dataKey="accel_magnitude" 
                stroke="#3498db" 
                name="가속도 크기 (m/s²)"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 데이터가 없을 때 */}
      {!robotData.lastUpdate && (
        <div style={{ 
          textAlign: 'center', 
          padding: '40px',
          background: '#f8f9fa',
          borderRadius: '8px'
        }}>
          <h3>🔄 로봇 데이터를 기다리는 중...</h3>
          <p>실제 로봇 토픽에서 데이터를 수신 대기 중입니다.</p>
          <div style={{ fontSize: '14px', color: '#666' }}>
            예상 토픽: robot1/battery_state, robot1/imu, robot1/odom, robot1/wheel_status
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
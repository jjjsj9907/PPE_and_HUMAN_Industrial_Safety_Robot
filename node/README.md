# buzzer_alert.py

## package.xml

package.xml에 아래의 코드를 추가해주세요:

```python
<exec_depend>rclpy</exec_depend>
<exec_depend>irobot_create_msgs</exec_depend>
<exec_depend>builtin_interfaces</exec_depend>
```

## terminal

터미널에서 네임스페이스에 맞춰 아래의 코드로 실행해주세요:

```bash
ros2 run your_pakage buzzer_alert --ros-args -r __ns:=/robot1
```

# mqtt_logger.py

## terminal

터미널에서 실행 권한을 주고 실행하세요:

```bash
chmod +x mqtt_logger.py
./mqtt_logger.py
```

여러 파일 동시 팔로우:
```bash
sudo apt install multitail
multitail /home/okj1812/logs/*.log
```

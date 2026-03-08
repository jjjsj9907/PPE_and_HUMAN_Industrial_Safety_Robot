# ROKEY_D_1

## Node flow chart

![flowchart](https://github.com/user-attachments/assets/efcf3d52-5cde-49ba-be48-832183f166e9)

---

### Robot1

#### Human YOLO + Depth -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/yolo_depth/human_detection` | `your_ros_pkg/msg/PersonDetection`| `x_m`        | `float64`       | m   | 맵 좌표 x              |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y   |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                    |


#### Puddle Seg -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/yolo_depth/puddle_detection`| `your_ros_pkg/msg/CPDetection`| `x_m`        | `float64`       | m   | 맵 좌표 x          |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y |
|                                      |                              | `area_cm2`   | `float64`       | cm² | 크랙의 면적                 |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                  |

#### Crack -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/yolo_depth/crack_detection` | `your_ros_pkg/msg/CPDetection`| `x_m`        | `float64`       | m   |  맵 좌표 x           |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y |
|                                      |                              | `area_cm2`   | `float64`       | cm² | 크랙의 면적                  |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                  |


#### TF + Nav -> Buzzer

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/arrival`                    | `your_ros_pkg/msg/Arrival`   | `alert_message`        | `string`       |    | 도착 알림          |


#### TF + Nav -> Maanager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/state`                    | `your_ros_pkg/msg/State`   | `event`        | `string`       |    | 이벤트 알림          |


#### Manage COM -> TF + Nav

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/manager_comand`             | `your_ros_pkg/msg/ManagerCommand`    | `command`      | `string`|    | 관리자 운전 정지/재개 명령    |



#### robot1/TF + Nav -> robot3/TF + Nav

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot1/mapping`                    | `your_ros_pkg/msg/GlobalMapping`| `mapping`      | `string`|    |  글로벌 매핑 명령    |


---

### Robot3

#### Human YOLO + Depth -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/yolo_depth/human_detection` | `your_ros_pkg/msg/PersonDetection`| `x_m`        | `float64`       | m   | 맵 좌표 x              |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y   |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                    |


#### Puddle Seg -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/yolo_depth/puddle_detection`| `your_ros_pkg/msg/CPDetection`| `x_m`        | `float64`       | m   | 맵 좌표 x          |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y |
|                                      |                              | `area_cm2`   | `float64`       | cm² | 크랙의 면적                 |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                  |

#### Crack -> TF + Nav, Manager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/yolo_depth/crack_detection` | `your_ros_pkg/msg/CPDetection`| `x_m`        | `float64`       | m   |  맵 좌표 x           |
|                                      |                              | `y_m`        | `float64`       | m   | 맵 좌표 y |
|                                      |                              | `area_cm2`   | `float64`       | cm² | 크랙의 면적                  |
|                                      |                              | `class_name` | `string`        |     | 클래스 라벨                  |


#### TF + Nav -> Buzzer

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/arrival`                    | `your_ros_pkg/msg/Arrival`   | `alert_message`        | `string`       |    | 도착 알림          |

#### TF + Nav -> Maanager COM

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/state`                    | `your_ros_pkg/msg/State`   | `event`        | `string`       |    | 이벤트 알림          |


#### Manage COM -> TF + Nav

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/manager_comand`             | `your_ros_pkg/msg/ManagerCommand`    | `command`      | `string`|    | 관리자 운전 정지/재개 명령    |



#### robot1/TF + Nav -> robot3/TF + Nav

  | 토픽 이름                                | 메시지 타입                       | 필드 이름        | 타입              | 단위  | 설명                      |
| ------------------------------------ | ---------------------------- | ------------ | --------------- | --- | ----------------------- |
| `/robot3/mapping`                    | `your_ros_pkg/msg/GlobalMapping`| `mapping`      | `string`|    |  글로벌 매핑 명령    |

# PersonDetection.msg, PPEViolation.msg, RoleAssignment.msg

## **directory**
```
  ros2_ws/
  └─ src/
     └─ your_ros_pkg/
        ├── package.xml
        ├── setup.py
        ├── resource/
        │   └── your_ros_pkg
        ├── your_ros_pkg/
        │   ├── __init__.py
        │   └── msg/
        │       ├── PersonDetection.msg
        │       ├── PPEViolation.msg
        │       └── RoleAssignment.msg
        └── setup.cfg
```        

## **package.xml**

package.xml에 아래 코드를 추가해주세요.

```python
<build_depend>std_msgs</build_depend>
<build_depend>geometry_msgs</build_depend>
<exec_depend>std_msgs</exec_depend>
<exec_depend>geometry_msgs</exec_depend>
```

## **node**

메세지를 사용하는 노드에 아래 코드를 추가해주세요.

```python
from your_ros_pkg.msg import MsgName
```

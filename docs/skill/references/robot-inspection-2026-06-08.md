# 天工机器人状态巡检记录

## 目录

- [总体结论](#总体结论)
- [主机与网络](#主机与网络)
- [ROS 2 状态](#ros-2-状态)
- [VLA 相关话题](#vla-相关话题)
- [相机与 USB 硬件](#相机与-usb-硬件)
- [计算资源](#计算资源)
- [巡检注意事项](#巡检注意事项)

巡检时间：2026-06-08 15:03-15:15 CST  
巡检方式：通过 `ssh tienkung` 登录上位机，再从上位机只读查询 `n1`、`n2`、`n3`。本次未在机器人端写文件、未修改配置、未启动或停止任何服务。

## 总体结论

- 上位机 `ubuntu-collect` 可连通，主要作为跳板/采集机；本机没有默认可用的 ROS 命令。
- `n1` 是主要 ROS 2 控制节点，运行 ROS 2 Humble，`bodyctrl`、`rl_control`、`usb_sbus`、`power_board_node` 等节点在线。
- `n2` 是 Jetson AGX 计算单元，接入 1 台 Orbbec Gemini 336 深度相机，另有 USB 声卡；ROS 2 工作区主要是 Orbbec 相机相关目录。
- `n3` 是 Jetson AGX 计算单元，接入 2 台 Intel RealSense D405，序列号为 `353322271022`、`230322275908`，固件版本均为 `5.17.0.10`。
- 当前 ROS 2 话题列表中能看到 `/camera/color/image_raw/compressed` 和 `/camera/depth/image_raw`，但巡检时这两个话题只有订阅者，没有 publisher，因此当前没有实际图像流频率。
- VLA 可优先关注：手部状态、手部控制、IMU、关节/电机状态、SBUS 遥控、机器人速度控制、相机硬件接入情况。相机数据流需要后续确认对应驱动是否启动。

## 主机与网络

| 名称 | 主机名 | 用户 | 系统 | 地址/接口 |
| --- | --- | --- | --- | --- |
| `tienkung` | `ubuntu-collect` | `ubuntu` | Ubuntu 22.04, kernel `6.8.0-124-generic`, x86_64 | `wlp67s0=172.19.2.97/22`, `eno0=192.168.41.5/24` |
| `n1` | `ubuntu` | `ubuntu` | Ubuntu 22.04, kernel `6.8.0-52-generic`, x86_64 | `enp3s0=192.168.41.1/24, 192.168.11.11/24`; `enp4s0` up |
| `n2` | `nvidia-desktop` | `nvidia` | Jetson Linux R36.4, kernel `5.15.148-tegra`, aarch64 | `eth0=192.168.41.2/24`, `enp1s0=10.42.0.1/24`; `can0/can1` down |
| `n3` | `nvidia-desktop` | `nvidia` | Jetson Linux R36.4, kernel `5.15.148-tegra`, aarch64 | `eth0=192.168.41.3/24`; `can0/can1` down |

3 秒瞬时网络速率快照：

| 主机 | 接口 | 接收 | 发送 |
| --- | --- | --- | --- |
| `tienkung` | `eno0` | 1,457,734 B/3s | 645,962 B/3s |
| `tienkung` | `wlp67s0` | 117,558 B/3s | 47,522 B/3s |
| `n1` | `enp3s0` | 549,192 B/3s | 1,360,092 B/3s |
| `n1` | `enp4s0` | 1,512,534 B/3s | 1,511,439 B/3s |
| `n2` | `eth0` | 640,358 B/3s | 353,684 B/3s |
| `n3` | `eth0` | 165,684 B/3s | 118,988 B/3s |

## ROS 2 状态

巡检当时 ROS 2 需要显式 source；2026-06-10 已将上位机 `ubuntu` 用户的 `~/.bashrc` 调整为自动 source `/opt/ros/humble/setup.bash`，但 `n1` 仍建议按本机环境显式 source：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2ws/install/setup.bash
```

`n1` 上 ROS 环境：

- `ROS_DISTRO=humble`
- `ROS_VERSION=2`
- `ROS_LOCALHOST_ONLY=0`

主要在线节点：

- `/bodyctrl`
- `/rl_control`
- `/usb_sbus`
- `/power_board_node`
- `/record_bag_node`
- `/proc_manager_node`
- `/diagnose_tiangong2_upgrade_node`
- `/xrocs_shared_ros2_node_e4756e`
- `/audio_*`
- `/cloud_service`
- `/OTA`

## VLA 相关话题

### 感知与相机

| 话题 | 类型 | 巡检状态 |
| --- | --- | --- |
| `/camera/color/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | 只有订阅者 `/xrocs_shared_ros2_node_e4756e`，publisher count 为 0，未测到频率 |
| `/camera/depth/image_raw` | `sensor_msgs/msg/Image` | 只有订阅者 `/xrocs_shared_ros2_node_e4756e`，publisher count 为 0，未测到频率 |
| `/imu` | `sensor_msgs/msg/Imu` | `bodyctrl` 发布，约 497 Hz，约 147-159 KB/s |

### 手部与关节

| 话题 | 类型 | 发布者 | 频率/带宽 |
| --- | --- | --- | --- |
| `/inspire_hand/state/left_hand` | `sensor_msgs/msg/JointState` | `bodyctrl` | 约 24.7 Hz，约 6.25 KB/s |
| `/inspire_hand/state/right_hand` | `sensor_msgs/msg/JointState` | `bodyctrl` | 约 24.7 Hz，约 6.25 KB/s |
| `/inspire_hand/ctrl/left_hand` | `sensor_msgs/msg/JointState` | 控制输入话题 | 未测到发布频率 |
| `/inspire_hand/ctrl/right_hand` | `sensor_msgs/msg/JointState` | 控制输入话题 | 未测到发布频率 |
| `/encoder_identical_joint` | `sensor_msgs/msg/JointState` | 当前 publisher count 为 0 | 未测到频率 |
| `/encoder_identical_button` | `sensor_msgs/msg/JointState` | 当前 publisher count 为 0 | 未测到频率 |
| `/joint_states_flex_freq` | `sensor_msgs/msg/JointState` | `/xrocs_shared_ros2_node_e4756e` | topic info 有 publisher，巡检窗口未稳定测出 hz |

### 机器人状态与控制

| 话题 | 类型 | 发布者/用途 | 频率/带宽 |
| --- | --- | --- | --- |
| `/arm/status` | `bodyctrl_msgs/msg/MotorStatusMsg` | `bodyctrl` 发布 | 约 497 Hz，约 180 KB/s |
| `/leg/status` | `bodyctrl_msgs/msg/MotorStatusMsg` | `bodyctrl` 发布 | 约 998-1000 Hz，约 313 KB/s |
| `/head/status` | `bodyctrl_msgs/msg/MotorStatusMsg` | `bodyctrl` 发布 | 约 400 Hz，约 40 KB/s |
| `/waist/status` | `bodyctrl_msgs/msg/MotorStatusMsg` | `bodyctrl` 发布 | 约 400 Hz，约 20.8 KB/s |
| `/sbus_data` | `sensor_msgs/msg/Joy` | `usb_sbus` 发布 | 约 43.37 Hz，约 3.3 KB/s |
| `/power/battery/status` | `bodyctrl_msgs/msg/PowerBatteryStatus` | `power_board_node` 发布 | 约 1 Hz，约 75-103 B/s |
| `/hric/robot/cmd_vel` | `geometry_msgs/msg/TwistStamped` | 速度控制输入；`rl_control`、`record_bag_node` 订阅 | 当前 publisher count 为 0 |

其他与控制相关的命令话题包括：

- `/arm/cmd_ctrl`、`/arm/cmd_pos`、`/arm/cmd_vel`、`/arm/cmd_imp_ctrl`
- `/leg/cmd_ctrl`、`/leg/cmd_pos`、`/leg/cmd_vel`
- `/head/cmd_ctrl`、`/head/cmd_pos`、`/head/cmd_vel`
- `/waist/cmd_ctrl`、`/waist/cmd_pos`、`/waist/cmd_vel`
- `/hric/robot/float_base_rpyz_cmd`
- `/hric/robot/set_vel_limit`

## 相机与 USB 硬件

### 上位机 `tienkung`

- USB：内置 Chicony 摄像头、CANalyst-II、Realtek 蓝牙。
- 视频设备：`/dev/video0`、`/dev/video1`、`/dev/media0`。
- `/dev/video0`：Integrated Camera，默认 `1280x720 MJPG 30 FPS`。
- RealSense 工具可用，但未检测到 RealSense 设备。

### `n1`

- USB：3 个 CANalyst-II、1 个 CH340 串口转换器、Intel AX210 蓝牙。
- 未发现视频设备。
- 未安装/未暴露 RealSense 工具。
- 主要角色更像机器人控制/遥控/状态节点。

### `n2`

- USB 相机：Orbbec Gemini 336，USB 3.0 5000M。
- USB 声卡：C-Media Audio Adapter。
- 视频设备：`/dev/video8` 到 `/dev/video15`，`/dev/media1`、`/dev/media2`。
- ROS 工作区线索：
  - `/home/nvidia/OrbbecCamera-Orin_ros2_tg2.0-plus_v2.0.2_20250717_222400/install/setup.bash`
  - `/home/nvidia/orbbec_camera_ros2.bk.20251227_193207/install/setup.bash`
- 当前未看到 Orbbec camera ROS publisher 出现在在线节点里。

### `n3`

- USB 相机：2 台 Intel RealSense D405，USB 3.0 5000M。
- 序列号：
  - `353322271022`
  - `230322275908`
- 固件版本：`5.17.0.10`
- 视频设备：`/dev/video0` 到 `/dev/video11`，`/dev/media1`、`/dev/media2`。
- ROS 工作区线索：
  - `/home/nvidia/d405_ws/install/setup.bash`
  - `/home/nvidia/librealsense/install/setup.bash`
  - `/home/nvidia/OrbbecCamera-Orin_ros2_tg2.0-plus_v2.0.2_20250717_222400/install/setup.bash`
- 当前未看到 D405 对应的 ROS camera publisher 出现在在线节点里。

## 计算资源

| 主机 | CPU/平台 | 内存 | 磁盘 |
| --- | --- | --- | --- |
| `tienkung` | Intel Core Ultra 5 225H，14 CPU | 30 GiB，总体空闲约 21 GiB | `/` 938G，已用 64G |
| `n1` | Intel Core i7-1355U，12 CPU | 15 GiB，总体空闲约 10 GiB | `/` 228G，已用 132G |
| `n2` | Jetson aarch64 Cortex-A78AE，12 CPU，当前 0-7 在线 | 61 GiB，总体空闲约 58 GiB | `/` 57G 已用 40G；`/data` 469G 基本空 |
| `n3` | Jetson aarch64 Cortex-A78AE，12 CPU，当前 0-7 在线 | 61 GiB，总体空闲约 59 GiB | `/` 57G 已用 26G |

Jetson 状态：

- `n2`：`NV Power Mode: MODE_30W`，巡检时 CPU 低负载，GPU `GR3D_FREQ 0%`，温度约 48-49 C。
- `n3`：`NV Power Mode: MODE_30W`，巡检时 CPU 低负载，GPU `GR3D_FREQ 0%`，温度约 51-52 C。

## 巡检注意事项

- `n2`、`n3` 的主机名都显示为 `nvidia-desktop`，记录时需要按 SSH alias 和 IP 区分。
- 文档原始预期提到“一个 AGX 两个 D405，另一个 AGX 一个 L355”。实际巡检结果是：`n3` 有两个 D405；`n2` 检测到的是 Orbbec Gemini 336，没有检测到 L355。
- 相机硬件均在 USB 层可见，但 ROS 图像 topic 当前没有 publisher。后续若要采 VLA 图像数据，需要确认相机驱动 launch 是否应当启动，以及命名空间是否应该是 `/camera/...` 或独立相机名。
- `record_bag_node` 已在线并订阅部分状态话题，说明系统内已有录包触发/磁盘管理相关节点，但本次没有触发录制。

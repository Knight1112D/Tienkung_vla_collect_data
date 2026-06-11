---
name: tienkung-remote-control
description: Remote inspection, SSH operation, ROS 2 diagnostics, and VLA data-collection project guidance for the Tienkung 2.0 PRO robot. Use when Codex needs to work with the tienkung SSH jump host, n1/n2/n3 robot computers, camera startup, ROS topics, robot state inspection, or the cbc_tienkung2.0_vla_collect_data collection workflow.
---

# 天工远程控制与数据采集

## 工作原则

- 默认先只读巡检，再提出或执行修改；涉及机器人运动、服务启停、写入远端文件、删除数据、长时间采集时，先明确风险和操作范围。
- 所有机器人端操作优先通过 `ssh tienkung` 登录上位机，再从上位机访问 `n1`、`n2`、`n3`。
- 区分主机角色：上位机负责跳板和采集落盘；`n1` 负责 ROS 2 控制；`n2` 和 `n3` 是 Jetson AGX 计算单元与相机主机。
- 上位机 `ubuntu` 用户的 `~/.bashrc` 已在交互判断前自动 source `/opt/ros/humble/setup.bash` 和 `/home/ubuntu/data/param/ros2_setup.bash`；通常不需要再手动 source ROS 2 系统环境。
- 处理 Python 项目时使用 `uv`，虚拟环境放在当前项目 `.venv`；安装包使用 `uv pip install -i https://mirrors.aliyun.com/pypi/simple/ ...`。
- 新增代码注释、脚本文档、提交日志使用中文。

## 参考资料

- 读取 `references/collect-data-requirements.md`：了解 VLA 数采目标、期望工程名、相机与 command/state 对齐要求、目标脚本名和参考项目路径。
- 读取 `references/robot-inspection-2026-06-08.md`：了解已巡检到的主机、网络、ROS 2、话题频率、相机硬件和磁盘资源。
- 读取 `references/vla-session-state-2026-06-10.md`：了解当前 VLA 采集工程的实际启动方式、默认话题、上传脚本和最新约束。

## 常用流程

### 远程巡检

1. 通过 `ssh tienkung` 登录上位机。
2. 只读确认主机和网络状态：`hostname`、`ip addr`、`df -h`、`free -h`、`uptime`。
3. 从上位机分别访问 `n1`、`n2`、`n3`，不要混淆两个 Jetson 的相同主机名 `nvidia-desktop`。
4. 上位机默认已自动 source ROS 2 环境；访问 `n1` 后仍按 `n1` 本机环境显式 source：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2ws/install/setup.bash
```

5. 使用 `ros2 node list`、`ros2 topic list`、`ros2 topic info`、`ros2 topic hz`、`ros2 topic bw` 收集状态；记录命令、时间窗口和结果。

### 数据采集项目开发

1. 目标工程名为 `cbc_tienkung2.0_vla_collect_data`，上位机路径为 `/home/ubuntu/cbc_tienkung2.0_vla_collect_data`。
2. 当前工程入口按用途拆分：`scripts/dual_hands_collect.py` 用于双手采集，`scripts/gripper_vla_collect.py` 用于后续加爪/夹爪采集；不要恢复单独的 `cbc_tienkung2.0_vla_dual_hands_collect_data.py`。
3. 参考旧稳定项目：`/home/nvidia/njd/vla/remote_control/collect_data.py` 和 `/home/nvidia/njd/vla/remote_control/vla_recorded_data`。当前任务是在旧稳定链路基础上做工程化封装，不重新设计底层相机驱动。
4. 一键启动入口是 `scripts/start_vla_nodes.sh`。它默认启动全部相机并让机器人低头；如果只启动相机、不执行动作，使用 `bash scripts/start_vla_nodes.sh --no-move-head`。
5. `launch/vla_camera_nodes.launch.py` 只负责托管旧稳定启动脚本：`n3` 执行 `/home/nvidia/njd/env_init.sh`，`n2` 执行 `/home/nvidia/njd/button/tool/start_camera.sh`，`n1` 根据 `move_head` 参数发布一次低头命令。不要再把它改回直接启动低层 D405 raw 节点。
6. 当前默认图像话题必须沿用旧稳定话题：头部 `/camera/color/image_raw/compressed`，左手 `/camera/d405_left/color/image_h264`，右手 `/camera/d405_right/color/image_h264`。
7. D405 启动脚本应显式关闭深度、红外、IMU、点云、TF 和 diagnostics；`extrinsics/depth_to_color` 是外参标定话题，不是深度图像流，通常不构成带宽瓶颈。
8. 采集目标频率为 `20Hz`，但实际写入频率由三路图像和必需 state 的真实更新决定；有新数据才写样本，不用旧数据凑频率。
9. 采集器必须避免复用：开始录制时丢弃录制前缓存；每条样本写入后标记已使用的图像和状态 seq；下一条样本必须拿到新的关键图像和新的必需状态流，否则跳过。
10. command/state 频率明显高于相机频率时，以图像帧时间为锚点选取最近状态，但同一条状态不能重复写入多个样本。
11. 图像优先让相机驱动或旧稳定转换链路直接输出训练可用 RGB；如果不能直接输出 `224x224`，采集脚本不要在录制时 resize，直接保存相机输出并记录元数据。
12. 每条样本记录各数据源原始时间戳和相对锚点时间差，便于后处理筛选。

### 相机与话题检查

- `n2`：重点检查 Orbbec Gemini 336 与其 ROS 2 工作区。
- `n3`：重点检查两台 Intel RealSense D405，序列号见巡检参考文档。
- 启动相机优先使用 `bash scripts/start_vla_nodes.sh`，确认安全后默认会低头；调试时可使用 `--no-move-head`。
- 启动相机前后都检查 publisher 是否出现，尤其是 `/camera/color/image_raw/compressed`、`/camera/d405_left/color/image_h264`、`/camera/d405_right/color/image_h264`。
- 调频或压测时逐步提高频率，记录稳定窗口内的 `ros2 topic hz`、CPU、内存、网络和丢帧现象。

常用健康检查：

```bash
ros2 topic info /camera/color/image_raw/compressed
ros2 topic info /camera/d405_left/color/image_h264
ros2 topic info /camera/d405_right/color/image_h264
ros2 topic hz /camera/color/image_raw/compressed --window 30
ros2 topic hz /camera/d405_left/color/image_h264 --window 30
ros2 topic hz /camera/d405_right/color/image_h264 --window 30
ros2 topic hz /arm/status --window 100
ros2 topic hz /inspire_hand/state/left_hand --window 50
ros2 topic hz /inspire_hand/state/right_hand --window 50
```

## 输出要求

- 给用户的巡检结论使用中文，包含具体主机、命令、观察结果和下一步建议。
- 修改脚本或项目结构后，说明文件路径、运行方式和已验证命令。
- 对可能引发机器人动作的命令，明确写出是否已执行；未执行时给出可复制命令和安全检查点。

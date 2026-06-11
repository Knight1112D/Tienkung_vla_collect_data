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
- 读取 `references/vla-session-state-2026-06-10.md`：了解当前 VLA 采集工程的实际启动方式、默认话题和历史约束；其中 n3 上传脚本相关内容已过时。最终稳定流程是上位机启动节点，n2 本地 tmpfs 采集，再上传回上位机。

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

1. 目标工程名为 `cbc_tienkung2.0_vla_collect_data`，上位机路径为 `/home/ubuntu/cbc_tienkung2.0_vla_collect_data`；n2 持久路径为 `/home/nvidia/cbc_tienkung2.0_vla_collect_data`。
2. 当前工程入口按用途拆分：`scripts/dual_hands_collect.py` 用于双手采集，`scripts/gripper_vla_collect.py` 用于后续加爪/夹爪采集；不要恢复单独的 `cbc_tienkung2.0_vla_dual_hands_collect_data.py`。
3. 参考旧稳定项目：`/home/nvidia/njd/vla/remote_control/collect_data.py` 和 `/home/nvidia/njd/vla/remote_control/vla_recorded_data`。当前任务是在旧稳定链路基础上做工程化封装，不重新设计底层相机驱动。
4. 一键启动入口是 `scripts/start_vla_nodes.sh`。它默认启动全部相机并让机器人低头；如果只启动相机、不执行动作，使用 `bash scripts/start_vla_nodes.sh --no-move-head`。
5. 采集前可运行 `python3 scripts/view_vla_cameras.py` 查看三路画面；无图形界面时用 `python3 scripts/view_vla_cameras.py --save-preview /tmp/vla_preview.jpg` 保存三路拼图。
6. `launch/vla_camera_nodes.launch.py` 只负责托管旧稳定启动脚本：`n3` 执行 `/home/nvidia/njd/env_init.sh`，`n2` 执行 `/home/nvidia/njd/button/tool/start_camera.sh`，`n1` 根据 `move_head` 参数发布一次低头命令。不要再把它改回直接启动低层 D405 raw 节点。
7. 当前默认图像话题必须沿用旧稳定话题：头部 `/camera/color/image_raw/compressed`，左手 `/camera/d405_left/color/image_h264`，右手 `/camera/d405_right/color/image_h264`。
8. D405 启动脚本应显式关闭深度、红外、IMU、点云、TF 和 diagnostics；`extrinsics/depth_to_color` 是外参标定话题，不是深度图像流，通常不构成带宽瓶颈。
9. 采集目标频率为固定 `20Hz`。各话题回调只维护最新缓存，新图像或新状态到来就替换旧缓存；图像订阅使用 depth=1 best-effort，回调只缓存最新原始图像，PNG 解码和写盘放在保存线程中，避免旧图像在 ROS 队列里堆积；录制线程每 50ms 保存当前快照，允许复用上一帧图像和状态以保持固定训练频率。
10. 终端输入 `1` 后，如果必需数据流尚未就绪，采集器会进入自动等待；等三路图像、机械臂 command/state 和左右手 state 都到齐后自动开始录制。缺 `head`、`hand_left`、`hand_right` 并超过宽限时间时会低频调用 `scripts/recover_vla_streams.sh` 自动恢复相机流；输入 `2` 可以取消等待或停止并保存当前录制。
11. 采集输出必须贴旧项目格式：每组目录只有 `head/`、`hand_left/`、`hand_right/` 三路 PNG 序列和一个 `arm.npz`。不要再写 `samples.jsonl`、`summary.json`、`config.json` 或逐帧 `state_npz/`。
12. `arm.npz` 至少保存机械臂 `cmd_positions`、`status_positions`、关节 id、左右手 state；左右手 command 也订阅并保存，如果当前话题不发布新消息，则保存为空数组，不伪造 command。
13. 图像保存必须参考旧 VLA 实现：解码后直接保存 PNG，默认保持相机输出尺寸，不在采集脚本里 resize。相机启动阶段可以降低分辨率以减少带宽和磁盘；当前头部 Orbbec 为 `640x480x30`，左右 D405 为 `424x240x30`。
14. 各主机时钟可能不同步，不要依赖跨主机 ROS stamp 做强对齐；如需检查复用和新鲜度，使用采集器写入的接收时间和图像 seq。
15. 稳定采集优先使用 n2 tmpfs 方案：上位机先运行 `bash scripts/start_vla_nodes.sh --no-move-head` 启动相机和头部状态；n2 项目持久目录为 `/home/nvidia/cbc_tienkung2.0_vla_collect_data`，运行 `bash scripts/n2_dual_hands_collect.sh --target-hz 20` 采集；数据默认写入 `/dev/shm/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands`，采完运行 `bash scripts/upload_n2_recorded_data.sh` 上传到上位机 `dual_hands/` 并删除 n2 本地数据。
16. `assets/` 目录保存天工 2.0 PRO 搭配因时 6 自由度灵巧手使用的 D405 手部相机支架资料，包括安装参考图、D405 USB 连接示意和 STL 模型；安装后确认两颗 M3 螺丝、运动包络和线缆余量。

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

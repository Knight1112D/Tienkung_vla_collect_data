# 天工 VLA 数据采集工程

本工程在上位机运行，负责按固定频率采集三路 RGB 图像、机械臂 command/state、灵巧手 command/state，并保存为旧项目兼容的数据结构。

## 最简单使用说明

默认采集在上位机运行，数据会直接保存到上位机，不需要再传输。

1. 启动相机节点：

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

如果机器人还没有低头，并且确认周围安全，可以去掉 `--no-move-head`。

如果 D405 经常报找不到 USB 设备，先按下面的“D405 USB 恢复”处理。

2. 采集前查看三路摄像头画面：

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
python3 scripts/view_vla_cameras.py
```

如果当前终端没有图形界面，可以保存一张预览图：

```bash
python3 scripts/view_vla_cameras.py --save-preview /tmp/vla_preview.jpg
```

3. 开始采集：

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
python3 scripts/dual_hands_collect.py --target-hz 20
```

进入采集程序后输入：

- `1`：开始录制
- `2`：停止录制并保存本组数据
- `3`：删除上一组数据
- `q`：退出脚本

数据默认保存到：

```text
/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands
```

4. 当前默认流程是在上位机采集并直接落盘，不再需要从 n3 上传数据。

## D405 USB 恢复

n3 上的 D405 偶尔会出现 `No RealSense devices were found`、`rs-enumerate-devices` 无设备、或者 `lsusb` 有设备但相机节点仍找不到设备的情况。优先使用下面的软件重置流程，不需要机器人动作。

1. 在上位机停止当前 VLA 节点：

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
tmux kill-session -t vla_camera_launch 2>/dev/null || true
```

2. 重绑 n3 的 USB 主控：

```bash
ssh n3
printf 'nvidia\n' | sudo -S bash -lc '
cd /sys/bus/platform/drivers/tegra-xusb
echo 3610000.usb > unbind
sleep 3
echo 3610000.usb > bind
sleep 8
lsusb
rs-enumerate-devices 2>/dev/null | grep -E "Name|Serial Number|Physical Port" || true
'
```

正常应能看到两台 `Intel RealSense D405`，序列号为：

- `353322271022`
- `230322275908`

3. 重新启动节点：

```bash
exit
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

4. 确认三路相机画面：

```bash
python3 scripts/view_vla_cameras.py --save-preview /tmp/vla_preview.jpg
```

如果重绑后 `lsusb` 仍看不到两台 D405，需要现场重新插拔或重新给 D405 上电。

## 目录结构

- `cbc_tienkung_vla/collector.py`：公共采集器，维护各话题最新缓存，按固定 20Hz 保存快照；不作为命令行主入口。
- `scripts/dual_hands_collect.py`：双手采集程序，内部有独立 `main()`，直接运行这个文件。
- `scripts/gripper_vla_collect.py`：加爪/夹爪采集程序模板，内部有独立 `main()`，后续确认爪子话题后直接运行这个文件。
- `scripts/view_vla_cameras.py`：三路相机预览脚本，用于采集前确认视角。
- `launch/vla_camera_nodes.launch.py`：推荐的一键启动入口，用独立进程启动每个远端相机节点。
- `scripts/start_vla_nodes.sh`：兼容包装，内部调用 `launch/vla_camera_nodes.launch.py`。
- `scripts/stop_vla_nodes.sh`：停止相机节点，便于重新启动。
- `configs/`：运行参数示例。
- `docs/skill/`：同步的 skill 文档和巡检参考资料。

## 推荐流程

1. 确认机器人已进入安全的 VLA 初始状态。
2. 使用 `bash scripts/start_vla_nodes.sh` 启动全部相机并默认低头；如果头已经低下去了，使用 `bash scripts/start_vla_nodes.sh --no-move-head`。
3. 检查图像、机械臂和灵巧手话题 publisher 与频率。
4. 运行对应采集程序，终端输入 `1` 开始、`2` 停止、`3` 删除上一组、`q` 退出。
5. 查看每组三路 PNG 数量和 `arm.npz` 数组形状，确认图像、机械臂和手部状态已保存。

## 双手采集

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
python3 scripts/dual_hands_collect.py
```

上位机已默认自动加载 `/opt/ros/humble/setup.bash`。如果换到其他主机运行，需要先 source 对应 ROS 2 环境。

常用参数：

```bash
python3 scripts/dual_hands_collect.py \
  --target-hz 20
```

当前默认图像输入为：

- 头部：`/camera/color/image_raw/compressed`，`sensor_msgs/msg/CompressedImage`
- 左手：`/camera/d405_left/color/image_h264`，`foxglove_msgs/msg/CompressedVideo`
- 右手：`/camera/d405_right/color/image_h264`，`foxglove_msgs/msg/CompressedVideo`

D405 默认沿用旧项目中已经稳定验证过的 h264 图像话题。采集器按 `20Hz` 固定保存当前最新缓存；新图像到来会替换缓存，没有新图像时允许复用上一帧，以保持固定训练采样频率。图像订阅使用 depth=1 best-effort，回调只缓存最新原始图像，PNG 解码和写盘放在保存线程中，避免旧图像在 ROS 队列里堆积。默认保存 PNG 保持相机输出尺寸，不做 resize；如需临时缩放可显式传 `--output-image-size 224`。

## 加爪/夹爪采集

当前固定格式采集器主要面向双手采集。加爪/夹爪采集需要先确认爪子消息类型，再在 `cbc_tienkung_vla/collector.py` 中新增对应最新缓存和 `arm.npz` 字段。

## 数据格式

每次录制会先按采集类型分目录，再生成递增编号目录：

```text
vla_recorded_data/
  dual_hands/
    0000/
      head/
      hand_left/
      hand_right/
      arm.npz
  gripper/
    0000/
      head/
      hand_left/
      hand_right/
      arm.npz
```

其中 `scripts/dual_hands_collect.py` 默认写入 `dual_hands/`，`scripts/gripper_vla_collect.py` 默认写入 `gripper/`。也可以用 `--output-dir` 显式覆盖。编号从当前目录下最大数字目录继续递增；空目录第一次采集会生成 `0000`，之后依次为 `0001`、`0002`。

GitHub 仓库只保留一组完整样例数据用于检查格式，当前样例为 `vla_recorded_data/dual_hands/0000`。上位机本地可以保留完整采集序列，例如 `0000` 到 `0010`。

每组编号目录内部结构：

- `head/`、`hand_left/`、`hand_right/`：三路 PNG 序列，文件名为 `000000.png` 递增。
- `arm.npz`：逐帧状态和命令数组。

`arm.npz` 主要字段：

- `cmd_positions`：机械臂 command，形状通常为 `(N, 14)`。
- `status_positions`：机械臂 state position，形状通常为 `(N, 14)`；不保存 speed/current/temperature/error。
- `left_hand_state_positions`、`right_hand_state_positions`：左右手 state，形状通常为 `(N, 6)`。
- `left_hand_cmd_positions`、`right_hand_cmd_positions`：左右手 command；如果当前控制话题不发布新消息，会保存为空形状 `(N, 0)`，不伪造数据。
- `*_image_seq`、`*_image_recv_sec`、`*_image_stamp_sec`：每帧复用的最新图像序号和时间信息，用于后处理检查复用情况。

采集目录不再写 `samples.jsonl`、`summary.json`、`config.json` 或 `state_npz/`，以兼容旧项目格式。

## 一键启动相机节点

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh
```

该脚本会：

- 在 `n3` 执行旧项目稳定使用的 `/home/nvidia/njd/env_init.sh`，由它启动左右 D405 和原有转换进程。
- 在 `n2` 执行旧项目稳定使用的 `/home/nvidia/njd/button/tool/start_camera.sh` 启动头部 Orbbec。
- 保持原有发布话题：头部 compressed RGB、左右手 h264 RGB。
- 当前相机启动已降分辨率：头部 Orbbec 为 `640x480x30`，左右 D405 为 `424x240x30`；采集器默认按相机输出尺寸保存 PNG。
- D405 启动脚本显式关闭深度、红外、IMU、点云、TF 和 diagnostics；`extrinsics/depth_to_color` 属于外参标定话题，不是深度图像流。
- 默认在 `n1` 发布一次低头命令，方便 VLA 采集视角。

这个 launch 只负责把之前“多个终端分别挂相机节点”的稳定流程纳入一个入口，方便启动和停止；不在这里重写相机驱动参数。

如果只想启动相机、不让机器人动作：

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

也可以直接使用 launch：

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
ros2 launch launch/vla_camera_nodes.launch.py move_head:=true
```

低头命令会在 `n1` 发布 `/head/cmd_pos`，属于机器人动作；只有确认周边安全、急停可用、机器人姿态允许时才使用。

需要重新启动相机节点时：

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
bash scripts/start_vla_nodes.sh
```

## 健康检查命令

```bash
ros2 topic list | grep -E 'camera|arm|inspire_hand'
ros2 topic info /camera/color/image_raw/compressed
ros2 topic info /camera/d405_left/color/image_h264
ros2 topic info /camera/d405_right/color/image_h264
ros2 topic hz /camera/color/image_raw/compressed --window 30
ros2 topic hz /camera/d405_left/color/image_h264 --window 30
ros2 topic hz /camera/d405_right/color/image_h264 --window 30
ros2 topic hz /arm/cmd_ctrl --window 30
ros2 topic hz /arm/status --window 100
ros2 topic hz /inspire_hand/state/left_hand --window 50
ros2 topic hz /inspire_hand/state/right_hand --window 50
```

合理采集频率以实测为准：三路相机、机械臂 command/state 和灵巧手 state 都有缓存后即可开始录制；录制期间按固定 20Hz 保存最新快照。

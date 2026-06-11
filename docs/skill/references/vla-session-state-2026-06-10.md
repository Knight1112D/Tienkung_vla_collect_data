# VLA 采集当前状态记录 2026-06-10

更新时间：2026-06-10 16:50 CST  
目标工程：`/home/ubuntu/cbc_tienkung2.0_vla_collect_data`

## 交接结论

下一轮新对话先读本文件，再读 `SKILL.md`。当前对话历史里有旧 raw D405 方案、错误 launch 残留和多次中间实验，不能再直接沿用历史上下文。

当前正确方向：

- 沿用旧项目稳定相机链路，不再直接改成上位机订阅 D405 raw 方案。
- 一键入口为 `bash scripts/start_vla_nodes.sh`，默认启动全部相机并低头。
- 如果头已经低下去了，后续重启相机必须用 `bash scripts/start_vla_nodes.sh --no-move-head`，避免重复动作。
- 双手采集默认订阅左右手 `image_h264`，不是 `image_raw`。
- 采集器要求关键数据更新后才写样本，不复用旧图像或旧 state 凑 20Hz。

## 当前实际状态

截至 2026-06-10 16:50 CST：

- 上位机工程已同步到 `/home/ubuntu/cbc_tienkung2.0_vla_collect_data`。
- 头部已经低下去，后续不要重复发低头命令，除非用户明确要求。
- 刚才的坏相机会话已停止：

```bash
tmux kill-session -t vla_camera_launch 2>/dev/null || true
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
```

- 停止后仍可见头部相机话题：
  - `/camera/color/image_raw`
  - `/camera/color/image_raw/compressed`
  - `/camera/color/camera_info`
- n3 当前 USB 层看不到 D405：
  - `lsusb | grep -i RealSense` 无输出。
  - `rs-enumerate-devices` 无设备。
  - `/dev/video*` 无 D405 相关设备。
- 因此当前不能进行有效双手采集。`/camera/d405_left/right/color/image_h264` 即使短暂有 publisher，也只是 conversion 节点空挂，不代表有真实图像帧。
- n3 USB 控制器重绑需要 sudo；非交互 ssh 触发了 `[sudo] password for nvidia:`，本轮未执行成功。

下一步恢复方式：

1. 用户现场重新插拔/重新上电两台 D405；或提供 n3 sudo 权限执行 USB 控制器重绑。
2. 确认 n3 USB 可见两台 RealSense：

```bash
ssh tienkung
ssh n3
lsusb | grep -i RealSense
rs-enumerate-devices | grep -E 'Serial Number|Name|Physical Port'
```

3. 再在上位机启动相机；因为头已经低下去了，优先使用：

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

4. 只有三路图像和状态话题都有真实新数据后，才开始采集。

## 当前方案

本轮回到旧项目已验证稳定的相机链路。我们的工程只做统一启动、统一采集和数据上传，不重写底层相机驱动参数。

一键启动：

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh
```

默认会低头。只启动相机、不让机器人动作时：

```bash
bash scripts/start_vla_nodes.sh --no-move-head
```

`launch/vla_camera_nodes.launch.py` 当前执行：

- `n3`：先 `source /opt/ros/humble/setup.bash`，再执行 `/home/nvidia/njd/env_init.sh`，沿用旧项目稳定的左右 D405 和转换进程启动方式。
- `n2`：`/home/nvidia/njd/button/tool/start_camera.sh`，沿用旧项目稳定的头部 Orbbec 启动方式。
- `n1`：`scripts/start_vla_nodes.sh` 默认发布一次低头命令；直接使用 launch 时由 `move_head` 参数控制。

## 当前采集入口

只保留两个 Python 采集入口：

```text
scripts/dual_hands_collect.py
scripts/gripper_vla_collect.py
```

公共逻辑在：

```text
cbc_tienkung_vla/collector.py
```

已删除旧入口：

```text
cbc_tienkung2.0_vla_dual_hands_collect_data.py
```

## 当前图像话题

双手采集默认使用旧项目稳定话题：

- 头部：`/camera/color/image_raw/compressed`，`sensor_msgs/msg/CompressedImage`
- 左手：`/camera/d405_left/color/image_h264`，`foxglove_msgs/msg/CompressedVideo`
- 右手：`/camera/d405_right/color/image_h264`，`foxglove_msgs/msg/CompressedVideo`

采集目标为 `20Hz`。采集器使用最新到达的数据做对齐，同一条关键图像或 state 消息不重复写入多个样本。

D405 启动脚本已在 n3 上备份并补充关闭项：

- 备份：`/home/nvidia/start_d405_left.sh.bak_20260610_vla_depth_off`
- 备份：`/home/nvidia/start_d405_right.sh.bak_20260610_vla_depth_off`
- 当前脚本显式关闭：`enable_depth`、`enable_infra`、`enable_infra1`、`enable_infra2`、`align_depth.enable`、`enable_rgbd`、`enable_gyro`、`enable_accel`、`enable_motion`、`pointcloud.enable`、`publish_tf`、`diagnostics_period`。
- `/camera/d405_*/extrinsics/depth_to_color` 是外参标定话题，不是深度图像流；真正需要避免的是 `/camera/d405_*/depth/image*`、`infra*`、`pointcloud` 等。

## 健康检查

启动 launch 后检查：

```bash
ros2 topic list | grep -E 'camera|arm|inspire_hand'
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

健康标准：

- `ros2 topic info /camera/d405_left/color/image_h264` 和 `/camera/d405_right/color/image_h264` 必须有 publisher。
- 还必须确认能收到真实消息，不能只看 publisher：

```bash
timeout 5s ros2 topic echo --once /camera/d405_left/color/image_h264 --field format
timeout 5s ros2 topic echo --once /camera/d405_right/color/image_h264 --field format
```

- 如果 echo 不到消息，去 n3 检查 `/camera/d405_left/color/image_raw` 和 `/camera/d405_right/color/image_raw` 是否有 publisher；没有的话就是 D405 节点/USB 层问题，不要启动采集。

## 验证采集命令

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
python3 scripts/dual_hands_collect.py \
  --target-hz 20 \
  --image-write-mode decoded_png \
  --output-dir /home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data_validation
```

采集程序启动后，每组输入 `1` 录制数秒，再输入 `2` 停止；重复三次。交互只保留 `1/2/3/q`，不把上传做成录制按键。

开始采集前必须确认：

- 头部 compressed RGB 有真实频率。
- 左右手 h264 能 echo 到真实消息。
- `/arm/status`、`/arm/cmd_ctrl`、左右手 state 都有真实更新。
- 没有 `/camera/d405_*/depth/image*`、`infra*`、`pointcloud` 这类不需要的高带宽话题。

## 上传脚本

如果后续把采集器放到 `n3` 本机运行，采集完成后单独上传：

```bash
cd /home/nvidia/cbc_tienkung2.0_vla_collect_data
bash scripts/upload_recorded_data.sh --dry-run
bash scripts/upload_recorded_data.sh
```

上传脚本行为：

- 扫描本地 `vla_recorded_data` 下的数字目录。
- 查询上位机目标目录已有最大编号。
- 按顺序把本地目录上传为远端后续编号，避免覆盖和编号乱序。
- 只有 rsync 成功后才删除对应本地目录。
- 如果需要测试流程但保留本地数据，使用 `--keep-local`。

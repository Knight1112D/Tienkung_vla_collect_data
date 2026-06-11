#!/usr/bin/env bash
# 按缺失的数据流恢复 VLA 相机节点。

set -euo pipefail

PROJECT_DIR="/home/ubuntu/cbc_tienkung2.0_vla_collect_data"

need_head=0
need_hand=0

if [[ "$#" -eq 0 ]]; then
  need_head=1
  need_hand=1
fi

for item in "$@"; do
  case "$item" in
    head)
      need_head=1
      ;;
    hand_left|hand_right)
      need_hand=1
      ;;
  esac
done

if [[ "$need_head" -eq 1 ]]; then
  echo "[recover] 重启 n2 头部 Orbbec 相机"
  ssh n2 "bash -lc '
set -e
pkill -f \"orbbec_camera gemini_330_series|camera_container\" 2>/dev/null || true
sleep 2
source /opt/ros/humble/setup.bash 2>/dev/null || true
ros2 daemon stop >/dev/null 2>&1 || true
ros2 daemon start >/dev/null 2>&1 || true
cd /home/nvidia/njd/button
source install/setup.bash
cd tool
nohup ./start_camera.sh > /tmp/vla_head_camera_restart.log 2>&1 &
'"
fi

if [[ "$need_hand" -eq 1 ]]; then
  echo "[recover] 重启 n3 左右手 D405 相机链路"
  ssh n3 "bash -lc '
set -e
pkill -f \"env_init.sh|conversion_left.py|conversion_right.py|realsense2_camera\" 2>/dev/null || true
sleep 3
source /opt/ros/humble/setup.bash
cd /home/nvidia/njd
nohup ./env_init.sh > /tmp/vla_hand_cameras_restart.log 2>&1 &
'"
fi

sleep 8

source /opt/ros/humble/setup.bash 2>/dev/null || true
for topic in \
  /camera/color/image_raw/compressed \
  /camera/d405_left/color/image_h264 \
  /camera/d405_right/color/image_h264
do
  echo "[recover] 检查 $topic"
  timeout 5 ros2 topic echo --once "$topic" >/dev/null && echo "[recover] ok $topic" || echo "[recover] missing $topic"
done


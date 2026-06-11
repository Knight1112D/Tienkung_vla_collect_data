#!/usr/bin/env bash
# 天工 VLA 节点一键启动脚本：启动全部相机，并默认让机器人低头。

set -euo pipefail

MOVE_HEAD=1
SHOW_HELP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --move-head)
      MOVE_HEAD=1
      shift
      ;;
    --no-move-head)
      MOVE_HEAD=0
      shift
      ;;
    -h|--help)
      SHOW_HELP=1
      shift
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$SHOW_HELP" -eq 1 ]]; then
  cat <<'EOF'
用法:
  bash scripts/start_vla_nodes.sh [--no-move-head]

功能:
  1. 在 n3 启动旧项目稳定使用的 /home/nvidia/njd/env_init.sh。
  2. 在 n2 启动旧项目稳定使用的头部相机脚本。
  3. 默认在 n1 发布一次低头命令，方便 VLA 采集视角。

说明:
  该脚本会调用 launch/vla_camera_nodes.launch.py。
  默认会低头；如果只想启动相机、不让机器人动作，请传入 --no-move-head。
  如需直接使用 launch：
    ros2 launch /home/ubuntu/cbc_tienkung2.0_vla_collect_data/launch/vla_camera_nodes.launch.py move_head:=true
EOF
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$MOVE_HEAD" -eq 1 ]]; then
  MOVE_HEAD_VALUE=true
else
  MOVE_HEAD_VALUE=false
fi

exec ros2 launch "$PROJECT_DIR/launch/vla_camera_nodes.launch.py" move_head:="$MOVE_HEAD_VALUE"

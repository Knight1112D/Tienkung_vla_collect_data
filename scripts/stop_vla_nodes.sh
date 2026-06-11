#!/usr/bin/env bash
# 停止 VLA 相机节点，便于重新按独立会话启动。

set -euo pipefail

stop_remote_session() {
  local host="$1"
  local session="$2"
  local pattern="$3"

  ssh "$host" "SESSION='$session' PATTERN='$pattern' bash -s" <<'REMOTE'
set -euo pipefail
if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION" || true
  echo "[$(hostname)] 已停止 tmux 会话: $SESSION"
fi

pid_path="$HOME/logs/${SESSION}.pid"
if [ -f "$pid_path" ]; then
  pid="$(cat "$pid_path")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    echo "[$(hostname)] 已停止 nohup 进程: $SESSION, pid=$pid"
  fi
  rm -f "$pid_path"
fi

mapfile -t pids < <(pgrep -f "$PATTERN" 2>/dev/null || true)
for pid in "${pids[@]}"; do
  if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then
    kill "$pid" 2>/dev/null || true
  fi
done
sleep 1
for pid in "${pids[@]}"; do
  if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ] && kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
done
REMOTE
}

stop_remote_session n3 vla_d405_left 'start_d405_left.sh|d405_left|realsense2_camera'
stop_remote_session n3 vla_d405_right 'start_d405_right.sh|d405_right|realsense2_camera'
stop_remote_session n3 vla_hand_cameras 'env_init.sh|vla_hand_cameras_start.sh|conversion_left.py|conversion_right.py'
stop_remote_session n2 vla_head_camera 'orbbec_camera|camera_container|gemini_330_series'

echo "VLA 相机节点停止命令已发送。"

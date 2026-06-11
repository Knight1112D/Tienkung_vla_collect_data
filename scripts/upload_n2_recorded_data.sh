#!/usr/bin/env bash
# 从 n2 上传 /dev/shm 中的双手采集数据到上位机，并在成功后删除本地数据。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_DIR="${LOCAL_DIR:-/dev/shm/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands}"
REMOTE_HOST="${REMOTE_HOST:-ubuntu@192.168.41.5}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands}"
DRY_RUN=0
KEEP_LOCAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --keep-local)
      KEEP_LOCAL=1
      shift
      ;;
    --local-dir)
      LOCAL_DIR="$2"
      shift 2
      ;;
    --remote-host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --remote-dir)
      REMOTE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
用法:
  bash scripts/upload_n2_recorded_data.sh [--dry-run] [--keep-local]

环境变量:
  LOCAL_DIR    本地 dual_hands 数据目录
  REMOTE_HOST  上位机 SSH 目标，默认 ubuntu@192.168.41.5
  REMOTE_DIR   上位机 dual_hands 目标目录

说明:
  脚本会读取上位机已有最大编号，把 n2 本地编号目录按顺序上传为后续编号。
  默认上传成功后删除 n2 本地目录；如需保留，加 --keep-local。
EOF
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$LOCAL_DIR" ]]; then
  echo "没有需要上传的本地数据: $LOCAL_DIR"
  exit 0
fi

mapfile -t local_sessions < <(find "$LOCAL_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -E '^[0-9]{4}$' | sort)
if [[ "${#local_sessions[@]}" -eq 0 ]]; then
  echo "没有需要上传的本地数据: $LOCAL_DIR"
  exit 0
fi

remote_max="$(
  ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_DIR'; find '$REMOTE_DIR' -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -E '^[0-9]{4}$' | sort -n | tail -n 1" || true
)"
if [[ -z "$remote_max" ]]; then
  next_id=0
else
  next_id=$((10#$remote_max + 1))
fi

echo "本地目录: $LOCAL_DIR"
echo "远端目录: $REMOTE_HOST:$REMOTE_DIR"
echo "远端下一个编号: $(printf '%04d' "$next_id")"

for session in "${local_sessions[@]}"; do
  target="$(printf '%04d' "$next_id")"
  src="$LOCAL_DIR/$session/"
  dst="$REMOTE_HOST:$REMOTE_DIR/$target/"
  echo "计划上传: $session -> $target"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    rsync -avnc --delete "$src" "$dst"
  else
    rsync -av --delete "$src" "$dst"
    if [[ "$KEEP_LOCAL" -eq 0 ]]; then
      rm -rf "$LOCAL_DIR/$session"
      echo "已删除本地数据: $LOCAL_DIR/$session"
    fi
  fi
  next_id=$((next_id + 1))
done

echo "上传流程完成。"

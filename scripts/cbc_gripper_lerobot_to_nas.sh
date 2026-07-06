#!/usr/bin/env bash
# 在上位机把夹爪原始采集数据转换为 LeRobot 数据集，然后转存到 NAS。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="${RAW_DIR:-/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/gripper}"
EXPORT_BASE="${EXPORT_BASE:-/home/ubuntu/cbc_tienkung2.0_vla_collect_data/lerobot_exports}"
NAS_HOST="${NAS_HOST:-192.168.41.6}"
NAS_BASE="${NAS_BASE:-/volume1/data/caobochun}"
FPS="${FPS:-20}"
TASK="${TASK:-Pick up the black box on the table with both grippers, hold it briefly, then put it down.}"

if [[ -x "${PROJECT_DIR}/.venv/bin/python" ]]; then
  PYTHON="${PYTHON:-${PROJECT_DIR}/.venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令：$1" >&2
    exit 1
  }
}

ask_dataset_name() {
  local value
  read -r -p "NAS 下的数据集文件夹名: " value
  if [[ -z "$value" ]] || [[ "$value" == */* ]] || [[ "$value" == "." ]] || [[ "$value" == ".." ]]; then
    echo "文件夹名不能为空，也不能包含 / . .." >&2
    exit 2
  fi
  printf '%s' "$value"
}

quote_remote() {
  printf "%q" "$1"
}

need_cmd ssh
need_cmd rsync

DATASET_NAME="${1:-}"
if [[ -z "$DATASET_NAME" ]]; then
  DATASET_NAME="$(ask_dataset_name)"
fi
if [[ "$DATASET_NAME" == */* ]] || [[ "$DATASET_NAME" == "." ]] || [[ "$DATASET_NAME" == ".." ]]; then
  echo "文件夹名不能包含 / . .." >&2
  exit 2
fi

EXPORT_DIR="${EXPORT_BASE%/}/${DATASET_NAME}"
NAS_TARGET="${NAS_BASE%/}/${DATASET_NAME}"
REPO_ID_DATASET="$(printf '%s' "$DATASET_NAME" | tr -c 'A-Za-z0-9._-' '_' | sed -E 's/_+/_/g; s/^_//; s/_$//')"
REPO_ID_DATASET="${REPO_ID_DATASET:-tienkung_gripper_dataset}"
REPO_ID="${REPO_ID:-caobochun/${REPO_ID_DATASET}}"

if [[ ! -d "$RAW_DIR" ]]; then
  echo "原始夹爪数据目录不存在: $RAW_DIR" >&2
  exit 1
fi
if ! find "$RAW_DIR" -mindepth 1 -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9]' | grep -q .; then
  echo "原始夹爪数据目录里没有 0000 这种轨迹目录: $RAW_DIR" >&2
  exit 1
fi

if ! "$PYTHON" - <<'PY' >/dev/null 2>&1
import lerobot
PY
then
  if command -v uv >/dev/null 2>&1; then
    INSTALL_HINT="  cd $PROJECT_DIR
  uv venv
  uv pip install -i https://mirrors.aliyun.com/pypi/simple/ lerobot Pillow numpy tqdm tyro"
  else
    INSTALL_HINT="  cd $PROJECT_DIR
  python3 -m pip install --user -i https://mirrors.aliyun.com/pypi/simple/ uv
  ~/.local/bin/uv venv
  ~/.local/bin/uv pip install -i https://mirrors.aliyun.com/pypi/simple/ lerobot Pillow numpy tqdm tyro"
  fi
  cat >&2 <<EOF
当前 Python 环境缺少 lerobot：$PYTHON
请先在上位机项目里安装转换依赖，例如：
$INSTALL_HINT
EOF
  exit 1
fi

echo "raw: $RAW_DIR"
echo "export: $EXPORT_DIR"
echo "nas: ${NAS_HOST}:${NAS_TARGET}"
echo "repo_id: $REPO_ID"

"$PYTHON" "$PROJECT_DIR/examples/tienkung/convert_tienkung_gripper_data_to_lerobot.py" \
  --raw-dir "$RAW_DIR" \
  --repo-id "$REPO_ID" \
  --root "$EXPORT_DIR" \
  --task "$TASK" \
  --fps "$FPS" \
  --overwrite

ssh "$NAS_HOST" "rm -rf -- $(quote_remote "$NAS_TARGET") && mkdir -p -- $(quote_remote "$NAS_TARGET")"
rsync -a --info=progress2 --delete "$EXPORT_DIR/" "$NAS_HOST:$NAS_TARGET/"

rm -rf "$EXPORT_DIR"

echo "已转存到 NAS: ${NAS_HOST}:${NAS_TARGET}"
echo "本地临时 LeRobot 目录已删除，原始采集数据保留在: $RAW_DIR"

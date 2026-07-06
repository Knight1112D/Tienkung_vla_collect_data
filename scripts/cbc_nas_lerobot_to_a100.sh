#!/usr/bin/env bash
# 从 NAS 把指定 LeRobot 数据集目录同步到 A100_8。

set -euo pipefail

NAS_HOST="${NAS_HOST:-192.168.41.6}"
A100_HOST="${A100_HOST:-A100_8}"
NAS_BASE="${NAS_BASE:-/volume1/data/caobochun}"
A100_BASE="${A100_BASE:-/data/caobochun}"

ask_dataset_name() {
  local value
  read -r -p "要从 NAS 同步的数据集文件夹名: " value
  if [[ -z "$value" ]] || [[ "$value" == */* ]] || [[ "$value" == "." ]] || [[ "$value" == ".." ]]; then
    echo "文件夹名不能为空，也不能包含 / . .." >&2
    exit 2
  fi
  printf '%s' "$value"
}

quote_remote() {
  printf "%q" "$1"
}

command -v ssh >/dev/null 2>&1 || {
  echo "缺少命令：ssh" >&2
  exit 1
}

DATASET_NAME="${1:-}"
if [[ -z "$DATASET_NAME" ]]; then
  DATASET_NAME="$(ask_dataset_name)"
fi
if [[ "$DATASET_NAME" == */* ]] || [[ "$DATASET_NAME" == "." ]] || [[ "$DATASET_NAME" == ".." ]]; then
  echo "文件夹名不能包含 / . .." >&2
  exit 2
fi

NAS_SOURCE="${NAS_BASE%/}/${DATASET_NAME}"
A100_TARGET="${A100_BASE%/}/${DATASET_NAME}"

echo "nas: ${NAS_HOST}:${NAS_SOURCE}"
echo "A100: ${A100_HOST}:${A100_TARGET}"

ssh "$NAS_HOST" "test -d $(quote_remote "$NAS_SOURCE")"
ssh "$A100_HOST" "rm -rf -- $(quote_remote "$A100_TARGET") && mkdir -p -- $(quote_remote "$A100_TARGET")"

ssh "$NAS_HOST" \
  "tar -cf - -C $(quote_remote "$NAS_SOURCE") . | ssh -o BatchMode=yes $(quote_remote "$A100_HOST") tar -xpf - -C $(quote_remote "$A100_TARGET")"

echo "已同步到 A100: ${A100_HOST}:${A100_TARGET}"

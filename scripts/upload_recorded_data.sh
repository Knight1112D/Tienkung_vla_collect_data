#!/usr/bin/env bash
# 上传 n3 本机 VLA 采集数据到上位机，并在成功后删除本地目录。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOCAL_DIR="${LOCAL_DIR:-/home/nvidia/cbc_tienkung2.0_vla_collect_data/vla_recorded_data}"
REMOTE_DIR="${REMOTE_DIR:-ubuntu@192.168.41.5:/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data_from_n3}"

python3 "${PROJECT_ROOT}/scripts/upload_recorded_data.py" \
  --local-dir "${LOCAL_DIR}" \
  --remote-dir "${REMOTE_DIR}" \
  "$@"

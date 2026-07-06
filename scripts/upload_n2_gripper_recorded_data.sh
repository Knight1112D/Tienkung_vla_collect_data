#!/usr/bin/env bash
# 从 n2 持久目录上传双夹爪采集数据到上位机，并在成功后删除本地数据。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export LOCAL_DIR="${LOCAL_DIR:-/home/nvidia/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/gripper}"
export REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/gripper}"

exec bash "$SCRIPT_DIR/upload_n2_recorded_data.sh" "$@"

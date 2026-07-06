#!/usr/bin/env bash
# 在 n2 的持久目录中运行双夹爪 VLA 采集。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-/home/nvidia/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/gripper}"
BUTTON_TOPIC="${BUTTON_TOPIC:-/encoder_identical_button}"

set +u
source /opt/ros/humble/setup.bash
source /home/nvidia/njd/button/install/setup.bash
set -u

mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_DIR"
exec python3 scripts/gripper_vla_collect.py \
  --output-dir "$OUTPUT_DIR" \
  --button-topic "$BUTTON_TOPIC" \
  "$@"

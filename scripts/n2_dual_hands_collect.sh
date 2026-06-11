#!/usr/bin/env bash
# 在 n2 的 /dev/shm 中运行双手 VLA 采集。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_DIR/vla_recorded_data/dual_hands}"

set +u
source /opt/ros/humble/setup.bash
source /home/nvidia/njd/button/install/setup.bash
set -u

mkdir -p "$OUTPUT_DIR"

cd "$PROJECT_DIR"
exec python3 scripts/dual_hands_collect.py \
  --output-dir "$OUTPUT_DIR" \
  "$@"

#!/usr/bin/env python3
"""加爪/夹爪 VLA 采集入口。

示例：
python3 scripts/gripper_vla_collect.py \
  --extra-joint-state-topic left_gripper_state=/TODO/left_gripper/state \
  --extra-joint-state-topic right_gripper_state=/TODO/right_gripper/state \
  --required-state-streams arm_cmd,arm_status,left_hand_state,right_hand_state,left_gripper_state,right_gripper_state
"""

from pathlib import Path
import sys
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cbc_tienkung_vla.collector import build_arg_parser, run_collector


def main(argv: Optional[Sequence[str]] = None) -> None:
    """加爪/夹爪采集入口。"""
    parser = build_arg_parser(description="天工 VLA 加爪/夹爪数据采集脚本")
    args = parser.parse_args(argv)
    run_collector(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""双夹爪 VLA 采集入口。

左右夹爪按 1 自由度保存。当前天工夹爪状态和命令话题为 UInt16，
采集器会把数值写入 arm.npz 中左右末端 position 的第 1 维。
"""

from pathlib import Path
import sys
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cbc_tienkung_vla.collector import build_arg_parser, run_collector

DEFAULT_OUTPUT_DIR = "/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/gripper"


def main(argv: Optional[Sequence[str]] = None) -> None:
    """双夹爪采集入口。"""
    parser = build_arg_parser(
        description="天工 VLA 双夹爪数据采集脚本",
        default_output_dir=DEFAULT_OUTPUT_DIR,
        default_left_hand_cmd_topic="/left_claw/command",
        default_right_hand_cmd_topic="/right_claw/command",
        default_left_hand_state_topic="/left_claw/status",
        default_right_hand_state_topic="/right_claw/status",
        default_left_hand_cmd_type="uint16",
        default_right_hand_cmd_type="uint16",
        default_left_hand_state_type="uint16",
        default_right_hand_state_type="uint16",
        default_left_hand_dof=1,
        default_right_hand_dof=1,
    )
    args = parser.parse_args(argv)
    run_collector(args)


if __name__ == "__main__":
    main()

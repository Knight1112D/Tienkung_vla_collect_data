#!/usr/bin/env python3
"""双夹爪 VLA 采集入口。

左右末端都按 1 自由度夹爪保存。夹爪话题暂时留空，实机确认后通过
--left-hand-state-topic 和 --right-hand-state-topic 传入。
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
        default_left_hand_cmd_topic="",
        default_right_hand_cmd_topic="",
        default_left_hand_state_topic="",
        default_right_hand_state_topic="",
        default_left_hand_dof=1,
        default_right_hand_dof=1,
    )
    args = parser.parse_args(argv)
    run_collector(args)


if __name__ == "__main__":
    main()

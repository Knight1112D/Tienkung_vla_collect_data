#!/usr/bin/env python3
"""双手 VLA 采集入口。"""

from pathlib import Path
import sys
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cbc_tienkung_vla.collector import build_arg_parser, run_collector


def main(argv: Optional[Sequence[str]] = None) -> None:
    """双手采集入口。"""
    parser = build_arg_parser(description="天工 VLA 双手数据采集脚本")
    args = parser.parse_args(argv)
    run_collector(args)


if __name__ == "__main__":
    main()

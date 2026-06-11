#!/usr/bin/env python3
"""把本机采集数据上传到上位机，并在成功后删除本地数据。"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional


def numeric_dirs(root: Path) -> List[Path]:
    """返回根目录下按编号排序的采集目录。"""
    if not root.exists():
        return []
    return sorted(
        [item for item in root.iterdir() if item.is_dir() and item.name.isdigit()],
        key=lambda item: int(item.name),
    )


def run(command: List[str], *, dry_run: bool = False, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """运行命令；dry-run 时只打印不执行。"""
    print("+ " + " ".join(command))
    if dry_run:
        return subprocess.CompletedProcess(command, 0, "", "")
    return subprocess.run(command, text=True, capture_output=capture)


def remote_max_index(target: str, width: int, dry_run: bool = False) -> int:
    """查询远端目标目录当前最大编号；本地路径和 ssh 目标都支持。"""
    if ":" not in target:
        root = Path(target).expanduser()
        dirs = numeric_dirs(root)
        return max((int(item.name) for item in dirs), default=-1)

    host, remote_dir = target.split(":", 1)
    script = (
        f"mkdir -p {quote(remote_dir)} && "
        f"find {quote(remote_dir)} -maxdepth 1 -type d -regextype posix-extended "
        f"-regex '.*/[0-9]{{{width},}}' -printf '%f\\n' | sort -n | tail -n 1"
    )
    result = run(["ssh", host, "bash", "-lc", script], dry_run=dry_run, capture=True)
    if dry_run or result.returncode != 0:
        return -1
    value = result.stdout.strip()
    return int(value) if value else -1


def quote(value: str) -> str:
    """给远端 bash 命令使用的单引号转义。"""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def target_child(target: str, child_name: str) -> str:
    """拼出目标子目录路径。"""
    target = target.rstrip("/")
    return f"{target}/{child_name}"


def rsync_dir(source: Path, target: str, remote_name: str, dry_run: bool = False) -> bool:
    """同步单个目录，成功返回 True。"""
    command = [
        "rsync",
        "-az",
        "--info=progress2",
        f"{source}/",
        target_child(target, remote_name) + "/",
    ]
    result = run(command, dry_run=dry_run)
    return result.returncode == 0


def remove_local(source: Path, dry_run: bool = False) -> None:
    """删除已成功上传的本地目录。"""
    print(f"删除本地目录: {source}")
    if not dry_run:
        shutil.rmtree(source)


def upload_all(args: argparse.Namespace) -> int:
    """上传所有本地编号目录，并按远端最大编号后续编号。"""
    local_root = Path(args.local_dir).expanduser().resolve()
    local_dirs = numeric_dirs(local_root)
    if not local_dirs:
        print(f"没有找到待上传目录: {local_root}")
        return 0

    max_index = remote_max_index(args.remote_dir, args.width, args.dry_run)
    next_index = max_index + 1
    print(f"远端当前最大编号: {max_index if max_index >= 0 else '无'}")

    uploaded: List[Path] = []
    for source in local_dirs:
        remote_name = f"{next_index:0{args.width}d}"
        print(f"上传编号映射: 本地 {source.name} -> 远端 {remote_name}")

        if not rsync_dir(source, args.remote_dir, remote_name, args.dry_run):
            print(f"上传失败，保留本地目录: {source}", file=sys.stderr)
            return 1

        uploaded.append(source)
        next_index += 1

    if args.keep_local:
        print("已按要求保留本地数据。")
        return 0

    for source in uploaded:
        remove_local(source, args.dry_run)
    print(f"上传完成，共处理 {len(uploaded)} 组数据。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    parser = argparse.ArgumentParser(description="上传 VLA 本地采集数据到上位机并清理本地目录")
    parser.add_argument("--local-dir", default="/home/nvidia/cbc_tienkung2.0_vla_collect_data/vla_recorded_data", help="本机采集数据根目录")
    parser.add_argument("--remote-dir", required=True, help="目标目录，例如 ubuntu@192.168.41.5:/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data_from_n3")
    parser.add_argument("--width", type=int, default=4, help="编号宽度，默认 0000 这种四位编号")
    parser.add_argument("--keep-local", action="store_true", help="上传成功后保留本地数据，不删除")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不执行上传、重命名或删除")
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """脚本入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    return upload_all(args)


if __name__ == "__main__":
    raise SystemExit(main())

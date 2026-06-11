#!/usr/bin/env python3
"""查看 VLA 三路相机画面。"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
import rclpy
from foxglove_msgs.msg import CompressedVideo
from rclpy.node import Node
from rclpy.qos import qos_profile_system_default
from sensor_msgs.msg import CompressedImage


class VLACameraViewer(Node):
    """订阅三路相机话题并维护最新画面。"""

    def __init__(self, args: argparse.Namespace):
        super().__init__("cbc_tienkung2_vla_camera_viewer")
        self.args = args
        self.lock = threading.Lock()
        self.frames: Dict[str, Optional[np.ndarray]] = {
            "head": None,
            "hand_left": None,
            "hand_right": None,
        }
        self.seq = {"head": 0, "hand_left": 0, "hand_right": 0}
        self.last_recv = {"head": 0.0, "hand_left": 0.0, "hand_right": 0.0}
        self._subscriptions = [
            self.create_subscription(CompressedImage, args.head_topic, lambda msg: self.on_compressed("head", bytes(msg.data)), qos_profile_system_default),
            self.create_subscription(CompressedVideo, args.left_hand_topic, lambda msg: self.on_compressed("hand_left", bytes(msg.data)), qos_profile_system_default),
            self.create_subscription(CompressedVideo, args.right_hand_topic, lambda msg: self.on_compressed("hand_right", bytes(msg.data)), qos_profile_system_default),
        ]

    def on_compressed(self, name: str, data: bytes) -> None:
        """解码压缩图并更新最新画面。"""
        if not data:
            return
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        with self.lock:
            self.frames[name] = frame
            self.seq[name] += 1
            self.last_recv[name] = time.time()

    def make_canvas(self) -> np.ndarray:
        """生成三路画面的横向拼图。"""
        with self.lock:
            frames = dict(self.frames)
            seq = dict(self.seq)
            last_recv = dict(self.last_recv)

        tiles = [
            self.make_tile("head", "head", frames["head"], seq["head"], last_recv["head"]),
            self.make_tile("hand_left", "left hand", frames["hand_left"], seq["hand_left"], last_recv["hand_left"]),
            self.make_tile("hand_right", "right hand", frames["hand_right"], seq["hand_right"], last_recv["hand_right"]),
        ]
        return np.concatenate(tiles, axis=1)

    def make_tile(self, key: str, label: str, frame: Optional[np.ndarray], seq: int, recv_sec: float) -> np.ndarray:
        """把单路画面缩放到预览尺寸并叠加状态文字。"""
        width = int(self.args.tile_width)
        height = int(self.args.tile_height)
        if frame is None:
            tile = np.zeros((height, width, 3), dtype=np.uint8)
            status = "waiting"
        else:
            tile = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            age = time.time() - recv_sec if recv_sec > 0 else 0.0
            status = f"seq={seq} age={age:.2f}s"

        cv2.rectangle(tile, (0, 0), (width, 34), (0, 0, 0), -1)
        cv2.putText(tile, f"{label}  {status}", (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
        return tile


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""
    parser = argparse.ArgumentParser(description="查看天工 VLA 三路相机画面")
    parser.add_argument("--head-topic", default="/camera/color/image_raw/compressed", help="头部相机压缩图话题")
    parser.add_argument("--left-hand-topic", default="/camera/d405_left/color/image_h264", help="左手相机压缩图话题")
    parser.add_argument("--right-hand-topic", default="/camera/d405_right/color/image_h264", help="右手相机压缩图话题")
    parser.add_argument("--tile-width", type=int, default=480, help="每路预览宽度")
    parser.add_argument("--tile-height", type=int, default=360, help="每路预览高度")
    parser.add_argument("--save-preview", default="", help="无图形界面时保存一张预览拼图到指定路径")
    parser.add_argument("--save-timeout", type=float, default=8.0, help="保存预览图时等待首帧的最长秒数")
    return parser


def main() -> int:
    """脚本入口。"""
    parser = build_parser()
    args = parser.parse_args()
    rclpy.init(args=None)
    node = VLACameraViewer(args)

    try:
        if args.save_preview:
            deadline = time.time() + float(args.save_timeout)
            while rclpy.ok() and time.time() < deadline:
                rclpy.spin_once(node, timeout_sec=0.1)
                with node.lock:
                    if all(frame is not None for frame in node.frames.values()):
                        break
            canvas = node.make_canvas()
            output_path = Path(args.save_preview).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            ok = cv2.imwrite(str(output_path), canvas)
            print(f"预览图已保存: {output_path}" if ok else f"预览图保存失败: {output_path}")
            return 0 if ok else 1

        print("按 q 或 Esc 退出预览窗口。")
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.03)
            cv2.imshow("Tienkung VLA Cameras", node.make_canvas())
            key = cv2.waitKey(1) & 0xFF
            if key in {27, ord("q")}:
                break
        return 0
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    sys.exit(main())

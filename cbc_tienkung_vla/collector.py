#!/usr/bin/env python3
"""
天工 2.0 PRO VLA 固定频率数据采集器。

采集规则：
- 回调线程只保存每个话题的最新原始数据，新消息到来就替换旧缓存，避免图像解码阻塞 ROS 回调。
- 录制线程按固定 20Hz 保存当前快照，允许复用上一帧图像和状态。
- 输出结构贴近旧项目：每组目录只包含 head/、hand_left/、hand_right/ 和 arm.npz。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import rclpy
from bodyctrl_msgs.msg import CmdMotorCtrl, MotorStatusMsg
from foxglove_msgs.msg import CompressedVideo
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image, JointState
from std_msgs.msg import UInt16

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ros_time_to_sec(stamp: Any) -> float:
    """把 ROS 时间戳转为秒；空时间戳返回 0。"""
    if stamp is None:
        return 0.0
    return float(getattr(stamp, "sec", 0)) + float(getattr(stamp, "nanosec", 0)) * 1e-9


class VLACollectNode(Node):
    """按旧数据格式保存三路图像、机械臂和左右手状态。"""

    def __init__(self, args: argparse.Namespace):
        super().__init__("cbc_tienkung2_vla_fixed_rate_collect")
        self.args = args
        self.running = True
        self.is_recording = False
        self.pending_start = False
        self.pending_start_sec = 0.0
        self.current_dir: Optional[Path] = None
        self.last_saved_dir: Optional[Path] = None
        self.frame_count = 0
        self.lock = threading.Lock()
        self.last_wait_log_sec = 0.0
        self.last_wait_missing: Tuple[str, ...] = ()
        self.last_recover_sec = 0.0
        self.last_checkpoint_sec = 0.0
        self.button_pressed_state: Dict[str, bool] = {}
        self.last_button_trigger_sec: Dict[str, float] = {}

        self.left_arm_joint_ids = list(range(11, 18))
        self.right_arm_joint_ids = list(range(21, 28))
        self.arm_joint_ids = self.left_arm_joint_ids + self.right_arm_joint_ids

        self.latest_images: Dict[str, Any] = {"head": None, "hand_left": None, "hand_right": None}
        self.latest_image_compressed: Dict[str, bool] = {"head": True, "hand_left": True, "hand_right": True}
        self.latest_image_seq: Dict[str, int] = {"head": 0, "hand_left": 0, "hand_right": 0}
        self.latest_image_recv_sec: Dict[str, float] = {"head": 0.0, "hand_left": 0.0, "hand_right": 0.0}
        self.latest_image_stamp_sec: Dict[str, float] = {"head": 0.0, "hand_left": 0.0, "hand_right": 0.0}

        self.latest_arm_cmd: Optional[List[float]] = None
        self.latest_arm_status: Optional[List[float]] = None
        self.latest_arm_cmd_by_id: Dict[int, float] = {}
        self.latest_left_hand_cmd: Optional[List[float]] = None
        self.latest_right_hand_cmd: Optional[List[float]] = None
        self.latest_left_hand_state: Optional[List[float]] = None
        self.latest_right_hand_state: Optional[List[float]] = None

        self.latest_arm_status_speed: Optional[List[float]] = None
        self.latest_arm_status_current: Optional[List[float]] = None
        self.latest_arm_status_temperature: Optional[List[float]] = None
        self.latest_arm_status_error: Optional[List[int]] = None

        self.histories: Dict[str, List[Any]] = {}
        self._reset_histories()
        self._owned_subscriptions = []

        self._create_subscriptions()
        self.save_thread = threading.Thread(target=self.save_loop, daemon=True)
        self.input_thread = threading.Thread(target=self.terminal_listener, daemon=True)
        self.save_thread.start()
        self.input_thread.start()
        self.get_logger().info("VLA 固定频率采集器已启动，请输入 1 开始、2 停止、3 删除上一组、q 退出。")

    def _create_subscriptions(self) -> None:
        image_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        state_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=80,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )

        self.create_image_subscription("head", self.args.head_topic, self.args.head_image_type, image_qos)
        self.create_image_subscription("hand_left", self.args.left_hand_image_topic, self.args.left_hand_image_type, image_qos)
        self.create_image_subscription("hand_right", self.args.right_hand_image_topic, self.args.right_hand_image_type, image_qos)

        self._owned_subscriptions.append(self.create_subscription(CmdMotorCtrl, self.args.arm_cmd_topic, self.on_arm_cmd, state_qos))
        self._owned_subscriptions.append(self.create_subscription(MotorStatusMsg, self.args.arm_status_topic, self.on_arm_status, state_qos))
        self.create_terminal_subscription("left_hand_cmd", self.args.left_hand_cmd_topic, self.args.left_hand_cmd_type, state_qos)
        self.create_terminal_subscription("right_hand_cmd", self.args.right_hand_cmd_topic, self.args.right_hand_cmd_type, state_qos)
        self.create_terminal_subscription("left_hand_state", self.args.left_hand_state_topic, self.args.left_hand_state_type, state_qos)
        self.create_terminal_subscription("right_hand_state", self.args.right_hand_state_topic, self.args.right_hand_state_type, state_qos)
        self.create_button_subscription(state_qos)

    def create_image_subscription(self, name: str, topic: str, image_type: str, qos: Any) -> None:
        """根据图像消息类型订阅话题。"""
        if image_type == "compressed_image":
            self._owned_subscriptions.append(self.create_subscription(CompressedImage, topic, lambda msg: self.on_compressed_image(name, msg), qos))
        elif image_type == "compressed_video":
            self._owned_subscriptions.append(self.create_subscription(CompressedVideo, topic, lambda msg: self.on_compressed_video(name, msg), qos))
        elif image_type == "raw_image":
            self._owned_subscriptions.append(self.create_subscription(Image, topic, lambda msg: self.on_raw_image(name, msg), qos))
        else:
            raise ValueError(f"未知图像类型: {image_type}")

    def create_terminal_subscription(self, name: str, topic: str, msg_type: str, qos: Any) -> None:
        """订阅末端执行器话题；话题为空时跳过，便于先预留采集方案。"""
        if not topic:
            self.get_logger().warn(f"{name} 话题为空，当前不会订阅该数据流。")
            return
        if msg_type == "joint_state":
            self._owned_subscriptions.append(self.create_subscription(JointState, topic, lambda msg: self.on_joint_state(name, msg), qos))
        elif msg_type == "uint16":
            self._owned_subscriptions.append(self.create_subscription(UInt16, topic, lambda msg: self.on_uint16_terminal(name, msg), qos))
        else:
            raise ValueError(f"未知末端执行器消息类型: {msg_type}")

    def create_button_subscription(self, qos: Any) -> None:
        """订阅外部按钮话题，用按钮边沿触发开始和停止采集。"""
        if not self.args.button_topic:
            return
        self._owned_subscriptions.append(self.create_subscription(JointState, self.args.button_topic, self.on_button_state, qos))
        self.get_logger().info(
            f"已启用按钮控制: {self.args.button_topic}，"
            f"开始={self.args.start_button_name or self.args.start_button_index}，"
            f"停止={self.args.stop_button_name or self.args.stop_button_index}"
        )

    def on_compressed_image(self, name: str, msg: CompressedImage) -> None:
        self.update_image(name, bytes(msg.data), ros_time_to_sec(msg.header.stamp), compressed=True)

    def on_compressed_video(self, name: str, msg: CompressedVideo) -> None:
        self.update_image(name, bytes(msg.data), ros_time_to_sec(msg.timestamp), compressed=True)

    def on_raw_image(self, name: str, msg: Image) -> None:
        frame = self.raw_image_to_bgr(msg)
        self.update_image(name, frame, ros_time_to_sec(msg.header.stamp), compressed=False)

    def update_image(self, name: str, payload: Any, stamp_sec: float, compressed: bool) -> None:
        """更新最新图像缓存；回调中不做 PNG 编码，避免阻塞 ROS 消息处理。"""
        cached_payload = bytes(payload) if compressed else payload
        if cached_payload is None:
            return
        with self.lock:
            self.latest_images[name] = cached_payload
            self.latest_image_compressed[name] = compressed
            self.latest_image_seq[name] += 1
            self.latest_image_recv_sec[name] = time.time()
            self.latest_image_stamp_sec[name] = stamp_sec

    def payload_to_png(self, payload: Any, compressed: bool) -> Optional[bytes]:
        """把压缩图或 BGR 图转成最终保存的 PNG 字节。"""
        try:
            if compressed:
                array = np.frombuffer(payload, np.uint8)
                frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
            else:
                frame = payload
            if frame is None:
                return None
            if self.args.output_image_size > 0:
                size = (self.args.output_image_size, self.args.output_image_size)
                frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
            ok, encoded = cv2.imencode(".png", frame)
            return bytes(encoded) if ok else None
        except Exception:
            return None

    def raw_image_to_bgr(self, msg: Image) -> Optional[np.ndarray]:
        """把 sensor_msgs/Image 转为 OpenCV BGR 图像。"""
        height = int(msg.height)
        width = int(msg.width)
        step = int(msg.step)
        encoding = str(msg.encoding or "").lower()
        raw = np.frombuffer(bytes(msg.data), np.uint8)

        if encoding in {"rgb8", "bgr8"}:
            row_bytes = width * 3
            if step < row_bytes or raw.size < step * height:
                return None
            frame = raw.reshape((height, step))[:, :row_bytes].reshape((height, width, 3))
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR) if encoding == "rgb8" else frame
        if encoding in {"mono8", "8uc1"}:
            row_bytes = width
            if step < row_bytes or raw.size < step * height:
                return None
            return raw.reshape((height, step))[:, :row_bytes].reshape((height, width))
        return None

    def on_arm_cmd(self, msg: CmdMotorCtrl) -> None:
        positions = {}
        for cmd in msg.cmds:
            try:
                joint_id = int(cmd.name)
            except (TypeError, ValueError):
                continue
            if joint_id in self.arm_joint_ids:
                positions[joint_id] = float(cmd.pos)
        if not positions:
            return
        with self.lock:
            self.latest_arm_cmd_by_id.update(positions)
            # 遥操模式下左右臂 command 会交替发布，每条消息通常只带 7 个关节。
            # 因此这里累计两侧最新 command，凑齐 14 个关节后再认为 command 数据流就绪。
            if not all(joint_id in self.latest_arm_cmd_by_id for joint_id in self.arm_joint_ids):
                return
            self.latest_arm_cmd = [self.latest_arm_cmd_by_id[joint_id] for joint_id in self.arm_joint_ids]

    def on_arm_status(self, msg: MotorStatusMsg) -> None:
        positions = {}
        speeds = {}
        currents = {}
        temperatures = {}
        errors = {}
        for status in msg.status:
            try:
                joint_id = int(status.name)
            except (TypeError, ValueError):
                continue
            if joint_id in self.arm_joint_ids:
                positions[joint_id] = float(status.pos)
                speeds[joint_id] = float(status.speed)
                currents[joint_id] = float(status.current)
                temperatures[joint_id] = float(status.temperature)
                errors[joint_id] = int(status.error)
        if all(joint_id in positions for joint_id in self.arm_joint_ids):
            with self.lock:
                self.latest_arm_status = [positions[joint_id] for joint_id in self.arm_joint_ids]
                self.latest_arm_status_speed = [speeds[joint_id] for joint_id in self.arm_joint_ids]
                self.latest_arm_status_current = [currents[joint_id] for joint_id in self.arm_joint_ids]
                self.latest_arm_status_temperature = [temperatures[joint_id] for joint_id in self.arm_joint_ids]
                self.latest_arm_status_error = [errors[joint_id] for joint_id in self.arm_joint_ids]

    def on_joint_state(self, name: str, msg: JointState) -> None:
        positions = self.slice_joint_positions(name, msg.position)
        names = self.slice_joint_names(name, msg.name)
        self.update_terminal_state(name, positions, names)

    def on_uint16_terminal(self, name: str, msg: UInt16) -> None:
        """把 UInt16 夹爪开合量保存为 1 维 position。"""
        self.update_terminal_state(name, [float(msg.data)], [name])

    def update_terminal_state(self, name: str, positions: List[float], names: List[str]) -> None:
        """更新末端执行器最新缓存和关节名元信息。"""
        with self.lock:
            if name == "left_hand_cmd":
                self.latest_left_hand_cmd = positions
                self.histories["left_hand_cmd_names_latest"] = names
            elif name == "right_hand_cmd":
                self.latest_right_hand_cmd = positions
                self.histories["right_hand_cmd_names_latest"] = names
            elif name == "left_hand_state":
                self.latest_left_hand_state = positions
                self.histories["left_hand_state_names_latest"] = names
            elif name == "right_hand_state":
                self.latest_right_hand_state = positions
                self.histories["right_hand_state_names_latest"] = names

    def on_button_state(self, msg: JointState) -> None:
        """把外部按钮映射到开始/停止采集，使用按下边沿触发。"""
        positions = [float(item) for item in msg.position]
        names = [str(item) for item in msg.name]
        events = []
        if self.button_is_pressed("start", self.args.start_button_name, self.args.start_button_index, names, positions):
            events.append("start")
        if self.button_is_pressed("stop", self.args.stop_button_name, self.args.stop_button_index, names, positions):
            events.append("stop")

        for event in events:
            if not self.button_edge_triggered(event):
                continue
            if event == "start":
                self.get_logger().info("检测到开始按钮，执行开始录制。")
                self.start_recording()
            elif event == "stop":
                self.get_logger().info("检测到停止按钮，执行停止录制。")
                self.stop_recording()

    def button_is_pressed(self, key: str, name: str, index: int, names: List[str], positions: List[float]) -> bool:
        """按名称优先、索引兜底判断按钮是否按下。"""
        value: Optional[float] = None
        if name and name in names:
            button_index = names.index(name)
            if button_index < len(positions):
                value = positions[button_index]
        elif 0 <= index < len(positions):
            value = positions[index]

        if value is None:
            self.button_pressed_state[key] = False
            return False
        if self.args.button_active_low:
            pressed = value <= self.args.button_pressed_threshold
        else:
            pressed = value >= self.args.button_pressed_threshold
        previous = self.button_pressed_state.get(key, False)
        self.button_pressed_state[key] = pressed
        return pressed and not previous

    def button_edge_triggered(self, key: str) -> bool:
        """按钮消抖，避免高频话题在一次按压里重复触发。"""
        now = time.time()
        last = self.last_button_trigger_sec.get(key, 0.0)
        if now - last < self.args.button_debounce_sec:
            return False
        self.last_button_trigger_sec[key] = now
        return True

    def slice_joint_positions(self, name: str, positions: Sequence[float]) -> List[float]:
        """按配置截取末端自由度；0 表示保存消息中的全部 position。"""
        dof = self.get_terminal_dof(name)
        values = [float(item) for item in positions]
        if dof <= 0:
            return values
        return values[:dof]

    def slice_joint_names(self, name: str, names: Sequence[str]) -> List[str]:
        """按配置截取末端关节名，保证元信息与 position 维度一致。"""
        dof = self.get_terminal_dof(name)
        values = [str(item) for item in names]
        if dof <= 0:
            return values
        return values[:dof]

    def get_terminal_dof(self, name: str) -> int:
        """查询某个末端通道需要保存的自由度数。"""
        dof_by_name = {
            "left_hand_cmd": self.args.left_hand_dof,
            "left_hand_state": self.args.left_hand_dof,
            "right_hand_cmd": self.args.right_hand_dof,
            "right_hand_state": self.args.right_hand_dof,
        }
        return int(dof_by_name.get(name, 0))

    def terminal_listener(self) -> None:
        print("\n" + "=" * 40)
        print("采集控制面板就绪！")
        print(" [1] 开始录制")
        print(" [2] 停止录制")
        print(" [3] 删除上一组数据")
        print(" [q] 退出脚本")
        print("=" * 40 + "\n")
        while self.running:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == "1":
                self.start_recording()
            elif cmd == "2":
                self.stop_recording()
            elif cmd == "3":
                self.delete_last_recording()
            elif cmd in {"q", "quit", "exit"}:
                self.running = False
                break

    def start_recording(self) -> None:
        with self.lock:
            if self.is_recording:
                self.get_logger().warn("已经在录制中，请勿重复操作。")
                return
            missing = self.missing_streams()
            if missing:
                if not self.pending_start:
                    self.pending_start_sec = time.time()
                self.pending_start = True
                self._log_waiting_streams(missing, force=True)
                return
            self._begin_recording_locked()

    def stop_recording(self) -> None:
        with self.lock:
            if self.pending_start and not self.is_recording:
                self.pending_start = False
                self.pending_start_sec = 0.0
                print("\n已取消等待启动。\n")
                return
            if not self.is_recording:
                return
            self.is_recording = False
            current_dir = self.current_dir
            frame_count = self.frame_count
            histories = {key: value for key, value in self.histories.items()}
        if current_dir is not None:
            self.write_arm_npz(current_dir, histories)
            self.last_saved_dir = current_dir
            print(f"\n停止采集，共 {frame_count} 帧。数据已保存至: {current_dir}\n")

    def delete_last_recording(self) -> None:
        with self.lock:
            if self.is_recording:
                self.get_logger().warn("正在录制中，请先输入 2 停止录制。")
                return
            target = self.last_saved_dir
        if target and target.exists():
            shutil.rmtree(target)
            self.last_saved_dir = None
            print(f"\n已删除上一组数据: {target}\n")
        else:
            print("\n没有可删除的上一组数据。\n")

    def save_loop(self) -> None:
        interval = 1.0 / float(self.args.target_hz)
        next_tick = time.perf_counter()
        while self.running:
            next_tick += interval
            time.sleep(max(0.0, next_tick - time.perf_counter()))
            self.try_auto_start()
            self.write_snapshot()

    def try_auto_start(self) -> None:
        """按 1 后如果数据流暂未就绪，在后台等待到齐后自动开始录制。"""
        with self.lock:
            if not self.pending_start or self.is_recording:
                return
            missing = self.missing_streams()
            if missing:
                self._log_waiting_streams(missing, force=False)
                return
            self._begin_recording_locked()

    def _begin_recording_locked(self) -> None:
        """在持锁状态下创建本组目录并进入录制状态。"""
        self.current_dir = self.next_session_dir()
        (self.current_dir / "head").mkdir(parents=True, exist_ok=False)
        (self.current_dir / "hand_left").mkdir(parents=True, exist_ok=False)
        (self.current_dir / "hand_right").mkdir(parents=True, exist_ok=False)
        self.frame_count = 0
        self._reset_histories()
        self.pending_start = False
        self.pending_start_sec = 0.0
        self.last_checkpoint_sec = 0.0
        self.is_recording = True
        print(f"\n开始采集... (帧率: {self.args.target_hz:.1f}Hz, 目录: {self.current_dir})")

    def _log_waiting_streams(self, missing: List[str], force: bool) -> None:
        """限频输出等待中的数据流，避免终端刷屏。"""
        now = time.time()
        missing_tuple = tuple(missing)
        if force or missing_tuple != self.last_wait_missing or now - self.last_wait_log_sec >= 2.0:
            self.get_logger().warn(f"数据流未完全就绪，已进入自动等待: {', '.join(missing)}")
            self.last_wait_missing = missing_tuple
            self.last_wait_log_sec = now
        self.maybe_recover_streams(missing, now)

    def maybe_recover_streams(self, missing: List[str], now: float) -> None:
        """等待启动时自动恢复缺失的相机流。"""
        image_missing = [name for name in missing if name in {"head", "hand_left", "hand_right"}]
        if not image_missing or not self.args.auto_recover_streams:
            return
        if self.pending_start_sec > 0.0 and now - self.pending_start_sec < self.args.recover_after_sec:
            return
        if now - self.last_recover_sec < self.args.recover_interval_sec:
            return
        self.last_recover_sec = now
        script = PROJECT_ROOT / "scripts" / "recover_vla_streams.sh"
        if not script.exists():
            self.get_logger().warn(f"自动恢复脚本不存在: {script}")
            return
        self.get_logger().warn(f"尝试自动恢复相机流: {', '.join(image_missing)}")
        try:
            subprocess.Popen(
                ["bash", str(script), *image_missing],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            self.get_logger().warn(f"自动恢复相机流失败: {exc}")

    def write_snapshot(self) -> None:
        with self.lock:
            if not self.is_recording or self.current_dir is None:
                return
            if self.missing_streams():
                return
            index = self.frame_count
            current_dir = self.current_dir
            image_payloads = {name: value for name, value in self.latest_images.items() if value is not None}
            image_compressed = dict(self.latest_image_compressed)
            snapshot = self.build_state_snapshot()

        images: Dict[str, bytes] = {}
        for name, payload in image_payloads.items():
            png_bytes = self.payload_to_png(payload, compressed=image_compressed[name])
            if png_bytes is None:
                return
            images[name] = png_bytes

        with self.lock:
            if not self.is_recording or self.current_dir != current_dir or self.frame_count != index:
                return
            self.append_histories(snapshot)
            self.frame_count += 1

        for name, data in images.items():
            (current_dir / name / f"{index:06d}.png").write_bytes(data)

        self.maybe_write_checkpoint(current_dir)

        sys.stdout.write(
            f"\r采集进度: {index} 帧 | Head: ✓ | LeftHand: ✓ | RightHand: ✓ | "
            f"Cmd/State: ✓ | 复用最新缓存"
        )
        sys.stdout.flush()

    def maybe_write_checkpoint(self, current_dir: Path) -> None:
        """录制中定期写 arm.npz，降低异常退出时只剩图像的风险。"""
        if self.args.checkpoint_interval_sec <= 0.0:
            return
        now = time.time()
        with self.lock:
            if not self.is_recording or self.current_dir != current_dir:
                return
            if now - self.last_checkpoint_sec < self.args.checkpoint_interval_sec:
                return
            self.last_checkpoint_sec = now
            histories = {key: value for key, value in self.histories.items()}
        self.write_arm_npz(current_dir, histories)

    def build_state_snapshot(self) -> Dict[str, Any]:
        """复制当前最新状态，供 20Hz 保存循环写入历史。"""
        return {
            "cmd_positions": list(self.latest_arm_cmd or []),
            "status_positions": list(self.latest_arm_status or []),
            "left_hand_cmd_positions": list(self.latest_left_hand_cmd or []),
            "right_hand_cmd_positions": list(self.latest_right_hand_cmd or []),
            "left_hand_state_positions": list(self.latest_left_hand_state or []),
            "right_hand_state_positions": list(self.latest_right_hand_state or []),
            "head_image_seq": self.latest_image_seq["head"],
            "left_hand_image_seq": self.latest_image_seq["hand_left"],
            "right_hand_image_seq": self.latest_image_seq["hand_right"],
            "head_image_recv_sec": self.latest_image_recv_sec["head"],
            "left_hand_image_recv_sec": self.latest_image_recv_sec["hand_left"],
            "right_hand_image_recv_sec": self.latest_image_recv_sec["hand_right"],
            "head_image_stamp_sec": self.latest_image_stamp_sec["head"],
            "left_hand_image_stamp_sec": self.latest_image_stamp_sec["hand_left"],
            "right_hand_image_stamp_sec": self.latest_image_stamp_sec["hand_right"],
        }

    def append_histories(self, snapshot: Dict[str, Any]) -> None:
        """把当前快照追加到内存历史，停止时统一写入 arm.npz。"""
        for key, value in snapshot.items():
            self.histories.setdefault(key, []).append(value)

    def write_arm_npz(self, session_dir: Path, histories: Dict[str, List[Any]]) -> None:
        """按旧项目方式在每组目录下保存 arm.npz。"""
        arrays: Dict[str, np.ndarray] = {
            "cmd_positions": self.rows_to_float_array(histories.get("cmd_positions", []), fallback_width=len(self.arm_joint_ids)),
            "status_positions": self.rows_to_float_array(histories.get("status_positions", []), fallback_width=len(self.arm_joint_ids)),
            "left_hand_cmd_positions": self.rows_to_float_array(histories.get("left_hand_cmd_positions", []), fallback_width=self.terminal_width("left_hand_cmd")),
            "right_hand_cmd_positions": self.rows_to_float_array(histories.get("right_hand_cmd_positions", []), fallback_width=self.terminal_width("right_hand_cmd")),
            "left_hand_state_positions": self.rows_to_float_array(histories.get("left_hand_state_positions", []), fallback_width=self.terminal_width("left_hand_state")),
            "right_hand_state_positions": self.rows_to_float_array(histories.get("right_hand_state_positions", []), fallback_width=self.terminal_width("right_hand_state")),
            "joint_ids": np.asarray(self.arm_joint_ids, dtype=np.int32),
            "left_arm_joint_ids": np.asarray(self.left_arm_joint_ids, dtype=np.int32),
            "right_arm_joint_ids": np.asarray(self.right_arm_joint_ids, dtype=np.int32),
            "head_image_seq": np.asarray(histories.get("head_image_seq", []), dtype=np.int64),
            "left_hand_image_seq": np.asarray(histories.get("left_hand_image_seq", []), dtype=np.int64),
            "right_hand_image_seq": np.asarray(histories.get("right_hand_image_seq", []), dtype=np.int64),
            "head_image_recv_sec": np.asarray(histories.get("head_image_recv_sec", []), dtype=np.float64),
            "left_hand_image_recv_sec": np.asarray(histories.get("left_hand_image_recv_sec", []), dtype=np.float64),
            "right_hand_image_recv_sec": np.asarray(histories.get("right_hand_image_recv_sec", []), dtype=np.float64),
            "head_image_stamp_sec": np.asarray(histories.get("head_image_stamp_sec", []), dtype=np.float64),
            "left_hand_image_stamp_sec": np.asarray(histories.get("left_hand_image_stamp_sec", []), dtype=np.float64),
            "right_hand_image_stamp_sec": np.asarray(histories.get("right_hand_image_stamp_sec", []), dtype=np.float64),
        }
        for key in ("left_hand_cmd_names_latest", "right_hand_cmd_names_latest", "left_hand_state_names_latest", "right_hand_state_names_latest"):
            arrays[key] = np.asarray(histories.get(key, []), dtype=str)
        np.savez(session_dir / "arm.npz", **arrays)

    def terminal_width(self, name: str) -> int:
        """返回末端执行器字段期望宽度；没有订阅 command 时允许为空数组。"""
        topic_by_name = {
            "left_hand_cmd": self.args.left_hand_cmd_topic,
            "right_hand_cmd": self.args.right_hand_cmd_topic,
            "left_hand_state": self.args.left_hand_state_topic,
            "right_hand_state": self.args.right_hand_state_topic,
        }
        if not topic_by_name.get(name):
            return 0
        return max(0, self.get_terminal_dof(name))

    def rows_to_float_array(self, rows: Sequence[Any], fallback_width: int = 0) -> np.ndarray:
        """把可能短暂缺失的行整理为稳定二维数组。

        夹爪 command 可能在录制开始后才第一次到达；这里用最近有效值前后填充，
        保持 arm.npz 形状稳定，避免一次短暂缺失破坏整组数据。
        """
        row_values: List[List[float]] = []
        max_width = max(0, int(fallback_width))
        for row in rows:
            values = [float(item) for item in row]
            row_values.append(values)
            max_width = max(max_width, len(values))
        if not row_values:
            return np.empty((0, max_width), dtype=np.float64)
        if max_width == 0:
            return np.empty((len(row_values), 0), dtype=np.float64)

        array = np.full((len(row_values), max_width), np.nan, dtype=np.float64)
        for index, values in enumerate(row_values):
            if values:
                width = min(len(values), max_width)
                array[index, :width] = values[:width]

        valid_rows = np.where(~np.isnan(array).all(axis=1))[0]
        if valid_rows.size == 0:
            return array

        first_valid = int(valid_rows[0])
        array[:first_valid] = array[first_valid]
        last_valid = array[first_valid].copy()
        for index in range(first_valid + 1, len(array)):
            if np.isnan(array[index]).all():
                array[index] = last_valid
            else:
                nan_mask = np.isnan(array[index])
                array[index, nan_mask] = last_valid[nan_mask]
                last_valid = array[index].copy()
        return array

    def missing_streams(self) -> List[str]:
        """返回尚未收到最新缓存的数据源。"""
        missing = [name for name, value in self.latest_images.items() if value is None]
        checks = {
            "arm_cmd": self.latest_arm_cmd,
            "arm_status": self.latest_arm_status,
        }
        if self.args.left_hand_state_topic:
            checks["left_hand_state"] = self.latest_left_hand_state
        if self.args.right_hand_state_topic:
            checks["right_hand_state"] = self.latest_right_hand_state
        missing.extend(name for name, value in checks.items() if value is None)
        return missing

    def _reset_histories(self) -> None:
        """清空本组历史，保留最新手部关节名用于 arm.npz 元信息。"""
        keep_names = {
            key: value
            for key, value in getattr(self, "histories", {}).items()
            if key.endswith("_names_latest")
        }
        self.histories = dict(keep_names)

    def next_session_dir(self) -> Path:
        base_dir = Path(self.args.output_dir).expanduser().resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        max_id = -1
        for child in base_dir.iterdir():
            if child.is_dir() and child.name.isdigit():
                max_id = max(max_id, int(child.name))
        return base_dir / f"{max_id + 1:04d}"

    def cleanup(self) -> None:
        self.running = False
        self.pending_start = False
        self.pending_start_sec = 0.0
        if self.is_recording:
            self.stop_recording()
        self.save_thread.join(timeout=1.0)


def parse_named_topic(value: str) -> Tuple[str, str]:
    """保留兼容参数，当前固定格式采集器暂不使用额外话题。"""
    if "=" not in value:
        raise argparse.ArgumentTypeError("额外话题必须使用 名称=话题 格式")
    name, topic = [item.strip() for item in value.split("=", 1)]
    if not name or not topic:
        raise argparse.ArgumentTypeError("名称和话题都不能为空")
    return name, topic


def build_arg_parser(
    description: str = "天工 VLA 固定频率数据采集脚本",
    default_output_dir: str = "/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data",
    default_left_hand_cmd_topic: str = "/inspire_hand/ctrl/left_hand",
    default_right_hand_cmd_topic: str = "/inspire_hand/ctrl/right_hand",
    default_left_hand_state_topic: str = "/inspire_hand/state/left_hand",
    default_right_hand_state_topic: str = "/inspire_hand/state/right_hand",
    default_left_hand_cmd_type: str = "joint_state",
    default_right_hand_cmd_type: str = "joint_state",
    default_left_hand_state_type: str = "joint_state",
    default_right_hand_state_type: str = "joint_state",
    default_left_hand_dof: int = 0,
    default_right_hand_dof: int = 0,
) -> argparse.ArgumentParser:
    """构建采集参数。"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--output-dir", default=default_output_dir, help="采集数据根目录")
    parser.add_argument("--target-hz", type=float, default=20.0, help="固定保存频率，默认 20Hz")
    parser.add_argument("--output-image-size", type=int, default=0, help="保存 PNG 的正方形边长；默认 0 表示保留相机输出尺寸")
    parser.add_argument("--head-topic", default="/camera/color/image_raw/compressed", help="头部相机 RGB 话题")
    parser.add_argument("--head-image-type", choices=["compressed_image", "compressed_video", "raw_image"], default="compressed_image", help="头部相机图像消息类型")
    parser.add_argument("--left-hand-image-topic", default="/camera/d405_left/color/image_h264", help="左手相机 RGB 话题")
    parser.add_argument("--left-hand-image-type", choices=["compressed_image", "compressed_video", "raw_image"], default="compressed_video", help="左手相机图像消息类型")
    parser.add_argument("--right-hand-image-topic", default="/camera/d405_right/color/image_h264", help="右手相机 RGB 话题")
    parser.add_argument("--right-hand-image-type", choices=["compressed_image", "compressed_video", "raw_image"], default="compressed_video", help="右手相机图像消息类型")
    parser.add_argument("--arm-cmd-topic", default="/arm/cmd_ctrl", help="机械臂 command 话题")
    parser.add_argument("--arm-status-topic", default="/arm/status", help="机械臂 state 话题")
    parser.add_argument("--left-hand-cmd-topic", default=default_left_hand_cmd_topic, help="左手/左夹爪 command 话题；为空则不订阅")
    parser.add_argument("--right-hand-cmd-topic", default=default_right_hand_cmd_topic, help="右手/右夹爪 command 话题；为空则不订阅")
    parser.add_argument("--left-hand-state-topic", default=default_left_hand_state_topic, help="左手/左夹爪 state 话题；为空则不订阅且不作为启动必需流")
    parser.add_argument("--right-hand-state-topic", default=default_right_hand_state_topic, help="右手/右夹爪 state 话题；为空则不订阅且不作为启动必需流")
    parser.add_argument("--left-hand-cmd-type", choices=["joint_state", "uint16"], default=default_left_hand_cmd_type, help="左手/左夹爪 command 消息类型")
    parser.add_argument("--right-hand-cmd-type", choices=["joint_state", "uint16"], default=default_right_hand_cmd_type, help="右手/右夹爪 command 消息类型")
    parser.add_argument("--left-hand-state-type", choices=["joint_state", "uint16"], default=default_left_hand_state_type, help="左手/左夹爪 state 消息类型")
    parser.add_argument("--right-hand-state-type", choices=["joint_state", "uint16"], default=default_right_hand_state_type, help="右手/右夹爪 state 消息类型")
    parser.add_argument("--left-hand-dof", type=int, default=default_left_hand_dof, help="左手/左夹爪保存的 position 自由度数；0 表示保存全部")
    parser.add_argument("--right-hand-dof", type=int, default=default_right_hand_dof, help="右手/右夹爪保存的 position 自由度数；0 表示保存全部")
    parser.add_argument("--button-topic", default="", help="外部按钮 JointState 话题；为空表示禁用按钮控制")
    parser.add_argument("--start-button-name", default="left_button", help="开始录制按钮名，优先按 name 匹配")
    parser.add_argument("--stop-button-name", default="right_button", help="停止录制按钮名，优先按 name 匹配")
    parser.add_argument("--start-button-index", type=int, default=0, help="开始录制按钮索引，按钮名不存在时使用")
    parser.add_argument("--stop-button-index", type=int, default=1, help="停止录制按钮索引，按钮名不存在时使用")
    parser.add_argument("--button-pressed-threshold", type=float, default=0.5, help="按钮按下阈值")
    parser.add_argument("--button-active-low", action=argparse.BooleanOptionalAction, default=True, help="按钮低电平按下；当前设备未按下为 1.0，默认启用")
    parser.add_argument("--button-debounce-sec", type=float, default=0.8, help="按钮触发消抖秒数")
    parser.add_argument("--checkpoint-interval-sec", type=float, default=1.0, help="录制中定期写 arm.npz 的间隔；小于等于 0 表示关闭")
    parser.add_argument("--auto-recover-streams", action=argparse.BooleanOptionalAction, default=True, help="等待启动时自动恢复缺失的相机流")
    parser.add_argument("--recover-after-sec", type=float, default=8.0, help="等待启动超过该秒数仍缺相机流时才自动恢复")
    parser.add_argument("--recover-interval-sec", type=float, default=20.0, help="自动恢复相机流的最小间隔秒数")
    parser.add_argument("--extra-joint-state-topic", dest="extra_joint_state_topics", type=parse_named_topic, action="append", default=[], help=argparse.SUPPRESS)
    return parser


def run_collector(args: argparse.Namespace) -> None:
    """运行采集节点。"""
    rclpy.init(args=None)
    node = VLACollectNode(args)
    try:
        while rclpy.ok() and node.running:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.cleanup()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

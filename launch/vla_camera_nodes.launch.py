#!/usr/bin/env python3
"""天工 VLA 相机节点启动 launch 文件。

这个 launch 文件在上位机运行，通过 ssh 分别在 n3/n2/n1 启动远端命令。
每个相机节点是独立 ExecuteProcess，行为更接近手动开多个终端分别启动。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
import shlex


def ssh_process(name: str, host: str, command: str) -> ExecuteProcess:
    """创建一个前台 ssh 进程，launch 退出时会关闭对应 ssh 会话。"""
    return ExecuteProcess(
        name=name,
        cmd=[
            "ssh",
            host,
            f"bash -lc {shlex.quote(command)}",
        ],
        output="screen",
        sigterm_timeout="5",
        sigkill_timeout="5",
    )


def head_camera_command() -> str:
    """按原稳定流程启动头部 Orbbec。"""
    return (
        "cd /home/nvidia/njd/button && "
        "source install/setup.bash && "
        "cd tool && "
        "exec ./start_camera.sh"
    )


def generate_launch_description() -> LaunchDescription:
    """生成 VLA 相机节点启动描述。"""
    move_head = LaunchConfiguration("move_head")
    hand_cameras = ssh_process(
        "vla_hand_cameras",
        "n3",
        "source /opt/ros/humble/setup.bash && cd /home/nvidia/njd && exec ./env_init.sh",
    )

    head_camera = ssh_process(
        "vla_head_camera",
        "n2",
        head_camera_command(),
    )

    move_head_once = ExecuteProcess(
        name="vla_move_head_once",
        condition=IfCondition(move_head),
        cmd=[
            "ssh",
            "n1",
            "bash -lc "
            + shlex.quote(
                "set +u; "
                "source /opt/ros/humble/setup.bash; "
                "[ -f /home/ubuntu/ros2ws/install/setup.bash ] && source /home/ubuntu/ros2ws/install/setup.bash; "
                "set -u; "
                "ros2 topic pub /head/cmd_pos bodyctrl_msgs/msg/CmdSetMotorPosition "
                "'{header: {stamp: {sec: 0, nanosec: 0}, frame_id: \"\"}, "
                "cmds: [{name: 2, pos: 0.3, spd: 0.1, cur: 0.2}]}' --once"
            ),
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "move_head",
                default_value="false",
                description="是否发布一次低头命令；属于机器人动作，默认关闭。",
            ),
            hand_cameras,
            head_camera,
            move_head_once,
        ]
    )

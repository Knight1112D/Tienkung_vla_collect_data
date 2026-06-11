# Tienkung VLA Data Collection

This project records VLA training data for Tienkung 2.0 PRO at a fixed sampling rate. It captures three RGB image streams, arm command/state positions, and dexterous-hand command/state positions, then saves them in the legacy VLA-compatible directory format. The final stable workflow starts camera/head nodes from the upper computer, records locally on the recording AGX into tmpfs, then uploads the episodes back to the upper computer.

## Hardware Topology

The physical system contains:

- A Tienkung 2.0 PRO robot with Inspire 6-DOF dexterous hands mounted on both arms.
- A homogeneous teleoperation arm system used for human demonstration during collection.
- An upper computer used to run the official teleoperation/collection software, start and stop robot-side camera nodes, and archive the final dataset.
- A robot x86 control computer used for ROS 2 control, arm/head commands, and robot state publishing.
- A recording AGX used to subscribe to the three image streams, arm topics, and hand topics, then write episodes to local `/dev/shm`.
- A camera AGX used to connect the left/right Intel RealSense D405 cameras and run the D405 image nodes plus h264 conversion processes.

Recording on the upper computer can occasionally stall when subscribing to remote image streams. For that reason, the stable workflow records on the recording AGX. Because AGX storage and memory are limited, episodes are first written to tmpfs and then uploaded to the upper computer for long-term storage.

## Quick Start

Start the camera nodes from the upper computer:

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

Use `--no-move-head` when the robot head is already in the desired pose. Remove it only when it is safe to send the head motion command.

Preview the three camera streams before recording:

```bash
python3 scripts/view_vla_cameras.py
```

If no GUI is available, save a preview image instead:

```bash
python3 scripts/view_vla_cameras.py --save-preview /tmp/vla_preview.jpg
```

Run the stable recorder on the recording AGX:

`n2` in the script name is a local deployment name; conceptually this script is the recording-AGX recorder.

```bash
cd /home/nvidia/cbc_tienkung2.0_vla_collect_data
bash scripts/n2_dual_hands_collect.sh --target-hz 20
```

Recorder controls:

- `1`: start recording; if any required stream is not ready yet, the recorder waits automatically and starts once all streams are available; missing camera streams trigger automatic recovery
- `2`: stop recording and save the episode; if the recorder is still waiting to start, this cancels the pending start
- `3`: delete the last saved episode
- `q`: quit

The recording AGX project lives in persistent storage at `/home/nvidia/cbc_tienkung2.0_vla_collect_data`, so it survives reboot. Episodes are written to tmpfs by default:

```text
/dev/shm/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands
```

Upload the recorded episodes to the upper computer and remove the local tmpfs copy from the recording AGX:

```bash
cd /home/nvidia/cbc_tienkung2.0_vla_collect_data
bash scripts/upload_n2_recorded_data.sh
```

The upload target is:

```text
/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands
```

The upper-computer recorder is still available as a fallback:

```bash
python3 scripts/dual_hands_collect.py --target-hz 20
```

## Camera Startup And Shutdown

Start all camera nodes:

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

Stop all VLA camera nodes before restarting them:

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
tmux kill-session -t vla_camera_launch 2>/dev/null || true
source /opt/ros/humble/setup.bash
ros2 daemon stop
ros2 daemon start
```

Then start again:

```bash
bash scripts/start_vla_nodes.sh --no-move-head
```

The launch flow starts:

- the head Orbbec camera on the recording AGX
- the left and right Intel RealSense D405 cameras on the camera AGX
- the D405 h264 conversion nodes
- optionally, a one-shot head-down command on the robot x86 control computer

## D405 USB Recovery

If a D405 camera is visible in `lsusb` but does not publish images, or if `rs-enumerate-devices` reports no usable device, reset the USB controller on the camera AGX.

On the upper computer, stop the current VLA nodes first:

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
tmux kill-session -t vla_camera_launch 2>/dev/null || true
```

On the camera AGX, reset the USB controller:

```bash
printf 'nvidia\n' | sudo -S bash -lc '
cd /sys/bus/platform/drivers/tegra-xusb
echo 3610000.usb > unbind
sleep 3
echo 3610000.usb > bind
sleep 8
lsusb
rs-enumerate-devices 2>/dev/null | grep -E "Name|Serial Number|Physical Port" || true
'
```

Expected D405 serial numbers:

- `353322271022`
- `230322275908`

After recovery, restart the nodes from the upper computer:

```bash
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/start_vla_nodes.sh --no-move-head
```

## Default Topics

Image streams:

- Head camera: `/camera/color/image_raw/compressed`
- Left hand camera: `/camera/d405_left/color/image_h264`
- Right hand camera: `/camera/d405_right/color/image_h264`

Arm streams:

- Arm command: `/arm/cmd_ctrl`
- Arm state: `/arm/status`

Hand streams:

- Left hand command: `/inspire_hand/ctrl/left_hand`
- Right hand command: `/inspire_hand/ctrl/right_hand`
- Left hand state: `/inspire_hand/state/left_hand`
- Right hand state: `/inspire_hand/state/right_hand`

`/arm/cmd_ctrl` is the command stream. `/arm/status` is the state stream. The recorder stores arm command positions and arm state positions separately.

## Output Format

Recordings are grouped by collection type first, then by numbered episode directories:

```text
vla_recorded_data/
  dual_hands/
    0000/
      head/
        000000.png
        ...
      hand_left/
        000000.png
        ...
      hand_right/
        000000.png
        ...
      arm.npz
  gripper/
    0000/
      head/
      hand_left/
      hand_right/
      arm.npz
```

`scripts/dual_hands_collect.py` writes to `dual_hands/` by default. `scripts/gripper_vla_collect.py` writes to `gripper/` by default. Use `--output-dir` to override either location.

Episode numbering continues from the largest numeric directory in the output folder. An empty folder starts at `0000`, then continues as `0001`, `0002`, and so on.

The GitHub repository keeps only one complete sample episode for format inspection, currently `vla_recorded_data/dual_hands/0000`. The upper computer may keep the full local collection sequence, such as `0000` through `0010`.

Main `arm.npz` fields:

- `cmd_positions`: arm command positions, normally shaped `(N, 14)`
- `status_positions`: arm state positions, normally shaped `(N, 14)`
- `left_hand_state_positions`, `right_hand_state_positions`: hand state positions
- `left_hand_cmd_positions`, `right_hand_cmd_positions`: hand command positions when available
- `*_image_seq`, `*_image_recv_sec`, `*_image_stamp_sec`: image-cache sequence and timing metadata

For arm state, only joint positions are written. Arm speed, current, temperature, and error fields are parsed internally but not saved to `arm.npz`.

The recorder no longer writes `samples.jsonl`, `summary.json`, `config.json`, or per-frame `state_npz/` files.

## D405 Hand Camera Mount Assets

The `assets/` directory contains Intel RealSense D405 camera-mount references for Tienkung 2.0 PRO with Inspire 6-DOF dexterous hands. The mount is placed near the wrist/hand so the D405 can observe the thumb-index web area and grasping region. It is fixed with two M3 screws.

Files:

- `camera_holder_dual_hands_l.jpg`: left-hand mount reference photo.
- `camera_holder_dual_hands_r.jpg`: right-hand mount reference photo.
- `d405_usb.jpg`: example D405 USB connection to the AGX.
- `tirnkung_wrist_camera.STL`: wrist D405 mount STL model.
- `2hand_camera.STL`: dual-hand camera mount STL model.

Before teleoperation or data collection, check screw length, finger clearance, camera-cable slack, and cable strain relief.

## Health Checks

```bash
source /opt/ros/humble/setup.bash

ros2 topic hz /camera/color/image_raw/compressed --window 30
ros2 topic hz /camera/d405_left/color/image_h264 --window 30
ros2 topic hz /camera/d405_right/color/image_h264 --window 30
ros2 topic hz /arm/cmd_ctrl --window 30
ros2 topic hz /arm/status --window 100
ros2 topic hz /inspire_hand/state/left_hand --window 50
ros2 topic hz /inspire_hand/state/right_hand --window 50
```

The collector can start once all three image streams, arm command/state, and hand state streams have received data. During recording it writes the latest cached snapshot at the requested fixed rate, typically 20 Hz.

New image or state messages replace the previous cache. If no newer image arrives before the next fixed-rate tick, the recorder may reuse the latest cached frame to keep the training sample rate stable. Image subscriptions use depth=1 best-effort QoS, and image callbacks only cache the latest raw payload; PNG decoding and disk writes happen in the save thread so old image messages do not build up in the ROS queue.

If `head`, `hand_left`, or `hand_right` is missing after pressing `1`, the recorder periodically calls `scripts/recover_vla_streams.sh` to recover the missing camera stream. The script can also be run manually.

Automatic recovery waits for a short grace period first, so newly starting camera streams are not restarted unnecessarily.

## Project Layout

- `cbc_tienkung_vla/collector.py`: shared fixed-rate collection logic
- `scripts/dual_hands_collect.py`: dual-hand recording entry point
- `scripts/gripper_vla_collect.py`: gripper collection template
- `scripts/view_vla_cameras.py`: three-camera preview tool
- `scripts/recover_vla_streams.sh`: camera-stream recovery helper used by the recorder while waiting to start
- `scripts/n2_dual_hands_collect.sh`: recording-AGX tmpfs recording wrapper with the required robot-side message environment; `n2` in the filename is a local deployment name
- `scripts/upload_n2_recorded_data.sh`: upload recording-AGX tmpfs episodes to the upper computer and delete the local copy after success; `n2` in the filename is a local deployment name
- `scripts/start_vla_nodes.sh`: camera startup wrapper
- `scripts/stop_vla_nodes.sh`: camera shutdown wrapper
- `launch/vla_camera_nodes.launch.py`: ROS 2 launch entry for remote camera startup
- `configs/`: example command-line configurations

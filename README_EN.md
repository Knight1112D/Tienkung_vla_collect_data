# Tienkung VLA Data Collection

This project runs on the Tienkung upper computer and records VLA training data at a fixed sampling rate. It captures three RGB image streams, arm command/state positions, and dexterous-hand command/state positions, then saves them in the legacy VLA-compatible directory format.

## Quick Start

Run the following commands on the upper computer:

```bash
ssh tienkung
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

Start the recorder:

```bash
python3 scripts/dual_hands_collect.py --target-hz 20
```

Recorder controls:

- `1`: start recording; if any required stream is not ready yet, the recorder waits automatically and starts once all streams are available; missing camera streams trigger automatic recovery
- `2`: stop recording and save the episode; if the recorder is still waiting to start, this cancels the pending start
- `3`: delete the last saved episode
- `q`: quit

Data is saved by default to:

```text
/home/ubuntu/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands
```

The default workflow records directly on the upper computer, so no n3 upload step is required.

If camera subscription on the upper computer stalls for a long time, record on n2 tmpfs instead:

```bash
ssh tienkung
ssh n2
cd /home/nvidia/cbc_tienkung2.0_vla_collect_data
bash scripts/n2_dual_hands_collect.sh --target-hz 20
```

After recording, upload the n2 data to the upper computer and remove the local n2 copy:

```bash
cd /home/nvidia/cbc_tienkung2.0_vla_collect_data
bash scripts/upload_n2_recorded_data.sh
```

The n2 project lives in persistent storage at `/home/nvidia/cbc_tienkung2.0_vla_collect_data`, so it survives reboot. Recorded episodes are written to `/dev/shm/cbc_tienkung2.0_vla_collect_data/vla_recorded_data/dual_hands` by default and are removed after a successful upload.

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

- the head Orbbec camera on `n2`
- the left and right Intel RealSense D405 cameras on `n3`
- the D405 h264 conversion nodes
- optionally, a one-shot head-down command on `n1`

## D405 USB Recovery

If a D405 camera is visible in `lsusb` but does not publish images, or if `rs-enumerate-devices` reports no usable device, reset the n3 USB controller:

```bash
ssh tienkung
cd /home/ubuntu/cbc_tienkung2.0_vla_collect_data
bash scripts/stop_vla_nodes.sh
tmux kill-session -t vla_camera_launch 2>/dev/null || true

ssh n3
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

After recovery, restart the nodes:

```bash
exit
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
- `scripts/n2_dual_hands_collect.sh`: n2 tmpfs recording wrapper with the required n2 message environment
- `scripts/upload_n2_recorded_data.sh`: upload n2 tmpfs recordings to the upper computer and delete the local copy after success
- `scripts/start_vla_nodes.sh`: camera startup wrapper
- `scripts/stop_vla_nodes.sh`: camera shutdown wrapper
- `launch/vla_camera_nodes.launch.py`: ROS 2 launch entry for remote camera startup
- `configs/`: example command-line configurations

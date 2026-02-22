# YOLO Object Detection — Add-on Documentation

This add-on runs a local YOLOv8 object detection server. It is used by the
**YOLO + LLM Vision** HACS integration to detect people, animals, vehicles,
and other objects in camera images before calling expensive AI analysis.

## Installation time

**Installation and first start can take a long time** (often several minutes).
The add-on has to build a Docker image and, on first run, download the YOLOv8
model (~6 MB for the default model). This is normal — later starts are much
faster. Wait for the add-on log to show “Sidecar ready” before configuring the
integration.

## How It Works

The add-on starts a FastAPI server on port 8000. The YOLO + LLM Vision
integration sends camera snapshots to this server, which runs YOLOv8
inference locally and returns what it found (detected classes, confidence,
bounding boxes).

Everything runs on your QNAP/HAOS machine. No images leave your network.

## Configuration

### Model

Which YOLOv8 model to use. Smaller models are faster, larger models are more
accurate.

| Model | Size | Speed | Use Case |
|---|---|---|---|
| `yolov8n.pt` | 6 MB | Fastest | Default — good for most cameras |
| `yolov8s.pt` | 22 MB | Fast | Better accuracy |
| `yolov8m.pt` | 50 MB | Moderate | Best accuracy (needs more RAM) |

The default `yolov8n.pt` is downloaded automatically on first start.

### Confidence Threshold

Minimum confidence score (0.1–1.0) for a detection to be accepted. Default is
0.5. Increase to reduce false positives, decrease to catch more objects.

### Log Level

Set to `debug` for verbose logging during troubleshooting.

## Integration Setup

After starting this add-on, configure the YOLO + LLM Vision integration:

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for "YOLO + LLM Vision"
3. For the sidecar URL, enter:

```
http://local-yolo-sidecar:8000
```

If that does not work, try:

```
http://addon_local_yolo_sidecar:8000
```

Or use your HAOS IP with the exposed port:

```
http://<your-haos-ip>:8000
```

## Verifying the Add-on

Check the add-on log tab — you should see:

```
Starting YOLO sidecar — model=yolov8n.pt, threshold=0.5
Sidecar ready — model=yolov8n.pt, threshold=0.50
```

## Supported Architectures

- amd64 (Intel/AMD NAS, most QNAP models)
- aarch64 (ARM-based devices)

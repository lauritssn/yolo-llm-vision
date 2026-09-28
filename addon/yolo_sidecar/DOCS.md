# RF-DETR Segmentation — Add-on Documentation

This add-on runs a local [Roboflow RF-DETR](https://github.com/roboflow/rf-detr) instance segmentation server. The **YOLO + LLM Vision** HACS integration sends camera snapshots here for local detection before optional AI threat analysis.

**Install from the Add-on Store:** **Settings > Add-ons > Add-on Store** → ⋮ → **Repositories** → add `https://github.com/lauritssn/yolo-llm-vision` → install **RF-DETR Segmentation**.

Full steps: [README](https://github.com/lauritssn/yolo-llm-vision#quick-start) and [docs/setup.md](https://github.com/lauritssn/yolo-llm-vision/blob/main/docs/setup.md).

## Installation time

**First install and start can take several minutes.** The add-on builds a Docker image and downloads RF-DETR weights on first run. This is normal — later starts are much faster. Wait for the log to show **Sidecar ready** before configuring the integration.

## How It Works

The add-on starts a FastAPI server on port **8000**. The integration POSTs images to `/detect` and receives:

- Detected classes and confidence
- Bounding boxes and segmentation metadata
- Optional annotated JPEG (light-green masks)

Everything runs locally. No images are sent to the cloud by the sidecar itself.

## Configuration

### Model

RF-DETR preset size. Smaller is faster; larger is more accurate.

| Preset | Speed | Use case |
|---|---|---|
| `nano` | Fastest | Default — good for most cameras and CPU |
| `small` | Fast | Better accuracy |
| `medium` | Moderate | Higher accuracy |
| `large` | Slower | Best open-source preset |

### Confidence Threshold

Minimum score (0.1–1.0) for a detection at the sidecar level. Default **0.5**. The integration sends its own threshold (default **0.6**) on each `/detect` call.

### Log Level

Set to `debug` for verbose logging during troubleshooting.

## Integration Setup

After starting this add-on:

1. **Settings > Devices & Services > Add Integration**
2. Search **YOLO + LLM Vision**
3. Sidecar URL — try in order:

```
http://local-yolo-sidecar:8000
http://addon_local_yolo_sidecar:8000
http://<your-haos-ip>:8000
```

4. Complete the wizard: cameras, AI Task, threat prompt, notifications

## Verifying the Add-on

Check the add-on **Log** tab:

```
Sidecar ready — task=segmentation, model=seg-nano, threshold=0.50
```

Or open `http://<ha-ip>:8000/health` and `http://<ha-ip>:8000/try`.

## Building locally

```bash
cd addon/yolo_sidecar
docker build -t rf-detr-sidecar:local .
docker run --rm -p 8000:8000 rf-detr-sidecar:local
```

## Supported Architectures

- amd64 (Intel/AMD NAS, most QNAP models)
- aarch64 (ARM-based devices)

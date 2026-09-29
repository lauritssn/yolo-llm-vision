# RF-DETR Sidecar — Docker Setup

The sidecar is a lightweight FastAPI service that runs [Roboflow RF-DETR](https://github.com/roboflow/rf-detr) **instance segmentation** locally. It accepts camera images and returns structured detection results with optional annotated images (light-green masks).

## Quick Start

```bash
cd sidecar
cp .env.example .env     # edit as needed
docker compose up -d
```

The service starts on port **8000** by default.

Open the interactive demo at **http://localhost:8000/try** (sample images included).

## API Reference

### POST /detect

Run instance segmentation on an image.

**Request body (JSON):**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `image_base64` | string | one of three | — | Base64-encoded JPEG/PNG |
| `image_url` | string | one of three | — | Public URL to fetch the image from |
| `entity_id` | string | one of three | — | HA camera entity ID (requires `ha_url` + `ha_token`) |
| `ha_url` | string | with entity_id | — | Home Assistant base URL |
| `ha_token` | string | with entity_id | — | Long-lived access token |
| `confidence_threshold` | float | no | env `CONFIDENCE_THRESHOLD` (0.5) | Minimum confidence (0.0–1.0) |
| `classes` | list[string] | no | all COCO classes | Class names to keep, e.g. `["person", "dog", "car"]` |
| `draw_boxes` | bool | no | true | Draw segmentation overlays, boxes, and labels |

**Response (JSON):**

```json
{
  "detected": true,
  "detection_count": 2,
  "classes_detected": ["person", "dog"],
  "confidence_max": 0.94,
  "confidence_avg": 0.88,
  "detections": [
    {
      "id": 0,
      "class": "person",
      "class_id": 0,
      "confidence": 0.94,
      "bbox": [120.5, 45.2, 380.1, 520.7],
      "segment": {
        "area_pixels": 45230,
        "area_percent": 12.4,
        "centroid": [250.1, 280.5],
        "polygon": [[120, 45], [380, 520]]
      }
    }
  ],
  "inference_time_ms": 23.4,
  "task": "segmentation",
  "model": {
    "engine": "rf-detr-seg",
    "preset": "seg-nano"
  },
  "image": {
    "width": 640,
    "height": 480
  },
  "annotated_image_base64": "..."
}
```

The `annotated_image_base64` field is present when `draw_boxes` is true **and** at least one object was detected. Masks use a light-green overlay.

### GET /health

Liveness check. Returns **HTTP 200** immediately when the server is up. On first start, `status` is `starting` while the RF-DETR model loads in the background; switches to `ok` when inference is ready.

```json
{
  "status": "ok",
  "model": "seg-nano",
  "engine": "rf-detr-seg",
  "task": "segmentation"
}
```

While loading:

```json
{
  "status": "starting",
  "model": "seg-nano",
  "engine": "rf-detr-seg",
  "task": "segmentation"
}
```

### GET /classes

Returns all COCO class names the model can detect:

```json
{"classes": ["person", "bicycle", "car", "..."]}
```

### GET /models

Lists active preset, available presets, and custom checkpoints in `MODELS_DIR`:

```json
{
  "active": "seg-nano",
  "task": "segmentation",
  "presets": ["nano", "small", "medium", "large"],
  "checkpoints": ["my-finetuned.pth"]
}
```

### GET /try

Interactive web page to test segmentation on bundled sample images.

## COCO Class Names

RF-DETR uses the COCO-80 dataset. Common classes for security cameras:

| Class | ID | Notes |
|---|---|---|
| person | 0 | People |
| car | 2 | |
| truck | 7 | |
| dog | 16 | |
| horse | 17 | Closest proxy for **deer** |
| cow | 19 | |
| bear | 21 | |
| cat | 15 | Often excluded for security |
| bird | 14 | Often excluded for security |

**Deer are not in COCO.** Deer may be classified as `horse`, `cow`, or missed. Add those classes as proxies, or use a custom `.pth` checkpoint via `RFDETR_CHECKPOINT`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RFDETR_MODEL` | `nano` | Preset: `nano`, `small`, `medium`, or `large` |
| `RFDETR_CHECKPOINT` | — | Optional custom `.pth` filename in `MODELS_DIR` |
| `MODELS_DIR` | `/models` | Directory for custom checkpoints |
| `CONFIDENCE_THRESHOLD` | `0.5` | Default threshold (integration overrides per request) |
| `PORT` | `8000` | Listen port |

See `sidecar/.env.example` for comments.

## Model Presets

| Preset | Speed | Accuracy | Use case |
|---|---|---|---|
| `nano` | Fastest | Good | Default, CPU-friendly |
| `small` | Fast | Better | Balanced |
| `medium` | Moderate | Great | When accuracy matters |
| `large` | Slower | Best preset | Maximum accuracy |

Weights download automatically on first run (cached under `~/.roboflow/models/`).

Place custom fine-tuned `.pth` files in `sidecar/models/` and set `RFDETR_CHECKPOINT`.

## GPU Support

Uncomment the GPU section in `docker-compose.yml` if you have NVIDIA Container Toolkit on the host. RF-DETR runs on CPU by default, which is fine for the Nano preset on most NAS hardware.

# YOLO Sidecar — Docker Setup

The YOLO sidecar is a lightweight FastAPI service that runs YOLOv8 inference locally. It accepts camera images and returns structured detection results with optional annotated images.

## Quick Start

```bash
cd sidecar
cp .env.example .env     # edit as needed

# CPU
docker compose up -d

# NVIDIA GPU — uncomment the GPU section in docker-compose.yml first
docker compose up -d
```

The service starts on port **8000** by default.

## API Reference

### POST /detect

Run object detection on an image.

**Request body (JSON):**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `image_base64` | string | one of three | — | Base64-encoded JPEG/PNG |
| `image_url` | string | one of three | — | Public URL to fetch the image from |
| `entity_id` | string | one of three | — | HA camera entity ID (requires `ha_url` + `ha_token`) |
| `ha_url` | string | with entity_id | — | Home Assistant base URL |
| `ha_token` | string | with entity_id | — | Long-lived access token |
| `confidence_threshold` | float | no | env `CONFIDENCE_THRESHOLD` (0.5) | Minimum confidence (0.0–1.0) |
| `classes` | list[string] | no | all 80 COCO classes | Object class names to detect, e.g. `["person", "dog", "car"]` |
| `draw_boxes` | bool | no | true | Draw labelled bounding boxes on the image |

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
      "class": "person",
      "class_id": 0,
      "confidence": 0.94,
      "bbox": [120.5, 45.2, 380.1, 520.7]
    },
    {
      "class": "dog",
      "class_id": 16,
      "confidence": 0.82,
      "bbox": [400.0, 300.0, 550.0, 480.0]
    }
  ],
  "inference_time_ms": 23.4,
  "annotated_image_base64": "..."
}
```

The `annotated_image_base64` field is only present when `draw_boxes` is true **and** at least one object was detected.

### GET /health

Returns `{"status": "ok", "model": "yolov8n.pt"}`.

### GET /classes

Returns all 80 COCO class names the model can detect:

```json
{"classes": ["person", "bicycle", "car", "..."]}
```

### GET /models

Lists `.pt` model files found in the `/models` volume.

## COCO Class Names

The standard YOLOv8 model uses the COCO-80 dataset. Some commonly used classes for security cameras:

| Class | ID | Notes |
|---|---|---|
| person | 0 | People |
| bicycle | 1 | |
| car | 2 | |
| motorcycle | 3 | |
| bus | 5 | |
| truck | 7 | |
| bird | 14 | Often excluded for security |
| cat | 15 | Often excluded for security |
| dog | 16 | |
| horse | 17 | Closest proxy for **deer** |
| cow | 19 | |
| bear | 21 | |

**Deer are not in the COCO dataset.** In practice, deer may be classified as `horse`, `cow`, or not detected at all. For reliable deer detection, consider a custom-trained YOLO model.

## Bounding Box Colors

Each class has a color-coded bounding box:

| Class | Color |
|---|---|
| person | Green |
| dog | Orange |
| car / truck | Red |
| Other | Cyan |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `YOLO_MODEL` | `yolov8n.pt` | Model file name (nano = fast, large = accurate) |
| `CONFIDENCE_THRESHOLD` | `0.5` | Default confidence threshold |
| `PORT` | `8000` | Listen port |

## GPU Support

Uncomment the GPU section in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

Requires NVIDIA Container Toolkit installed on the host.

## Model Options

| Model | Size | Speed | Accuracy | Use Case |
|---|---|---|---|---|
| `yolov8n.pt` | 6 MB | ~5ms GPU / ~30ms CPU | Good | Default, fast |
| `yolov8s.pt` | 22 MB | ~10ms GPU / ~60ms CPU | Better | Balanced |
| `yolov8m.pt` | 50 MB | ~20ms GPU / ~120ms CPU | Great | When accuracy matters |

Place custom models in the `sidecar/models/` directory.

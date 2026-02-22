# YOLO + LLM Vision — HACS Integration

Local object detection for Home Assistant cameras using a YOLOv8 Docker sidecar. Detects people, animals, vehicles and more — only calls expensive AI analysis when something relevant is actually there.

## How It Works

```
Camera Motion
     │
     ▼
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│  Camera   │────▶│ YOLO Sidecar │────▶│ Detection Result │
│ Snapshot  │     │ (local, free)│     │ person, dog, car │
└──────────┘     └──────────────┘     └────────┬────────┘
                                                │
                                     ┌──────────┴──────────┐
                                     │ Relevant object?     │
                                     │ (person, dog, etc.)  │
                                     └──────────┬──────────┘
                                          yes │        │ no
                                              ▼        ▼
                                     ┌────────────┐  (stop)
                                     │ AI Analysis │
                                     │ (optional)  │
                                     └──────┬─────┘
                                            ▼
                                     ┌────────────┐
                                     │ Notification│
                                     └────────────┘
```

**The YOLO sidecar runs locally — zero API costs.** The expensive AI call (OpenAI, LLM Vision, etc.) only runs when YOLO confirms a relevant detection. Empty frames, cats, and birds are filtered out before they cost you anything.

## Quick Start

### 1. Install the YOLO Sidecar

**Home Assistant OS** (QNAP VM, Raspberry Pi, etc.) — install as an add-on:

1. **Settings > Add-ons > Add-on Store** > three-dot menu (⋮) > **Repositories**
2. Add repository URL: `https://github.com/lauritssn/yolo-llm-vision` → **Add** → **Close**
3. In the Add-on Store, find **YOLO Object Detection** → **Install**
4. Open the add-on → **Start**

The first install can take several minutes (image build and model download). Wait until the add-on **Log** shows “Sidecar ready” before configuring the integration.

**Docker installs** (HA Container, no add-ons):

```bash
cd sidecar
cp .env.example .env
docker compose up -d
```

See [docs/setup.md](docs/setup.md) for full details on both methods.

### 2. Install the Integration (HACS)

1. Go to **HACS > Integrations**
2. Open the three-dot menu (⋮) → **Custom repositories**
3. **Repository:** `https://github.com/lauritssn/yolo-llm-vision`
4. **Type:** **Integration**
5. Click **Add**
6. In HACS, go to **Integrations** → **Explore & Download** (or **+**), search for **YOLO + LLM Vision** → **Download**
7. **Restart Home Assistant**
8. Go to **Settings > Devices & Services > Add Integration** → search **YOLO + LLM Vision** → configure

### 3. Configure

Go to **Settings > Devices & Services > Add Integration > YOLO + LLM Vision**.

| Setting | Description |
|---|---|
| Sidecar URL | `http://<your-host>:8000` |
| Cameras | Select one or more camera entities |
| Confidence threshold | Minimum confidence to trigger (default: 0.6) |
| Detection classes | Which objects to detect: person, dog, car, etc. |
| Draw bounding boxes | Overlay colored boxes on detections |

### 4. Import the Blueprint

Go to **Settings → Automations → Blueprints → Import Blueprint** and paste:

```
https://github.com/lauritssn/yolo-llm-vision/blob/main/blueprints/automation/yolo_llm_vision/camera_event_pipeline.yaml
```

Or copy the file to `config/blueprints/automation/yolo_llm_vision/`.

## Blueprint: Camera Security Pipeline

The blueprint replaces manual automations with a configurable pipeline:

1. **Trigger** — an HA event or motion sensor
2. **Snapshot** — grabs the camera image
3. **YOLO gate** — runs local detection, stops if nothing relevant found
4. **AI analysis** (optional) — calls `ai_task.generate_data` for detailed threat assessment
5. **Notification** — sends Telegram message + photo, with threat/all-clear distinction

### Blueprint Inputs

| Input | Description |
|---|---|
| Camera | Camera entity to snapshot |
| Trigger type | Event name or motion binary_sensor |
| AI Task entity | e.g. `ai_task.openai_ai_task` (leave empty to skip AI) |
| AI instructions | Custom prompt for the AI analysis |
| Telegram notifications | Toggle Telegram messages + photos |
| Alternative notify service | e.g. `notify.mobile_app_phone` |
| Cooldown | Seconds between triggers |

### Mapping to Your Automation

Your current automation flow maps directly to the blueprint:

| Your automation step | Blueprint equivalent |
|---|---|
| `trigger: event` → `test_shed_camera_ai` | Input: trigger event type |
| `camera.snapshot` | Built-in, takes snapshot automatically |
| `ai_task.generate_data` | Input: AI Task entity + instructions |
| `telegram_bot.send_message` / `send_photo` | Built-in, controlled by toggle |
| `THREAT DETECTED` condition | Built-in threat/all-clear branching |

## Detection Classes

The sidecar uses standard COCO-80 classes. Configure which ones trigger a detection:

| Common classes | ID | Default |
|---|---|---|
| person | 0 | yes |
| dog | 16 | yes |
| car | 2 | yes |
| truck | 7 | yes |
| horse | 17 | yes |
| cow | 19 | yes |
| bear | 21 | yes |
| cat | 15 | no (excluded) |
| bird | 14 | no (excluded) |

**Note on deer:** COCO does not include deer. Deer may be classified as `horse` or `cow` by the standard model. For reliable deer detection, add `horse` to your detection classes or use a custom YOLO model.

## Entities Created

For each configured camera:

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.yolo_detection_*` | Binary Sensor | On when YOLO detects a configured class |
| `sensor.yolo_confidence_*` | Sensor | Highest detection confidence (%) |
| `sensor.yolo_detection_count_*` | Sensor | Number of detections |
| `sensor.yolo_classes_*` | Sensor | Comma-separated detected class names |
| `sensor.yolo_last_detected_*` | Sensor | Timestamp of last detection |
| `sensor.yolo_llm_summary_*` | Sensor | LLM analysis text (only if LLM configured) |
| `image.yolo_annotated_*` | Image | Last annotated snapshot with bounding boxes |

## Service: yolo_llm_vision.analyze

Call manually or from automations:

```yaml
action: yolo_llm_vision.analyze
data:
  entity_id: camera.front_door
  force_llm: false
response_variable: result
```

Returns:

```yaml
detected: true
confidence: 0.94
detection_count: 2
classes_detected:
  - person
  - dog
last_seen: "2026-02-22T15:30:00+00:00"
llm_summary: "A person walking a large dog..."  # only if LLM enabled
```

## Events

When a detection occurs, the integration fires `yolo_llm_vision_detection`:

```yaml
event_type: yolo_llm_vision_detection
data:
  entity_id: camera.front_door
  detected: true
  confidence: 0.94
  detection_count: 2
  classes_detected: ["person", "dog"]
  last_seen: "2026-02-22T15:30:00+00:00"
```

## FAQ

**Q: Can it detect deer?**
A: The standard COCO model does not have a "deer" class. Deer might be detected as `horse` or `cow`. Add those to your detection classes as a proxy, or train/use a custom YOLO model.

**Q: Does the AI analysis require LLM Vision?**
A: No. The blueprint uses `ai_task.generate_data` which works with any AI Task provider (OpenAI, Google, Anthropic, etc.). The LLM Vision integration is a separate optional feature in the integration settings.

**Q: Can I use this without AI analysis at all?**
A: Yes. Leave the AI Task entity empty in the blueprint and you get YOLO-only detection with Telegram notifications showing what was detected.

**Q: How fast is the YOLO detection?**
A: 5–30ms on GPU, 30–120ms on CPU depending on the model size. Much faster than any cloud API call.

## Development & testing

- **Unit tests** (no YOLO model): from project root run `uv sync --extra test` then `uv run pytest tests/`. See `tests/` and `pyproject.toml` optional deps.
- **Integration tests** (real YOLO model, `_run_inference`): you need the YOLO weights and the sidecar running locally. See **[docs/integration-testing.md](docs/integration-testing.md)** for:
  - How to **download the YOLO model** (automatic on first run, or manual `curl` into `sidecar/models/`)
  - Installing sidecar deps and running the sidecar locally
  - Running integration tests against the live sidecar

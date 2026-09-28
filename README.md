# RF-DETR + LLM Vision — HACS Integration

Local object detection for Home Assistant cameras using a [Roboflow RF-DETR](https://github.com/roboflow/rf-detr) sidecar. Detects people, animals, vehicles and more — only calls expensive AI analysis when something relevant is actually there.

## How It Works

```
Camera Motion
     │
     ▼
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│  Camera   │────▶│ RF-DETR Sidecar│──▶│ Detection Result │
│ Snapshot  │     │ (local, free)  │   │ person, dog, car │
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

**The RF-DETR sidecar runs locally — zero API costs.** The expensive AI call (OpenAI, LLM Vision, etc.) only runs when RF-DETR confirms a relevant detection. Empty frames, cats, and birds are filtered out before they cost you anything.

## Quick Start

### 1. Install the RF-DETR Sidecar

**Home Assistant OS** (QNAP VM, Raspberry Pi, etc.) — install as an add-on:

1. **Settings > Add-ons > Add-on Store** > three-dot menu (⋮) > **Repositories**
2. Add repository URL: `https://github.com/lauritssn/rf-detr-vision` → **Add** → **Close**
3. In the Add-on Store, find **RF-DETR Segmentation** → **Install**
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
3. **Repository:** `https://github.com/lauritssn/rf-detr-vision`
4. **Type:** **Integration**
5. Click **Add**
6. In HACS, go to **Integrations** → **Explore & Download** (or **+**), search for **RF-DETR + LLM Vision** → **Download**
7. **Restart Home Assistant**
8. Go to **Settings > Devices & Services > Add Integration** → search **RF-DETR + LLM Vision** → configure

### 3. Configure

Go to **Settings > Devices & Services > Add Integration > RF-DETR + LLM Vision**. Setup is a four-step wizard; reopen **Configure** on the integration anytime to edit a section.

**Sidecar**

| Setting | Description |
|---|---|
| Sidecar URL | `http://<your-host>:8000` |

**Cameras & detection**

| Setting | Description |
|---|---|
| Cameras | One or more camera entities to monitor |
| Confidence threshold | Minimum confidence to trigger (default: 0.6) |
| Detection classes | COCO classes that pass the gate (person, dog, car, …) |
| Draw overlays | Segmentation masks on saved snapshots |
| Save annotated images | Write snapshots to `/config/media/rf_detr_vision/` |

**AI threat analysis**

| Setting | Description |
|---|---|
| AI Task entity | e.g. `ai_task.openai_ai_task` (ChatGPT via Home Assistant AI Task) |
| AI Task name | Task name passed to `ai_task.generate_data` |
| Threat analysis prompt | Instructions for the AI (editable; default matches the blueprint) |
| Threat phrase | Text that means “threat” in the AI reply (default: `THREAT DETECTED`) |
| LLM Vision provider | Optional fallback if AI Task is not configured |

**Notifications**

| Setting | Description |
|---|---|
| Notify service | e.g. `telegram_bot.send_message` or `notify.mobile_app_phone` |
| Notify on threat | Send when AI includes the threat phrase (or on detection-only if AI is off) |
| Notify on all clear | Send when AI runs but no threat phrase is found |
| Threat / all-clear titles | Prefix for notification titles |
| Attach photo | Sends annotated snapshot via Telegram when enabled |

When configured, the integration runs the full pipeline itself: camera snapshot → RF-DETR gate → AI Task threat analysis → threat or all-clear notification. The blueprint below is optional if you prefer automations.

### 4. Import the Blueprint (optional)

If you use the integration configuration above, you do not need the blueprint. Use it when you want the same pipeline inside a custom automation instead.

Go to **Settings → Automations → Blueprints → Import Blueprint** and paste:

```
https://github.com/lauritssn/rf-detr-vision/blob/main/blueprints/automation/rf_detr_vision/camera_event_pipeline.yaml
```

Or copy the file to `config/blueprints/automation/rf_detr_vision/`.

## Blueprint: Camera Security Pipeline

The blueprint replaces manual automations with a configurable pipeline:

1. **Trigger** — an HA event or motion sensor
2. **Snapshot** — grabs the camera image
3. **RF-DETR gate** — runs local segmentation, stops if nothing relevant found
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

**Note on deer:** COCO does not include deer. Deer may be classified as `horse` or `cow` by the standard model. Add those classes as proxies, or use a custom RF-DETR checkpoint via `RFDETR_CHECKPOINT`.

## Entities Created

For each configured camera:

| Entity | Type | Description |
|---|---|---|
| `binary_sensor.rf_detr_vision_*_detected` | Binary Sensor | On when RF-DETR detects a configured class |
| `sensor.rf_detr_vision_*_confidence` | Sensor | Highest detection confidence (%) |
| `sensor.rf_detr_vision_*_detection_count` | Sensor | Number of detections |
| `sensor.rf_detr_vision_*_classes` | Sensor | Comma-separated detected class names |
| `sensor.rf_detr_vision_*_last_detected` | Sensor | Timestamp of last detection |
| `sensor.rf_detr_vision_*_llm_summary` | Sensor | AI analysis text (when AI Task / LLM enabled) |
| `image.rf_detr_vision_*_annotated` | Image | Last annotated snapshot with segmentation overlays |

## Service: rf_detr_vision.analyze

Call manually or from automations:

```yaml
action: rf_detr_vision.analyze
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
ai_analysis: "Person walking a dog. THREAT DETECTED"  # when AI Task / LLM enabled
threat_detected: true
llm_summary: "Person walking a dog. THREAT DETECTED"  # same text as ai_analysis
```

## Events

When a detection occurs, the integration fires `rf_detr_vision_detection`:

```yaml
event_type: rf_detr_vision_detection
data:
  entity_id: camera.front_door
  detected: true
  confidence: 0.94
  detection_count: 2
  classes_detected: ["person", "dog"]
  last_seen: "2026-02-22T15:30:00+00:00"
```

## Upgrading from v2 (YOLO-named integration)

Version **3.0.0** renames everything to match RF-DETR:

| v2 (remove) | v3 (use) |
|---|---|
| Domain `yolo_llm_vision` | `rf_detr_vision` |
| Service `yolo_llm_vision.analyze` | `rf_detr_vision.analyze` |
| Add-on slug `yolo_sidecar` | `rf_detr_sidecar` |
| Sidecar URL `http://local-yolo-sidecar:8000` | `http://local-rf-detr-sidecar:8000` |
| HACS custom repo `…/yolo-llm-vision` | `…/rf-detr-vision` |

1. Remove the old **YOLO + LLM Vision** integration from HA.
2. Uninstall the old **YOLO** add-on (if used).
3. Update your HACS custom repository URL to `https://github.com/lauritssn/rf-detr-vision`.
4. Install **RF-DETR + LLM Vision** and the **RF-DETR Segmentation** add-on.
5. Reconfigure cameras, AI Task, and notifications.
6. Update automations: service `rf_detr_vision.analyze`, event `rf_detr_vision_detection`.

## FAQ

**Q: Can it detect deer?**
A: COCO has no deer class. Deer may appear as `horse` or `cow`. Add those classes, or use a custom RF-DETR `.pth` checkpoint.

**Q: Does the AI analysis require LLM Vision?**
A: No. Configure **AI Task** in the integration wizard — it uses `ai_task.generate_data` with any AI Task provider (OpenAI, Google, Anthropic, etc.). LLM Vision is an optional fallback.

**Q: Can I use this without AI analysis at all?**
A: Yes. Leave the AI Task entity empty in the integration config. You still get RF-DETR detection and optional detection-only notifications when **Notify on threat** is enabled.

**Q: How fast is RF-DETR detection?**
A: RF-DETR Nano runs in ~2–30ms on GPU and ~50–200ms on CPU depending on hardware. Much faster than any cloud API call.

**Q: Can I try detection without Home Assistant?**
A: Yes. Start the sidecar and open `http://localhost:8000/try` for an interactive demo with sample images.

## Development & testing

- **Unit tests** (no RF-DETR model): from project root run `uv sync --extra test` then `uv run pytest tests/`.
- **Live sidecar tests**: start the sidecar locally and use `/try` or POST `/detect`. See **[docs/integration-testing.md](docs/integration-testing.md)** for RF-DETR model download, env vars, and curl examples.

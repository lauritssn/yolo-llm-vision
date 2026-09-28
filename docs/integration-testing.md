# Integration Testing (RF-DETR Sidecar with Real Model)

Integration tests run the sidecar with a real [RF-DETR](https://github.com/roboflow/rf-detr) model and call `_run_inference`. Weights download automatically on first run.

## 1. Get the RF-DETR model

### Option A: Automatic download (recommended)

The `rfdetr` package downloads weights the first time you load a model preset. You do **not** need to download anything by hand.

1. Install the sidecar dependencies (see below).
2. Run the sidecar or an integration test once. When the code runs `RFDETRNano()`, weights are cached under `~/.roboflow/models/`.

No extra steps required.

### Option B: Custom fine-tuned checkpoint

Place a `.pth` checkpoint in `sidecar/models/` (or `/models` in Docker) and set:

```bash
export RFDETR_CHECKPOINT=my-model.pth
export MODELS_DIR=/path/to/sidecar/models
```

### Model size presets

Set `RFDETR_MODEL` to one of:

| Preset | Size (approx) | Use case |
|--------|---------------|----------|
| `nano` (default) | ~350 MB | Fastest, CPU-friendly |
| `small` | ~370 MB | Better accuracy |
| `medium` | ~390 MB | Higher accuracy |
| `large` | ~400 MB | Best open-source preset |

## 2. Install sidecar dependencies

From the project root:

```bash
cd sidecar
uv venv
uv pip install -r requirements.txt
```

## 3. Run the sidecar locally

```bash
cd sidecar
source .venv/bin/activate
python main.py
```

Optional env vars:

- `RFDETR_MODEL` — `nano`, `small`, `medium`, or `large` (default: `nano`)
- `RFDETR_CHECKPOINT` — custom `.pth` filename in `MODELS_DIR`
- `CONFIDENCE_THRESHOLD` — default `0.5`
- `PORT` — default `8000`

4. Check health and try the demo:

   ```bash
   curl http://localhost:8000/health
   open http://localhost:8000/try
   ```

5. Test inference using bundled fixture images in `tests/fixtures/images/`:

   | File | Expected detections |
   |------|---------------------|
   | `bus.jpg` | person, bus |
   | `zidane.jpg` | person |
   | `empty.jpg` | none (negative test) |

   ```bash
   curl -X POST http://localhost:8000/detect \
     -H "Content-Type: application/json" \
     -d '{"image_base64":"'$(base64 -i tests/fixtures/images/bus.jpg)'", "confidence_threshold": 0.5}'
   ```

## 4. Run integration tests that use the model

- **Unit tests** (no model): from project root, `uv run pytest tests/`.
- **Live sidecar tests**: start the sidecar locally, then POST to `/detect` or use the `/try` demo page.

Summary:

1. **Model**: automatic on first run, or custom `.pth` via `RFDETR_CHECKPOINT`.
2. **Install deps**: `uv pip install -r sidecar/requirements.txt`.
3. **Run sidecar**: `python main.py` from `sidecar/`.
4. **Test**: `/try` demo page or curl to `/detect`.

## 5. Test the Home Assistant pipeline (RF-DETR + AI Task + Telegram)

Use this checklist after the integration, sidecar add-on, and cameras are configured.

### Step A — Sidecar only (no Home Assistant)

1. Open `http://<sidecar-host>:8000/try` and upload `bus.jpg` or `zidane.jpg`.
2. Confirm masks and classes appear. Use `empty.jpg` to confirm no false positives.

### Step B — Dry run (Developer Tools)

1. Go to **Developer Tools → Services**.
2. Call **`rf_detr_vision.test_pipeline`**:

```yaml
service: rf_detr_vision.test_pipeline
data:
  entity_id: camera.driveway
  send_notifications: false
  bypass_detection_gate: false
  force_ai: true
  use_camera_snapshot: true
  snapshot_delay_seconds: 2
```

This mirrors the security blueprint: **`camera.snapshot`** → wait → read JPEG from `/config/www/` → RF-DETR → AI Task → notify.

3. Check the response JSON:
   - `steps.sidecar_health.ok` — sidecar reachable
   - `steps.snapshot.ok` — camera frame grab worked
   - `steps.snapshot.method` — should be `camera.snapshot` (or `async_get_image` if snapshot failed)
   - `steps.snapshot.snapshot_path` — path to the saved JPEG on disk
   - `steps.detection.gate_passed` — RF-DETR found something relevant
   - `steps.ai_task.ok` — OpenAI AI Task responded
   - `steps.notification.reason` — should say dry run

### Step C — Test ChatGPT without standing in front of the camera

Set `bypass_detection_gate: true` so AI runs even when the driveway is empty:

```yaml
service: rf_detr_vision.test_pipeline
data:
  entity_id: camera.driveway
  send_notifications: false
  bypass_detection_gate: true
  force_ai: true
```

Confirm `steps.ai_task.ran` is true and `response_preview` looks sensible.

### Step D — Live notifications (Telegram)

```yaml
service: rf_detr_vision.test_pipeline
data:
  entity_id: camera.driveway
  send_notifications: true
  bypass_detection_gate: true
  notification_prefix: "[TEST] "
```

You should receive:

1. A production-style alert or all-clear (when detection gate passes or is bypassed).
2. A second **Pipeline test** summary message prefixed with `[TEST]`.

Verify the snapshot photo is attached if **Send snapshot photo** is enabled in integration options.

### Step E — One-click self-test blueprint

Import the self-test blueprint:

```
https://raw.githubusercontent.com/lauritssn/yolo-llm-vision/main/blueprints/automation/rf_detr_vision/pipeline_self_test.yaml
```

1. **Settings → Automations → Create automation → Import blueprint**.
2. Select **RF-DETR Pipeline Self-Test**.
3. Choose your **Driveway** camera and enable **Send real notifications**.
4. Save the automation.
5. Open the automation and click **Run actions** (runs immediately without waiting for motion).

A persistent notification in Home Assistant shows the summary when enabled.

### Step F — Full security blueprint (motion/event)

Import the production blueprint:

```
https://raw.githubusercontent.com/lauritssn/yolo-llm-vision/main/blueprints/automation/rf_detr_vision/camera_event_pipeline.yaml
```

1. Configure **Driveway** camera, motion sensors, OpenAI AI Task, and Telegram as in your setup.
2. Trigger real motion or fire your camera event from Developer Tools.
3. Confirm RF-DETR gates expensive AI — check logs for detection before AI Task runs.
4. Confirm threat vs all-clear titles match your blueprint settings.

### Step G — Listen for test completion event

Developer Tools → **Events** → listen to `rf_detr_vision_test_complete`.

Each `test_pipeline` run fires this event with the full report payload (useful for debugging automations).

### Quick reference

| Goal | Service / action |
|------|------------------|
| RF-DETR only | `rf_detr_vision.analyze` with `entity_id` |
| Full pipeline dry run | `rf_detr_vision.test_pipeline`, `send_notifications: false` |
| Test Telegram + AI | `test_pipeline`, `send_notifications: true`, `bypass_detection_gate: true` |
| One-click in UI | Self-test blueprint → **Run actions** |
| Production flow | Security blueprint on motion/event |

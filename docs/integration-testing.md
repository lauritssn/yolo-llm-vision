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

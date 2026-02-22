# Integration Testing (YOLO Sidecar with Real Model)

Integration tests run the sidecar with a real YOLOv8 model and call `_run_inference`. You need the YOLO weights and the sidecar’s Python dependencies installed locally.

## 1. Get the YOLO model

Two options: **automatic** (recommended) or **manual**.

### Option A: Automatic download (recommended)

The Ultralytics library downloads the model the first time you load it. You do **not** need to download anything by hand.

1. Install the sidecar dependencies (see below).
2. Run the sidecar or an integration test once. When the code runs `YOLO("yolov8n.pt")`, Ultralytics will:
   - Download `yolov8n.pt` (~6.5 MB) from the Ultralytics CDN
   - Cache it (e.g. under `~/.config/Ultralytics` or `~/.cache/ultralytics`)

No extra steps required.

### Option B: Manual download

Use this if you want a specific file location (e.g. a `./models` folder) or to avoid downloads at test time.

1. Create a directory for weights, e.g. `sidecar/models` or `/models` if you mirror the add-on layout:

   ```bash
   mkdir -p sidecar/models
   cd sidecar/models
   ```

2. Download the default model (nano, good for CPU):

   ```bash
   # yolov8n.pt (~6.5 MB) — fastest, good for integration tests
   curl -L -o yolov8n.pt "https://huggingface.co/Ultralytics/YOLOv8/resolve/main/yolov8n.pt"
   ```

3. Tell the sidecar to use this directory by setting `MODELS_DIR` and `YOLO_MODEL` when you run it (see “Run the sidecar locally” below). If the path is `./sidecar/models` and the file is `yolov8n.pt`, set:

   - `MODELS_DIR=/path/to/sidecar/models`
   - `YOLO_MODEL=yolov8n.pt`

   so that `MODELS_DIR / YOLO_MODEL` points at the downloaded file.

Other sizes (if you want to test a larger model later):

| Model        | File        | Size (approx) | Use case        |
|-------------|-------------|---------------|------------------|
| Nano (default) | `yolov8n.pt` | ~6.5 MB   | Fast, CPU-friendly |
| Small       | `yolov8s.pt` | ~22 MB    | Better accuracy  |
| Medium      | `yolov8m.pt` | ~52 MB    | Higher accuracy  |

Same URLs, replace the filename (e.g. `yolov8s.pt`, `yolov8m.pt`).

## 2. Install sidecar dependencies

We use **uv** for Python. From the project root:

```bash
cd sidecar
uv venv
uv pip install -r requirements.txt
```

This installs at least: `ultralytics`, `fastapi`, `uvicorn`, `opencv-python-headless`, `httpx`, `numpy`, `Pillow`, `python-multipart`.

## 3. Run the sidecar locally

So that integration tests (or manual calls) hit real inference:

1. From the `sidecar` directory (so `main.py` and, if you use one, `models/` are in place):

   ```bash
   cd sidecar
   ```

2. Optional env vars:

   - `YOLO_MODEL` — model filename (default: `yolov8n.pt`).
   - `MODELS_DIR` — directory that contains the `.pt` file. If unset, the code uses `/models`; if that path doesn’t exist or doesn’t contain the file, it uses the name only and Ultralytics will download it (Option A).
   - `PORT` — default `8000`.
   - `CONFIDENCE_THRESHOLD` — default `0.5`.

   Example (manual model path):

   ```bash
   export MODELS_DIR="$(pwd)/models"
   export YOLO_MODEL=yolov8n.pt
   source .venv/bin/activate && python main.py
   ```

   Or let Ultralytics download on first run (with venv active):

   ```bash
   source .venv/bin/activate && python main.py
   ```

3. Activate the venv and start the app:

   ```bash
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   python main.py
   ```

   Or with uvicorn:

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

4. Check health and classes (no image needed):

   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/classes
   ```

5. Test inference (example with a small base64 image or an image URL):

   ```bash
   curl -X POST http://localhost:8000/detect \
     -H "Content-Type: application/json" \
     -d '{"image_base64":"'$(base64 -i /path/to/test.jpg)'", "confidence_threshold": 0.5}'
   ```

Once this works, the same setup is what you use for integration tests that call the sidecar’s `/detect` (and thus `_run_inference`) with a real model.

## 4. Run integration tests that use the model

- **Unit tests** (no model): from project root, `uv run pytest tests/` (or `pytest tests/`). These do **not** download or use YOLO.
- **Integration tests** that hit `_run_inference`: start the sidecar locally (step 3) so it loads the real model, then run your integration test suite against `http://localhost:8000` (e.g. a test that POSTs to `/detect` with a small test image and asserts on the JSON). You can use a separate pytest marker or script that is only run when the sidecar is up and you want to test with the real model.

Summary:

1. **Download YOLO**: use automatic (first run) or manual download into e.g. `sidecar/models/yolov8n.pt`.
2. **Install deps**: `pip install -r sidecar/requirements.txt` (or uv equivalent) in the `sidecar` directory.
3. **Run sidecar**: `cd sidecar`, activate the venv (`source .venv/bin/activate`), then `python main.py` (set `MODELS_DIR`/`YOLO_MODEL` if you use a manual path).
4. **Integration test**: run tests that POST to the sidecar’s `/detect` endpoint; the sidecar will use `_run_inference` with the real YOLO model.

# Installation and Setup

You need two things: the **YOLO sidecar** (runs detection) and the **YOLO + LLM Vision** integration (connects HA to the sidecar). Install the sidecar first, then the integration via HACS.

| Step | What | Where |
|------|------|--------|
| 1 | YOLO sidecar | Add-on Store (HAOS) or Docker (see below) |
| 2 | YOLO + LLM Vision integration | HACS → Custom repositories → Type: **Integration** |
| 3 | Configure | Settings > Devices & Services > Add Integration |
| 4 | (Optional) Blueprint | Settings > Automations & Scenes > Blueprints > Import |

## Prerequisites

1. **Home Assistant** 2025.1.0 or newer
2. **HACS** installed ([instructions](https://hacs.xyz/docs/use/))
3. At least one **camera entity** in Home Assistant
4. Optional: **AI Task** integration (OpenAI, Google, etc.) for the blueprint's AI analysis

## Step 1: Install the YOLO Sidecar

The YOLO sidecar runs YOLOv8 object detection locally. Choose the installation
method that matches your HA setup.

### Home Assistant OS (Recommended — QNAP VM, Raspberry Pi, etc.)

On HAOS, the sidecar runs as a **Home Assistant add-on** — installed and managed
directly from the HA UI.

#### Option A: Add-on Repository (Recommended)

1. Go to **Settings > Add-ons > Add-on Store**
2. Click the three-dot menu (top right) > **Repositories**
3. Add: `https://github.com/lauritssn/yolo-llm-vision`
4. Click **Add** then **Close**
5. Find **YOLO Object Detection** in the store and click **Install**
6. **Important:** The first build can take **5–15 minutes** (Debian base image and PyTorch download). Do not cancel.
7. When installation finishes, open the add-on → **Configuration** tab (optional):
   - **Model**: `yolov8n.pt` (default, fastest) or `yolov8s.pt` (more accurate)
   - **Confidence threshold**: `0.5` (default)
8. Click **Start**
9. Check the **Log** tab — wait until you see:
   ```
   Starting YOLO sidecar — model=yolov8n.pt, threshold=0.5
   Sidecar ready — model=yolov8n.pt, threshold=0.50
   ```
   The first start also downloads the YOLO model (~6 MB). After that, starts are fast.

#### Option B: Local Add-on (No GitHub Needed)

If you prefer not to add a repository, copy the add-on files directly to your
HAOS instance.

1. Access your HAOS config directory via Samba, SSH, or the File Editor add-on
2. Create the folder: `addons/yolo_sidecar/`
3. Copy everything from this repo's `addon/yolo_sidecar/` into that folder:
   ```
   addons/yolo_sidecar/
   ├── build.yaml
   ├── config.yaml
   ├── Dockerfile
   ├── main.py
   ├── requirements.txt
   └── run.sh
   ```
4. Go to **Settings > Add-ons > Add-on Store**
5. Click the three-dot menu > **Check for updates**
6. Find **YOLO Object Detection** under **Local add-ons** and install it
7. Configure and start as above

#### Sidecar URL for the Integration

When configuring the YOLO + LLM Vision integration, use one of these URLs
for the sidecar:

| URL to try | When to use |
|---|---|
| `http://local-yolo-sidecar:8000` | Internal Docker hostname (try first) |
| `http://addon_local_yolo_sidecar:8000` | Alternative internal hostname |
| `http://<your-HAOS-IP>:8000` | Fallback — uses the exposed port |

The first option works in most HAOS setups. If it fails during integration
setup, try the next one.

### Docker / Docker Compose (HA Container Installations)

If you run HA Container (plain Docker, not HAOS), add-ons are not available.
Run the sidecar as a regular Docker container instead.

#### Add to Your Existing HA Compose File

Add the `yolo-sidecar` service to the same `docker-compose.yml` as your
`homeassistant` container:

```yaml
services:
  homeassistant:
    # ... your existing HA config ...

  yolo-sidecar:
    build:
      context: /path/to/yolo-llm-vision/sidecar
      dockerfile: Dockerfile
    container_name: yolo-sidecar
    ports:
      - "8000:8000"
    volumes:
      - /path/to/yolo-llm-vision/sidecar/models:/models
    environment:
      - YOLO_MODEL=yolov8n.pt
      - CONFIDENCE_THRESHOLD=0.5
    restart: unless-stopped
```

```bash
docker compose up -d
```

Sidecar URL depends on your HA network mode:

| HA network_mode | Sidecar URL |
|---|---|
| `host` | `http://localhost:8000` |
| bridge (default) | `http://yolo-sidecar:8000` |

#### Standalone Compose File

```bash
cd yolo-llm-vision/sidecar
cp .env.example .env
docker compose up -d
```

If HA and the sidecar are in different compose files on the same machine,
create a shared Docker network so they can find each other:

```bash
docker network create ha-network
```

Add `networks: [ha-network]` to both compose files (under each service and
as a top-level `networks:` block with `external: true`). Then use
`http://yolo-sidecar:8000`.

### Verify the Sidecar

From the HA host or from the add-on log tab:

```bash
curl http://localhost:8000/health
# {"status":"ok","model":"yolov8n.pt"}

curl http://localhost:8000/classes
# {"classes":["person","bicycle","car",...]}
```

## Step 2: Install the Integration via HACS

1. Open Home Assistant and go to **HACS > Integrations**
2. Click the three-dot menu (⋮) > **Custom repositories**
3. **Repository:** enter `https://github.com/lauritssn/yolo-llm-vision`
4. **Type:** select **Integration**
5. Click **Add**, then close the dialog
6. Go to **HACS > Integrations** → **Explore & Download** (or the **+** button), search for **YOLO + LLM Vision**, then **Download**
7. **Restart Home Assistant**
8. Go to **Settings > Devices & Services > Add Integration**, search for **YOLO + LLM Vision**, and complete the configuration (see Step 3)

## Step 3: Configure the Integration

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for "YOLO + LLM Vision"
3. Fill in the settings:

| Setting | What to enter |
|---|---|
| Sidecar URL | See the URL table above for your setup |
| Cameras | Select camera entities to monitor |
| Confidence threshold | 0.6 is a good starting point |
| Detection classes | Pick objects to detect: person, dog, car, etc. |
| Draw bounding boxes | Toggle on for annotated snapshots |
| Save annotated images | Toggle on to save to `/media` |
| LLM Vision provider | Only shown if LLM Vision is installed — optional |
| Notification service | e.g. `notify.mobile_app_phone` — optional |

4. Click **Submit**

## Step 4: Import the Blueprint (Optional)

For the full security pipeline (YOLO gate + AI analysis + Telegram):

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Click **Import Blueprint**
3. Paste:
   ```
   https://github.com/lauritssn/yolo-llm-vision/blob/main/blueprints/automation/yolo_llm_vision/camera_event_pipeline.yaml
   ```

See [blueprint.md](blueprint.md) for how to configure the blueprint inputs.

## Changing Settings

### Integration Settings

**Settings > Devices & Services** > find YOLO + LLM Vision > **Configure**

### Add-on Settings (HAOS Only)

**Settings > Add-ons** > YOLO Object Detection > **Configuration** tab

## Testing

### Developer Tools

1. Go to **Developer Tools > Services**
2. Select `yolo_llm_vision.analyze`
3. Enter a camera entity ID
4. Click **Call Service**
5. Check the response and entity states

### Direct API Test

```bash
IMAGE_B64=$(base64 -i test_image.jpg)

curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d "{\"image_base64\": \"$IMAGE_B64\", \"classes\": [\"person\", \"dog\"]}"
```

## Troubleshooting

### Add-on won't start (HAOS)

Check the add-on **Log** tab. Common issues:

- **Out of memory**: The YOLO model needs RAM. `yolov8n.pt` needs ~300 MB;
  larger models need more. Ensure your QNAP VM has enough memory allocated.
- **Build failed / takes very long**: The first build downloads a Debian base image and PyTorch (several hundred MB). It can take **5–15 minutes** (longer on aarch64). Let it finish; later updates are faster.

### "Connection refused" in integration setup

The sidecar URL is wrong or the container is not running.

On HAOS, try each URL from the table above. The internal hostname depends on
how the Supervisor names the container.

On Docker, remember that `localhost` from inside the HA container is the
container itself, not the host. Use the container name or host IP.

### Slow detection

- Use `yolov8n.pt` (fastest model)
- QNAP NAS CPUs are typically Intel Celeron/Atom — expect 50–150ms per frame
- If your QNAP has an NVIDIA GPU (unlikely for most models), enable GPU in the
  sidecar config

### Debug logging (service returns `error: true`)

To see exactly where the integration fails (e.g. no HTTP request reaching the sidecar), enable debug logging:

1. In `configuration.yaml` add:

```yaml
logger:
  default: warning
  logs:
    custom_components.yolo_llm_vision: debug
```

2. Restart Home Assistant.
3. Call the `yolo_llm_vision.analyze` service again.
4. Check **Settings > System > Logs** (or your HA log file). You will see:
   - When the service is called and with what data
   - The sidecar URL from config/options
   - Whether a config entry is loaded
   - Snapshot fetch and size
   - The exact sidecar URL, HTTP method, and payload size
   - The raw HTTP response or full exception traceback if the request fails

Use the last debug line before an exception to see where it failed (e.g. fetching snapshot vs. calling the sidecar).

## Uninstalling

1. Remove the integration from **Settings > Devices & Services**
2. Stop/uninstall the add-on from **Settings > Add-ons** (HAOS)
   — or `docker compose down` (Docker)
3. Uninstall from HACS
4. Restart Home Assistant

# Installation and Setup

You need two things: the **RF-DETR sidecar** (runs local segmentation) and the **RF-DETR + LLM Vision** integration (connects HA to the sidecar and runs the full pipeline). Install the sidecar first, then the integration via HACS.

| Step | What | Where |
|------|------|--------|
| 1 | RF-DETR sidecar | Add-on Store (HAOS) or Docker (see below) |
| 2 | RF-DETR + LLM Vision integration | HACS → Custom repositories → Type: **Integration** |
| 3 | Configure | Settings > Devices & Services → Add Integration (4-step wizard) |
| 4 | (Optional) Blueprint | Only if you want the pipeline in a custom automation |

## Prerequisites

1. **Home Assistant** 2025.1.0 or newer
2. **HACS** installed ([instructions](https://hacs.xyz/docs/use/))
3. At least one **camera entity** in Home Assistant
4. Optional: **AI Task** integration (OpenAI, Google, etc.) for threat analysis
5. Optional: **Telegram Bot** or other **notify** service

## Step 1: Install the RF-DETR Sidecar

The sidecar runs [Roboflow RF-DETR](https://github.com/roboflow/rf-detr) instance segmentation locally. Choose the method that matches your HA setup.

### Home Assistant OS (Recommended)

On HAOS, the sidecar runs as a **Home Assistant add-on**.

#### Option A: Add-on Repository (Recommended)

1. Go to **Settings > Add-ons > Add-on Store**
2. Click the three-dot menu (top right) > **Repositories**
3. Add: `https://github.com/lauritssn/yolo-llm-vision`
4. Click **Add** then **Close**
5. Find **RF-DETR Segmentation** in the store and click **Install**
6. **Important:** The first build can take **5–15 minutes** (image build and model download). Do not cancel.
7. When installation finishes, open the add-on → **Configuration** tab (optional):
   - **Model**: `nano` (default, fastest) or `small` / `medium` / `large` (more accurate)
   - **Confidence threshold**: `0.5` (default; the integration overrides this when calling `/detect`)
8. Click **Start**
9. Check the **Log** tab — wait until you see something like:
   ```
   Sidecar ready — task=segmentation, model=seg-nano, threshold=0.50
   ```

#### Option B: Local Add-on (No GitHub Needed)

1. Access your HAOS config directory via Samba, SSH, or the File Editor add-on
2. Create the folder: `addons/rf_detr_sidecar/`
3. Copy everything from this repo's `rf_detr_sidecar/` folder into that folder
4. Go to **Settings > Add-ons > Add-on Store**
5. Click the three-dot menu > **Check for updates**
6. Find **RF-DETR Segmentation** under **Local add-ons** and install it
7. Configure and start as above

#### Sidecar URL for the Integration

On **Home Assistant OS**, leave **Sidecar URL** empty during setup — the integration auto-detects the add-on via the Supervisor API using its internal Docker hostname (not `localhost`).

| Install source | Internal hostname pattern | Example URL |
|---|---|---|
| Local add-on folder | `local-rf-detr-sidecar` | `http://local-rf-detr-sidecar:8000` |
| GitHub add-on store | `{repo-hash}-rf-detr-sidecar` | Auto-detected (varies per repo) |

You only need a manual URL for **Docker/container** Home Assistant without Supervisor, e.g. `http://rf-detr-sidecar:8000` on a shared Docker network.

Verify from **Terminal & SSH** add-on (inside HA):

```bash
curl http://local-rf-detr-sidecar:8000/health
```

Or use the auto-detected URL shown in the integration setup wizard.

### Docker / Home Assistant Container

If you run HA in Docker without add-ons, run the sidecar separately:

```bash
cd sidecar
cp .env.example .env
docker compose up -d
```

See [sidecar.md](sidecar.md) for API details and environment variables.

**Sidecar URL from HA:** use the Docker service name (e.g. `http://rf-detr-sidecar:8000`) or the host IP — not `localhost` from inside the HA container.

## Step 2: Install the Integration (HACS)

1. Go to **HACS > Integrations**
2. Open the three-dot menu (⋮) → **Custom repositories**
3. **Repository:** `https://github.com/lauritssn/yolo-llm-vision`
4. **Type:** **Integration** → **Add**
5. Go to **HACS > Integrations** → **Explore & Download** → search **RF-DETR + LLM Vision** → **Download**
6. **Restart Home Assistant**
7. Go to **Settings > Devices & Services > Add Integration**, search for **RF-DETR + LLM Vision**

### Manual install (no HACS)

Copy `custom_components/rf_detr_vision/` to your HA `config/custom_components/` folder and restart.

## Step 3: Configure the Integration

Adding the integration opens a **four-step wizard**. You can reopen **Configure** on the integration card anytime to edit one section.

### Sidecar

| Setting | What to enter |
|---|---|
| Sidecar URL | See the URL table above |

### Cameras & detection

| Setting | What to enter |
|---|---|
| Cameras | Camera entities to monitor |
| Confidence threshold | 0.6 is a good starting point |
| Detection classes | person, dog, car, truck, etc. |
| Draw overlays | Light-green segmentation masks on snapshots |
| Save annotated images | Saves to `/config/media/rf_detr_vision/` |

### AI threat analysis

| Setting | What to enter |
|---|---|
| AI Task entity | e.g. `ai_task.openai_ai_task` |
| AI Task name | Passed to `ai_task.generate_data` |
| Threat analysis prompt | Full instructions for the AI (editable) |
| Threat phrase | Text meaning “threat” in the reply (default: `THREAT DETECTED`) |
| LLM Vision provider | Optional fallback if AI Task is not set |

When configured, the integration runs: snapshot → RF-DETR gate → AI Task analysis → threat or all-clear notification. You do **not** need the blueprint for this.

### Notifications

| Setting | What to enter |
|---|---|
| Notify service | e.g. `telegram_bot.send_message` or `notify.mobile_app_phone` |
| Notify on threat | Send when AI includes the threat phrase |
| Notify on all clear | Send when AI runs but no threat is found |
| Threat / all-clear titles | Notification title prefixes |
| Attach photo | Sends annotated snapshot via Telegram when enabled |

## Step 4: Import the Blueprint (Optional)

Use the blueprint only if you want the same pipeline inside a **custom automation** instead of the built-in integration flow.

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Click **Import Blueprint**
3. Paste:
   ```
   https://github.com/lauritssn/yolo-llm-vision/blob/main/blueprints/automation/rf_detr_vision/camera_event_pipeline.yaml
   ```

See [blueprint.md](blueprint.md) for blueprint inputs.

## Changing Settings

### Integration settings

**Settings > Devices & Services** → RF-DETR + LLM Vision → **Configure** → pick a section (Sidecar, Cameras, AI analysis, Notifications).

### Add-on settings (HAOS only)

**Settings > Add-ons** → **RF-DETR Segmentation** → **Configuration** tab (model size, default threshold, log level).

## Testing

### Developer Tools

1. Go to **Developer Tools > Services**
2. Select `rf_detr_vision.analyze`
3. Enter a camera entity ID
4. Click **Call Service**
5. Check the response for `detected`, `ai_analysis`, and `threat_detected`

### Try page (no Home Assistant)

With the sidecar running, open `http://<sidecar-host>:8000/try` in a browser.

### Direct API test

```bash
IMAGE_B64=$(base64 -i tests/fixtures/images/bus.jpg)

curl -X POST http://localhost:8000/detect \
  -H "Content-Type: application/json" \
  -d "{\"image_base64\": \"$IMAGE_B64\", \"classes\": [\"person\", \"bus\"]}"
```

## Troubleshooting

### Add-on won't start (HAOS)

Check the add-on **Log** tab. Common issues:

- **Health check failed on first start**: Fixed in add-on **3.0.1+** — the HTTP server starts immediately and loads the model in the background. Update the add-on, uninstall/reinstall if needed, then wait for `Sidecar ready` in the log (model load can take several minutes on QNAP CPU).
- **Out of memory**: RF-DETR Nano needs roughly 1–2 GB RAM during inference. Use `nano` on low-memory systems.
- **NumPy X86_V2 error on QNAP/QEMU VM**: Use add-on **3.0.5+**, which pins NumPy 1.26 on Python 3.11 (Bookworm base). NumPy 2.x wheels require x86-64-v2. Enable CPU host passthrough in the VM if possible.
- **Docker build fails compiling NumPy**: Use add-on **3.0.7+** (Bookworm / Python 3.11). Version 3.0.5–3.0.6 used Trixie Python 3.13, which has no NumPy 1.26 wheel.
- **Build failed / takes very long**: First build downloads PyTorch and dependencies. Let it finish; later updates are faster.

### "Connection refused" in integration setup

The sidecar URL is wrong or the container is not running. Try each URL from the table above.

On Docker HA, `localhost` inside the HA container is not the host — use the sidecar container name or host IP.

### Slow detection

- Use add-on model preset `nano`
- CPU-only NAS hardware often sees 50–200 ms per frame — still faster than cloud APIs

### Debug logging

```yaml
logger:
  default: warning
  logs:
    custom_components.rf_detr_vision: debug
```

Restart HA, call `rf_detr_vision.analyze`, then check **Settings > System > Logs**.

## Uninstalling

1. Remove the integration from **Settings > Devices & Services**
2. Stop/uninstall the add-on (HAOS) or `docker compose down` (Docker)
3. Uninstall from HACS
4. Restart Home Assistant

# Blueprint: Camera Security Pipeline

The blueprint provides a camera security automation: motion trigger, RF-DETR detection gate, optional AI analysis, and Telegram/notification output.

> **Prefer integration config:** If you configure **AI Task**, **threat prompt**, and **notifications** in **Settings > Devices & Services > RF-DETR + LLM Vision > Configure**, the integration runs the full pipeline automatically. Use this blueprint only when you need triggers, cooldowns, or custom automation logic the integration does not cover.

## What It Does

```
Trigger (event or motion sensor)
     │
     ▼
Camera snapshot saved to /config/www/
     │
     ▼
rf_detr_vision.analyze
  → sends image to RF-DETR sidecar
  → returns: detected classes, confidence, count
     │
     ▼
Relevant object detected?
     │
  no └──▶ (stop — no notification, no AI cost)
     │
  yes
     │
     ▼
AI Task entity configured?
     │
  no └──▶ Send detection-only notification
  yes
     │
     ▼
ai_task.generate_data
  → sends camera image + your instructions
  → returns AI analysis text
     │
     ▼
"THREAT DETECTED" in response?
     │
  yes └──▶ SECURITY ALERT + photo via Telegram
     │
  no  └──▶ All Clear + photo via Telegram
```

## Prerequisites

1. **rf_detr_vision** integration configured with sidecar URL + cameras
2. **Camera entity** in Home Assistant
3. A **trigger**: custom HA event or motion binary_sensor
4. Optional: **AI Task** integration for detailed analysis
5. Optional: **Telegram Bot** for notifications

## Installing the Blueprint

Install the sidecar and integration first — see [Installation and Setup](setup.md).

### From URL

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Click **Import Blueprint**
3. Paste:
   ```
   https://github.com/lauritssn/rf-detr-vision/blob/main/blueprints/automation/rf_detr_vision/camera_event_pipeline.yaml
   ```

### Manual Copy

```
config/blueprints/automation/rf_detr_vision/camera_event_pipeline.yaml
```

## Blueprint Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| Camera | yes | — | Camera entity to snapshot |
| Trigger type | yes | event | "Event", "Motion sensor", or "Both" |
| Trigger event name | if event/both | — | HA event type |
| Trigger event name 2 / 3 | no | — | Additional event types |
| Motion sensor(s) | if motion/both | — | One or more binary_sensor entities |
| AI Task entity | no | — | e.g. `ai_task.openai_ai_task` |
| AI Task name | no | "Security Camera Analysis" | Name for logging |
| AI instructions | no | (default prompt) | Full prompt for AI analysis |
| Snapshot delay | no | 2 seconds | Wait for camera to write the file |
| Threat notification title | no | "SECURITY ALERT" | Title when AI detects a threat |
| Clear notification title | no | "All Clear" | Title when AI finds nothing |
| Send Telegram | no | true | Toggle Telegram messages |
| Send photo with Telegram | no | true | Attach snapshot |
| Alternative notify service | no | — | e.g. `notify.mobile_app_phone` |
| Cooldown | no | 30 seconds | Min time between triggers |

## Integration config vs blueprint

| Feature | Integration config | Blueprint |
|---|---|---|
| RF-DETR gate | Yes (via service / motion listener) | Yes |
| AI Task + threat prompt | Yes — stored in integration | Yes — per automation |
| Threat / all-clear notify | Yes — stored in integration | Yes — per automation |
| Custom triggers & cooldown | Limited (camera state changes) | Full control |

## Three Operating Modes

### 1. Integration-only (recommended)

Configure everything in the integration wizard. Call `rf_detr_vision.analyze` from automations if you need extra triggers, or rely on camera state listening.

### 2. Full blueprint pipeline

Import the blueprint and set AI Task + Telegram inputs. RF-DETR gates the AI call; AI response determines threat/all-clear.

### 3. Service-only custom automation

```yaml
- action: rf_detr_vision.analyze
  data:
    entity_id: camera.front_door
  response_variable: result

- condition: template
  value_template: "{{ result.threat_detected }}"

# Your custom logic here...
```

## Detection Classes

Configure classes in **Settings > Devices & Services > RF-DETR + LLM Vision > Configure > Cameras & detection**. Default includes person, dog, car, truck, horse, cow, and bear.

The blueprint and service use whatever classes the integration is configured to detect. If RF-DETR finds none of those classes above the confidence threshold, analysis stops before any AI call.

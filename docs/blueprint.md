# Blueprint: Camera Security Pipeline

The blueprint provides a complete camera security automation: motion trigger, YOLO detection gate, optional AI analysis, and Telegram/notification output.

## What It Does

```
Trigger (event or motion sensor)
     │
     ▼
Camera snapshot saved to /config/www/
     │
     ▼
yolo_llm_vision.analyze
  → sends image to YOLO sidecar
  → returns: detected classes, confidence, count
     │
     ▼
YOLO detected relevant object?
     │
  no └──▶ (stop — no notification, no AI cost)
     │
  yes
     │
     ▼
AI Task entity configured?
     │
  no └──▶ Send YOLO-only Telegram notification
     │       "person, dog detected (94% confidence)"
  yes
     │
     ▼
ai_task.generate_data
  → sends camera image + your instructions to OpenAI/etc.
  → returns AI analysis text
     │
     ▼
"THREAT DETECTED" in response?
     │
  yes └──▶ 🚨 SECURITY ALERT + photo via Telegram
     │
  no  └──▶ ✅ All Clear + photo via Telegram
```

## Prerequisites

1. **yolo_llm_vision** integration configured with sidecar URL + cameras
2. **Camera entity** in Home Assistant
3. A **trigger**: either a custom HA event or a motion binary_sensor
4. Optional: **AI Task** integration (OpenAI, Google, etc.) for detailed analysis
5. Optional: **Telegram Bot** integration for notifications

## Installing the Blueprint

### From URL

1. Go to **Settings > Automations & Scenes > Blueprints**
2. Click **Import Blueprint**
3. Paste:
   ```
   https://github.com/lauritssn/yolo-llm-vision/blob/main/blueprints/automation/yolo_llm_vision/camera_event_pipeline.yaml
   ```

### Manual Copy

Copy `blueprints/automation/yolo_llm_vision/camera_event_pipeline.yaml` to your HA config:

```
config/blueprints/automation/yolo_llm_vision/camera_event_pipeline.yaml
```

## Blueprint Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| Camera | yes | — | Camera entity to snapshot |
| Trigger type | yes | event | "Event" or "Motion sensor" |
| Trigger event name | if event | — | HA event type, e.g. `shed_camera_motion` |
| Motion sensor entity | if motion | — | Binary sensor entity |
| AI Task entity | no | — | e.g. `ai_task.openai_ai_task`. Leave empty to skip AI. |
| AI Task name | no | "Security Camera Analysis" | Descriptive name for logging |
| AI instructions | no | (default prompt) | Full prompt for the AI analysis |
| Snapshot delay | no | 2 seconds | Wait for camera to write the file |
| Threat notification title | no | "SECURITY ALERT" | Title when AI detects a threat |
| Clear notification title | no | "All Clear" | Title when AI finds nothing |
| Send Telegram | no | true | Toggle Telegram messages |
| Send photo with Telegram | no | true | Attach snapshot to Telegram |
| Alternative notify service | no | — | e.g. `notify.mobile_app_phone` |
| Cooldown | no | 30 seconds | Min time between triggers |

## Example: Reproducing Your Shed Camera Automation

Your original automation:

```yaml
triggers:
  - event_type: test_shed_camera_ai
    trigger: event
actions:
  - camera.snapshot → ai_task.generate_data → telegram notification
```

Blueprint equivalent — create an automation from the blueprint with these inputs:

| Input | Value |
|---|---|
| Camera | `camera.ds_7608ni_i20820180626ccrrc31559009wcvu_201` |
| Trigger type | Event |
| Trigger event name | `test_shed_camera_ai` |
| AI Task entity | `ai_task.openai_ai_task` |
| AI Task name | `Shed Camera Security Analysis` |
| AI instructions | (paste your existing instructions from the automation) |
| Send Telegram | true |
| Send photo with Telegram | true |

The difference: between the snapshot and the AI call, YOLO now checks whether a person, dog, or other configured object is actually in the frame. If the frame is empty (or only shows cats/birds), the AI call is skipped entirely.

## Three Operating Modes

### 1. Full pipeline (YOLO + AI + Telegram)

Set all inputs. YOLO gates the AI call. AI response determines threat/all-clear.

### 2. YOLO + Telegram (no AI)

Leave the AI Task entity empty. You get Telegram notifications showing what YOLO detected, with confidence and class names. No AI cost at all.

### 3. YOLO gate + custom automation

Use the `yolo_llm_vision.analyze` service directly in your own automation instead of the blueprint. The service returns detection data you can branch on however you like:

```yaml
- action: yolo_llm_vision.analyze
  data:
    entity_id: camera.front_door
  response_variable: yolo_result

- condition: template
  value_template: "{{ 'person' in yolo_result.classes_detected }}"

# Your custom logic here...
```

## Detection Classes

The integration config determines which object classes YOLO reports. The default is `person` and `dog`. Change this in **Settings > Devices & Services > YOLO + LLM Vision > Configure**.

The blueprint uses whatever classes the integration is configured to detect. If YOLO finds none of those classes, the automation stops before the AI call.

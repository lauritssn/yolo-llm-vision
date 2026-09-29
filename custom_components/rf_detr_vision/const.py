"""Constants for the RF-DETR + LLM Vision integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rf_detr_vision"

# Config keys — sidecar & detection
CONF_SIDECAR_URL = "sidecar_url"

ADDON_SLUG = "rf_detr_sidecar"
ADDON_PORT = 8000
DATA_DISCOVERED_SIDECAR_URL = "discovered_sidecar_url"
CONF_CAMERAS = "cameras"
CONF_CONFIDENCE_THRESHOLD = "confidence_threshold"
CONF_DETECTION_CLASSES = "detection_classes"
CONF_DRAW_BOXES = "draw_boxes"
CONF_SAVE_ANNOTATED = "save_annotated_image"

# Config keys — AI threat analysis
CONF_AI_TASK_ENTITY = "ai_task_entity"
CONF_AI_TASK_NAME = "ai_task_name"
CONF_THREAT_PROMPT = "threat_analysis_prompt"
CONF_THREAT_PHRASE = "threat_phrase"

# Legacy LLM Vision (optional alternative to AI Task)
CONF_LLM_PROVIDER = "llm_provider"
CONF_LLM_PROMPT = "llm_prompt"

# Config keys — notifications
CONF_NOTIFY_SERVICE = "notify_service"
CONF_NOTIFY_ON_THREAT = "notify_on_threat"
CONF_NOTIFY_ON_ALL_CLEAR = "notify_on_all_clear"
CONF_THREAT_TITLE = "threat_notification_title"
CONF_CLEAR_TITLE = "all_clear_notification_title"
CONF_NOTIFY_INCLUDE_PHOTO = "notify_include_photo"

# Defaults
DEFAULT_SIDECAR_URL = ""
DEFAULT_CONFIDENCE = 0.6
DEFAULT_DETECTION_CLASSES = ["person", "dog", "car", "truck", "horse", "cow", "bear"]
DEFAULT_AI_TASK_NAME = "Security Camera Analysis"
DEFAULT_THREAT_PHRASE = "THREAT DETECTED"
DEFAULT_THREAT_PROMPT = (
    "Analyze this image from a security camera.\n\n"
    "Report ONLY on:\n"
    "1. PERSONS/PEOPLE - any humans visible\n"
    "2. BIG ANIMALS - large dogs, deer, or other large animals (NOT cats or small animals)\n"
    "3. CARS/VEHICLES - but ONLY if they are NOT parked in the driveway\n\n"
    "Provide a brief description of what you see.\n\n"
    "IMPORTANT: If you detect any person, big animal, or non-parked vehicle, "
    'end your response with exactly: "THREAT DETECTED"\n\n'
    "If there are NO threats, describe the scene neutrally WITHOUT adding any conclusion."
)
DEFAULT_PROMPT = DEFAULT_THREAT_PROMPT  # backward compatibility
DEFAULT_THREAT_TITLE = "SECURITY ALERT"
DEFAULT_CLEAR_TITLE = "All Clear"
DEFAULT_NOTIFY_ON_THREAT = True
DEFAULT_NOTIFY_ON_ALL_CLEAR = True
DEFAULT_NOTIFY_INCLUDE_PHOTO = False

DETECTION_CLASS_OPTIONS = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
    "boat",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "bear",
    "backpack",
    "umbrella",
    "handbag",
    "suitcase",
]

EVENT_DETECTION = "rf_detr_vision_detection"
EVENT_TEST_COMPLETE = "rf_detr_vision_test_complete"

SERVICE_TEST_PIPELINE = "test_pipeline"
DEFAULT_TEST_NOTIFICATION_PREFIX = "[TEST] "
DEFAULT_SNAPSHOT_DELAY = 2

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.IMAGE,
]

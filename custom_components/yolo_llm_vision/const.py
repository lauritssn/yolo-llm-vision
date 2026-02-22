"""Constants for the YOLO + LLM Vision integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "yolo_llm_vision"

# Config keys
CONF_SIDECAR_URL = "sidecar_url"
CONF_CAMERAS = "cameras"
CONF_CONFIDENCE_THRESHOLD = "confidence_threshold"
CONF_DETECTION_CLASSES = "detection_classes"
CONF_DRAW_BOXES = "draw_boxes"
CONF_SAVE_ANNOTATED = "save_annotated_image"
CONF_LLM_PROVIDER = "llm_provider"
CONF_LLM_PROMPT = "llm_prompt"
CONF_NOTIFY_SERVICE = "notify_service"

# Defaults
DEFAULT_SIDECAR_URL = "http://localhost:8000"
DEFAULT_CONFIDENCE = 0.6
DEFAULT_DETECTION_CLASSES = ["person", "dog", "car", "truck", "horse", "cow", "bear", "wolf"]
DEFAULT_PROMPT = (
    "Describe what you see. Focus on people — what are they doing, "
    "what are they wearing, do they appear to be a threat or acting unusually?"
)

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
    "wolf",  # not in COCO-80; for custom models only
    "backpack",
    "umbrella",
    "handbag",
    "suitcase",
]

EVENT_DETECTION = "yolo_llm_vision_detection"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.IMAGE,
]

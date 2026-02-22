"""Tests for config flow _build_schema and validation."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.yolo_llm_vision.config_flow import _build_schema
from custom_components.yolo_llm_vision.const import (
    CONF_CAMERAS,
    CONF_LLM_PROMPT,
    CONF_LLM_PROVIDER,
    CONF_SIDECAR_URL,
)


def _schema_keys(schema: vol.Schema) -> set[str]:
    """Extract logical key names from a voluptuous Schema."""
    keys = set()
    for key in schema.schema:
        if hasattr(key, "schema"):
            keys.add(key.schema)
        elif isinstance(key, str):
            keys.add(key)
    return keys


def test_build_schema_returns_schema_with_required_keys() -> None:
    schema = _build_schema()
    keys = _schema_keys(schema)
    assert CONF_SIDECAR_URL in keys
    assert CONF_CAMERAS in keys


def test_build_schema_show_llm_true_includes_llm_keys() -> None:
    schema = _build_schema(show_llm=True)
    keys = _schema_keys(schema)
    assert CONF_LLM_PROVIDER in keys
    assert CONF_LLM_PROMPT in keys


def test_build_schema_show_llm_false_excludes_llm_keys() -> None:
    schema = _build_schema(show_llm=False)
    keys = _schema_keys(schema)
    assert CONF_LLM_PROVIDER not in keys
    assert CONF_LLM_PROMPT not in keys


def test_schema_validates_correct_input() -> None:
    schema = _build_schema(show_llm=False)
    data = {
        CONF_SIDECAR_URL: "http://localhost:8000",
        CONF_CAMERAS: ["camera.front_door"],
        "confidence_threshold": 0.6,
        "detection_classes": ["person", "dog", "car", "truck", "horse", "cow", "bear", "wolf"],
        "draw_boxes": True,
        "save_annotated_image": True,
        "notify_service": "",
    }
    result = schema(data)
    assert result[CONF_SIDECAR_URL] == "http://localhost:8000"
    assert result[CONF_CAMERAS] == ["camera.front_door"]


def test_schema_rejects_invalid_type_sidecar_url() -> None:
    schema = _build_schema(show_llm=False)
    with pytest.raises(vol.Invalid):
        schema({CONF_SIDECAR_URL: 123, CONF_CAMERAS: []})


def test_schema_rejects_invalid_type_cameras() -> None:
    schema = _build_schema(show_llm=False)
    with pytest.raises(vol.Invalid):
        schema({CONF_SIDECAR_URL: "http://localhost:8000", CONF_CAMERAS: "not-a-list"})

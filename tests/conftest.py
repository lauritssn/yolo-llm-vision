"""Shared pytest fixtures for YOLO + LLM Vision unit tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Project root on path so custom_components can be imported
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _patch_ha_frame() -> None:
    """Avoid RuntimeError when creating DataUpdateCoordinator outside HA context."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Default config entry data."""
    return {
        "sidecar_url": "http://sidecar:8000",
        "cameras": ["camera.front_door", "camera.garden"],
        "confidence_threshold": 0.6,
        "detection_classes": ["person", "dog", "car", "truck", "horse", "cow", "bear", "wolf"],
        "draw_boxes": True,
        "save_annotated_image": True,
        "llm_provider": "",
        "llm_prompt": "Describe what you see.",
        "notify_service": "",
    }


@pytest.fixture
def mock_config_entry_options() -> dict[str, Any]:
    """Default config entry options (overrides)."""
    return {}


@pytest.fixture
def mock_config_entry(
    mock_config_entry_data: dict[str, Any],
    mock_config_entry_options: dict[str, Any],
) -> MagicMock:
    """Mock Home Assistant ConfigEntry with data and options."""
    entry = MagicMock()
    entry.data = dict(mock_config_entry_data)
    entry.options = dict(mock_config_entry_options)
    entry.entry_id = "test-entry-id"
    entry.title = "YOLO LLM Vision"
    entry.runtime_data = None  # Set by tests to coordinator when needed
    return entry


@pytest.fixture
def mock_hass() -> MagicMock:
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/config")
    hass.async_create_task = MagicMock(return_value=None)
    hass.async_add_executor_job = AsyncMock(return_value=None)
    hass.bus.async_fire = MagicMock(return_value=None)
    hass.bus.async_listen = MagicMock(return_value=MagicMock())
    hass.services.async_call = AsyncMock(return_value=None)
    return hass


@pytest.fixture
def mock_coordinator(mock_hass: MagicMock, mock_config_entry: MagicMock) -> MagicMock:
    """Mock YoloLLMVisionCoordinator with config entry and hass."""
    from custom_components.yolo_llm_vision.coordinator import (
        CameraState,
        YoloLLMVisionCoordinator,
    )

    coordinator = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    mock_config_entry.runtime_data = coordinator
    return coordinator


@pytest.fixture
def camera_state() -> type:
    """CameraState class for building test state."""
    from custom_components.yolo_llm_vision.coordinator import CameraState
    return CameraState

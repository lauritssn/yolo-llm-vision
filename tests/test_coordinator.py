"""Tests for YoloLLMVisionCoordinator config and analyze_camera with mocks."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from homeassistant.components.camera import Image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.yolo_llm_vision.const import EVENT_DETECTION
from custom_components.yolo_llm_vision.coordinator import (
    CameraState,
    YoloLLMVisionCoordinator,
)


@pytest.fixture
def coordinator(mock_hass: MagicMock, mock_config_entry: MagicMock) -> YoloLLMVisionCoordinator:
    """Real coordinator with mock hass and entry."""
    return YoloLLMVisionCoordinator(mock_hass, mock_config_entry)


def test_sidecar_url_from_config(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.sidecar_url == "http://sidecar:8000"


def test_sidecar_url_from_options(
    mock_config_entry: MagicMock, mock_hass: MagicMock
) -> None:
    mock_config_entry.options = {"sidecar_url": "http://other:9000"}
    mock_config_entry.data = {"sidecar_url": "http://sidecar:8000", "cameras": []}
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    assert coord.sidecar_url == "http://other:9000"


def test_confidence_threshold(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.confidence_threshold == 0.6


def test_detection_classes(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.detection_classes == ["person", "dog", "car", "truck", "horse", "cow", "bear"]


def test_cameras(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.cameras == ["camera.front_door", "camera.garden"]


def test_draw_boxes(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.draw_boxes is True


def test_save_annotated(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.save_annotated is True


def test_llm_enabled_false_when_empty(coordinator: YoloLLMVisionCoordinator) -> None:
    assert coordinator.llm_enabled is False


def test_llm_enabled_true_when_provider_set(
    mock_config_entry: MagicMock, mock_hass: MagicMock
) -> None:
    mock_config_entry.data = {
        "sidecar_url": "http://s:8000",
        "cameras": [],
        "llm_provider": "llmvision.provider",
    }
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    assert coord.llm_enabled is True


def test_get_camera_state_creates_new(coordinator: YoloLLMVisionCoordinator) -> None:
    s1 = coordinator.get_camera_state("camera.test")
    assert isinstance(s1, CameraState)
    s2 = coordinator.get_camera_state("camera.test")
    assert s1 is s2


@respx.mock
@pytest.mark.asyncio
async def test_call_sidecar_sends_correct_payload(
    coordinator: YoloLLMVisionCoordinator,
) -> None:
    route = respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": False,
                "detection_count": 0,
                "classes_detected": [],
                "confidence_max": 0.0,
                "inference_time_ms": 1.0,
            },
        ),
    )
    await coordinator._call_sidecar("YmFzZTY0")
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "image_base64": "YmFzZTY0",
        "confidence_threshold": 0.6,
        "classes": ["person", "dog", "car", "truck", "horse", "cow", "bear"],
        "draw_boxes": True,
    }


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_detection_true_sets_state_and_fires_event(
    coordinator: YoloLLMVisionCoordinator,
    mock_hass: MagicMock,
) -> None:
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 2,
                "classes_detected": ["dog", "person"],
                "confidence_max": 0.92,
                "confidence_avg": 0.88,
                "inference_time_ms": 50.0,
                "annotated_image_base64": None,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    with patch(
        "custom_components.yolo_llm_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    cam = coordinator.get_camera_state("camera.front_door")
    assert cam.detected is True
    assert cam.confidence == 0.92
    assert cam.detection_count == 2
    assert cam.classes_detected == ["dog", "person"]
    assert cam.last_seen is not None
    assert result.get("detected") is True
    assert result.get("confidence") == 0.92
    mock_hass.bus.async_fire.assert_called_once()
    call_args = mock_hass.bus.async_fire.call_args
    assert call_args[0][0] == EVENT_DETECTION
    assert call_args[0][1].get("entity_id") == "camera.front_door"
    assert call_args[0][1].get("detected") is True


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_below_threshold_sets_detected_false(
    coordinator: YoloLLMVisionCoordinator,
    mock_hass: MagicMock,
) -> None:
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["person"],
                "confidence_max": 0.3,
                "inference_time_ms": 40.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    with patch(
        "custom_components.yolo_llm_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    cam = coordinator.get_camera_state("camera.front_door")
    assert cam.detected is False
    assert result.get("detected") is False
    mock_hass.bus.async_fire.assert_not_called()


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_concurrent_returns_empty(
    coordinator: YoloLLMVisionCoordinator,
) -> None:
    slow_response = asyncio.Event()

    async def slow_post(request: httpx.Request) -> httpx.Response:
        await slow_response.wait()
        return httpx.Response(
            200,
            json={
                "detected": False,
                "detection_count": 0,
                "classes_detected": [],
                "confidence_max": 0.0,
                "inference_time_ms": 1.0,
            },
        )

    respx.post("http://sidecar:8000/detect").mock(side_effect=slow_post)
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    with patch(
        "custom_components.yolo_llm_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        task1 = asyncio.create_task(coordinator.analyze_camera("camera.front_door"))
        await asyncio.sleep(0.05)
        result2 = await coordinator.analyze_camera("camera.front_door")
        slow_response.set()
        await task1

    assert result2 == {}


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_on_exception_returns_error_and_message(
    coordinator: YoloLLMVisionCoordinator,
) -> None:
    """When analyze_camera raises, result includes entity_id, error=True, and message."""
    with patch(
        "custom_components.yolo_llm_vision.coordinator.async_get_image",
        AsyncMock(side_effect=OSError("Connection refused")),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    assert result.get("entity_id") == "camera.front_door"
    assert result.get("error") is True
    assert "message" in result
    assert "Connection refused" in result["message"]


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_sidecar_4xx_returns_error_and_message(
    coordinator: YoloLLMVisionCoordinator,
) -> None:
    """When sidecar returns 4xx/5xx, result includes error and message with detail."""
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            502,
            json={"detail": "Failed to fetch image"},
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    with patch(
        "custom_components.yolo_llm_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    assert result.get("entity_id") == "camera.front_door"
    assert result.get("error") is True
    assert "message" in result
    assert "502" in result["message"]
    assert "Failed to fetch image" in result["message"]

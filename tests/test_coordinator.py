"""Tests for RfDetrVisionCoordinator config and analyze_camera with mocks."""

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

from custom_components.rf_detr_vision.const import EVENT_DETECTION, EVENT_TEST_COMPLETE
from custom_components.rf_detr_vision.coordinator import (
    CameraState,
    RfDetrVisionCoordinator,
)


@pytest.fixture
def coordinator(mock_hass: MagicMock, mock_config_entry: MagicMock) -> RfDetrVisionCoordinator:
    """Real coordinator with mock hass and entry."""
    return RfDetrVisionCoordinator(mock_hass, mock_config_entry)


def test_sidecar_url_from_config(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.sidecar_url == "http://sidecar:8000"


def test_sidecar_url_from_options(
    mock_config_entry: MagicMock, mock_hass: MagicMock
) -> None:
    mock_config_entry.options = {"sidecar_url": "http://other:9000"}
    mock_config_entry.data = {"sidecar_url": "http://sidecar:8000", "cameras": []}
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    assert coord.sidecar_url == "http://other:9000"


def test_confidence_threshold(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.confidence_threshold == 0.6


def test_detection_classes(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.detection_classes == ["person", "dog", "car", "truck", "horse", "cow", "bear"]


def test_cameras(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.cameras == ["camera.front_door", "camera.garden"]


def test_draw_boxes(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.draw_boxes is True


def test_save_annotated(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.save_annotated is True


def test_llm_enabled_false_when_empty(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.llm_enabled is False


def test_llm_enabled_true_when_provider_set(
    mock_config_entry: MagicMock, mock_hass: MagicMock
) -> None:
    mock_config_entry.data = {
        "sidecar_url": "http://s:8000",
        "cameras": [],
        "llm_provider": "llmvision.provider",
    }
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    assert coord.llm_enabled is True


def test_get_camera_state_creates_new(coordinator: RfDetrVisionCoordinator) -> None:
    s1 = coordinator.get_camera_state("camera.test")
    assert isinstance(s1, CameraState)
    s2 = coordinator.get_camera_state("camera.test")
    assert s1 is s2


@respx.mock
@pytest.mark.asyncio
async def test_call_sidecar_sends_correct_payload(
    coordinator: RfDetrVisionCoordinator,
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
    coordinator: RfDetrVisionCoordinator,
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
        "custom_components.rf_detr_vision.coordinator.async_get_image",
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
    coordinator: RfDetrVisionCoordinator,
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
        "custom_components.rf_detr_vision.coordinator.async_get_image",
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
    coordinator: RfDetrVisionCoordinator,
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
        "custom_components.rf_detr_vision.coordinator.async_get_image",
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
    coordinator: RfDetrVisionCoordinator,
) -> None:
    """When analyze_camera raises, result includes entity_id, error=True, and message."""
    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
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
    coordinator: RfDetrVisionCoordinator,
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
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    assert result.get("entity_id") == "camera.front_door"
    assert result.get("error") is True
    assert "message" in result
    assert "502" in result["message"]
    assert "Failed to fetch image" in result["message"]


def test_ai_task_enabled_false_when_empty(coordinator: RfDetrVisionCoordinator) -> None:
    assert coordinator.ai_task_enabled is False


def test_ai_task_enabled_true_when_entity_set(
    mock_config_entry: MagicMock, mock_hass: MagicMock
) -> None:
    mock_config_entry.data = {
        "sidecar_url": "http://s:8000",
        "cameras": [],
        "ai_task_entity": "ai_task.openai_ai_task",
    }
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    assert coord.ai_task_enabled is True
    assert coord.ai_analysis_enabled is True


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_with_ai_task_threat_detected(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
        "threat_analysis_prompt": "Analyze the image.",
        "threat_phrase": "THREAT DETECTED",
        "notify_service": "notify.test",
        "notify_on_threat": True,
        "notify_on_all_clear": False,
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)

    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["person"],
                "confidence_max": 0.95,
                "inference_time_ms": 50.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    mock_hass.services.async_call = AsyncMock(
        return_value={"data": "Person in driveway. THREAT DETECTED"}
    )

    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    assert result.get("threat_detected") is True
    assert "THREAT DETECTED" in result.get("ai_analysis", "")
    mock_hass.services.async_call.assert_called()
    first_call = mock_hass.services.async_call.call_args_list[0]
    assert first_call[0][0] == "ai_task"
    assert first_call[0][1] == "generate_data"


@respx.mock
@pytest.mark.asyncio
async def test_analyze_camera_with_ai_task_all_clear(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
        "notify_service": "notify.test",
        "notify_on_threat": False,
        "notify_on_all_clear": True,
        "all_clear_notification_title": "All Clear",
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)

    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["dog"],
                "confidence_max": 0.88,
                "inference_time_ms": 40.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    mock_hass.services.async_call = AsyncMock(
        return_value={"data": "Small dog in yard, no threat."}
    )

    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        result = await coordinator.analyze_camera("camera.front_door")

    assert result.get("threat_detected") is False
    notify_calls = [
        c for c in mock_hass.services.async_call.call_args_list if c[0][0] == "notify"
    ]
    assert len(notify_calls) == 1
    assert notify_calls[0][0][2]["title"].startswith("All Clear")


@respx.mock
@pytest.mark.asyncio
async def test_test_pipeline_fails_when_sidecar_unhealthy(
    coordinator: RfDetrVisionCoordinator,
    mock_hass: MagicMock,
) -> None:
    respx.get("http://sidecar:8000/health").mock(
        return_value=httpx.Response(503, json={"status": "down"}),
    )

    report = await coordinator.test_pipeline("camera.front_door")

    assert report["test"] is True
    assert report["steps"]["sidecar_health"]["ok"] is False
    assert "Sidecar health check failed" in report["summary"]
    mock_hass.bus.async_fire.assert_called_once()
    assert mock_hass.bus.async_fire.call_args[0][0] == EVENT_TEST_COMPLETE


@respx.mock
@pytest.mark.asyncio
async def test_test_pipeline_dry_run_full_success(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
        "threat_phrase": "THREAT DETECTED",
        "notify_service": "notify.telegram",
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)

    respx.get("http://sidecar:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "model": "nano"}),
    )
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["person"],
                "confidence_max": 0.91,
                "inference_time_ms": 45.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    mock_hass.services.async_call = AsyncMock(
        return_value={"data": "Person visible. THREAT DETECTED"}
    )

    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        report = await coordinator.test_pipeline(
            "camera.front_door",
            send_notifications=False,
            use_camera_snapshot=False,
        )

    assert report["ok"] is True
    assert report["steps"]["detection"]["gate_passed"] is True
    assert report["steps"]["ai_task"]["ok"] is True
    assert report["steps"]["ai_task"]["threat_detected"] is True
    assert report["steps"]["notification"]["reason"] == "send_notifications is false (dry run)"
    assert "THREAT DETECTED" in report["summary"] or report["steps"]["ai_task"]["ok"]
    mock_hass.bus.async_fire.assert_called_once()
    assert mock_hass.bus.async_fire.call_args[0][0] == EVENT_TEST_COMPLETE


@respx.mock
@pytest.mark.asyncio
async def test_test_pipeline_bypass_gate_runs_ai_when_no_detection(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)

    respx.get("http://sidecar:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": False,
                "detection_count": 0,
                "classes_detected": [],
                "confidence_max": 0.0,
                "inference_time_ms": 30.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    mock_hass.services.async_call = AsyncMock(return_value={"data": "Empty driveway."})

    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        report = await coordinator.test_pipeline(
            "camera.front_door",
            bypass_detection_gate=True,
            send_notifications=False,
            use_camera_snapshot=False,
        )

    assert report["steps"]["detection_gate"]["bypassed"] is True
    assert report["steps"]["ai_task"]["ran"] is True
    assert report["steps"]["ai_task"]["ok"] is True


@respx.mock
@pytest.mark.asyncio
async def test_test_pipeline_sends_notifications_when_requested(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
        "threat_phrase": "THREAT DETECTED",
        "notify_service": "notify.test",
        "notify_on_threat": True,
        "threat_notification_title": "SECURITY ALERT",
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)

    respx.get("http://sidecar:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["person"],
                "confidence_max": 0.93,
                "inference_time_ms": 50.0,
            },
        ),
    )
    fake_image = Image(content_type="image/jpeg", content=b"fake_jpeg_bytes")
    mock_hass.services.async_call = AsyncMock(
        return_value={"data": "Person in frame. THREAT DETECTED"}
    )

    with patch(
        "custom_components.rf_detr_vision.coordinator.async_get_image",
        AsyncMock(return_value=fake_image),
    ):
        report = await coordinator.test_pipeline(
            "camera.front_door",
            send_notifications=True,
            notification_prefix="[TEST] ",
            use_camera_snapshot=False,
        )

    notify_calls = [
        c for c in mock_hass.services.async_call.call_args_list if c[0][0] == "notify"
    ]
    assert len(notify_calls) >= 2
    assert report["steps"]["notification"]["sent"] is True
    assert any(
        "[TEST]" in str(c[0][2].get("title", "")) for c in notify_calls
    )


@respx.mock
@pytest.mark.asyncio
async def test_test_pipeline_uses_camera_snapshot_when_enabled(
    mock_config_entry: MagicMock,
    mock_hass: MagicMock,
) -> None:
    mock_config_entry.data = {
        **mock_config_entry.data,
        "ai_task_entity": "ai_task.openai_ai_task",
    }
    coordinator = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    snapshot_path = "/config/www/rf_detr_test_camera_front_door_20250101_120000.jpg"
    fake_bytes = b"camera_jpeg_from_snapshot"

    respx.get("http://sidecar:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"}),
    )
    respx.post("http://sidecar:8000/detect").mock(
        return_value=httpx.Response(
            200,
            json={
                "detected": True,
                "detection_count": 1,
                "classes_detected": ["person"],
                "confidence_max": 0.9,
                "inference_time_ms": 40.0,
            },
        ),
    )

    async def service_call(
        domain: str, service: str, data: dict, **kwargs: object
    ) -> dict[str, str] | None:
        if domain == "camera" and service == "snapshot":
            assert data["entity_id"] == "camera.front_door"
            assert data["filename"] == snapshot_path
            return None
        if domain == "ai_task" and service == "generate_data":
            return {"data": "Person visible."}
        return None

    mock_hass.services.async_call = AsyncMock(side_effect=service_call)
    mock_hass.async_add_executor_job = AsyncMock(return_value=fake_bytes)

    with patch.object(
        coordinator,
        "_build_snapshot_path",
        return_value=snapshot_path,
    ), patch(
        "custom_components.rf_detr_vision.coordinator.asyncio.sleep",
        AsyncMock(),
    ):
        report = await coordinator.test_pipeline(
            "camera.front_door",
            send_notifications=False,
            snapshot_delay_seconds=2,
            use_camera_snapshot=True,
        )

    assert report["steps"]["snapshot"]["method"] == "camera.snapshot"
    assert report["steps"]["snapshot"]["snapshot_path"] == snapshot_path
    assert report["steps"]["snapshot"]["delay_seconds"] == 2

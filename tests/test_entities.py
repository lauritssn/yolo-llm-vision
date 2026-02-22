"""Tests for sensor and binary_sensor entity native_value / is_on / extra_state_attributes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.yolo_llm_vision.binary_sensor import YoloDetectionBinarySensor
from custom_components.yolo_llm_vision.coordinator import CameraState, YoloLLMVisionCoordinator
from custom_components.yolo_llm_vision.sensor import (
    YoloClassesSensor,
    YoloConfidenceSensor,
    YoloDetectionCountSensor,
    YoloLastDetectedSensor,
)


@pytest.fixture
def coordinator_with_state(
    mock_hass: MagicMock, mock_config_entry: MagicMock
) -> YoloLLMVisionCoordinator:
    """Coordinator with one camera state pre-filled."""
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.detected = True
    cam.confidence = 0.87
    cam.detection_count = 2
    cam.classes_detected = ["person", "dog"]
    cam.last_seen = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    cam.llm_result = "A person and a dog in the frame."
    cam.inference_time_ms = 45.0
    return coord


def test_yolo_confidence_sensor_native_value(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloConfidenceSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == 87.0


def test_yolo_detection_count_sensor_native_value(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloDetectionCountSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == 2


def test_yolo_classes_sensor_native_value(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloClassesSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == "person, dog"


def test_yolo_classes_sensor_native_value_none(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.classes_detected = []
    sensor = YoloClassesSensor(coord, "camera.test")
    assert sensor.native_value == "none"


def test_yolo_last_detected_sensor_native_value(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloLastDetectedSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == "2025-06-15T12:00:00+00:00"


def test_yolo_last_detected_sensor_native_value_none(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    sensor = YoloLastDetectedSensor(coord, "camera.test")
    assert sensor.native_value is None


def test_yolo_detection_binary_sensor_is_on(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloDetectionBinarySensor(coordinator_with_state, "camera.test")
    assert sensor.is_on is True


def test_yolo_detection_binary_sensor_is_off(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = YoloLLMVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.detected = False
    sensor = YoloDetectionBinarySensor(coord, "camera.test")
    assert sensor.is_on is False


def test_yolo_detection_binary_sensor_extra_state_attributes(
    coordinator_with_state: YoloLLMVisionCoordinator,
) -> None:
    sensor = YoloDetectionBinarySensor(coordinator_with_state, "camera.test")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    assert "confidence" in attrs
    assert "detection_count" in attrs
    assert "classes_detected" in attrs
    assert "last_seen" in attrs
    assert "llm_summary" in attrs
    assert attrs["confidence"] == 0.87
    assert attrs["detection_count"] == 2
    assert attrs["classes_detected"] == ["person", "dog"]
    assert attrs["last_seen"] == "2025-06-15T12:00:00+00:00"
    assert attrs["llm_summary"] == "A person and a dog in the frame."

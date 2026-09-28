"""Tests for sensor and binary_sensor entity native_value / is_on / extra_state_attributes."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.rf_detr_vision.binary_sensor import RfDetrDetectionBinarySensor
from custom_components.rf_detr_vision.coordinator import CameraState, RfDetrVisionCoordinator
from custom_components.rf_detr_vision.sensor import (
    RfDetrClassesSensor,
    RfDetrConfidenceSensor,
    RfDetrDetectionCountSensor,
    RfDetrLastDetectedSensor,
)


@pytest.fixture
def coordinator_with_state(
    mock_hass: MagicMock, mock_config_entry: MagicMock
) -> RfDetrVisionCoordinator:
    """Coordinator with one camera state pre-filled."""
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.detected = True
    cam.confidence = 0.87
    cam.detection_count = 2
    cam.classes_detected = ["person", "dog"]
    cam.last_seen = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    cam.llm_result = "A person and a dog in the frame."
    cam.inference_time_ms = 45.0
    return coord


def test_rf_detr_confidence_sensor_native_value(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrConfidenceSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == 87.0


def test_rf_detr_detection_count_sensor_native_value(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrDetectionCountSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == 2


def test_rf_detr_classes_sensor_native_value(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrClassesSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == "person, dog"


def test_rf_detr_classes_sensor_native_value_none(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.classes_detected = []
    sensor = RfDetrClassesSensor(coord, "camera.test")
    assert sensor.native_value == "none"


def test_rf_detr_last_detected_sensor_native_value(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrLastDetectedSensor(coordinator_with_state, "camera.test")
    assert sensor.native_value == "2025-06-15T12:00:00+00:00"


def test_rf_detr_last_detected_sensor_native_value_none(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    sensor = RfDetrLastDetectedSensor(coord, "camera.test")
    assert sensor.native_value is None


def test_rf_detr_detection_binary_sensor_is_on(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrDetectionBinarySensor(coordinator_with_state, "camera.test")
    assert sensor.is_on is True


def test_rf_detr_detection_binary_sensor_is_off(
    mock_hass: MagicMock, mock_config_entry: MagicMock,
) -> None:
    coord = RfDetrVisionCoordinator(mock_hass, mock_config_entry)
    cam = coord.get_camera_state("camera.test")
    cam.detected = False
    sensor = RfDetrDetectionBinarySensor(coord, "camera.test")
    assert sensor.is_on is False


def test_rf_detr_detection_binary_sensor_extra_state_attributes(
    coordinator_with_state: RfDetrVisionCoordinator,
) -> None:
    sensor = RfDetrDetectionBinarySensor(coordinator_with_state, "camera.test")
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

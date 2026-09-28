"""Sensor platform for RF-DETR + LLM Vision."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RfDetrConfigEntry
from .const import CONF_CAMERAS, DOMAIN
from .coordinator import CameraState, RfDetrVisionCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RfDetrConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    cameras: list[str] = entry.data.get(CONF_CAMERAS, [])
    entities: list[SensorEntity] = []
    for cam_id in cameras:
        entities.extend([
            RfDetrConfidenceSensor(coordinator, cam_id),
            RfDetrDetectionCountSensor(coordinator, cam_id),
            RfDetrClassesSensor(coordinator, cam_id),
            RfDetrLastDetectedSensor(coordinator, cam_id),
        ])
        if coordinator.llm_enabled:
            entities.append(RfDetrAiSummarySensor(coordinator, cam_id))
    async_add_entities(entities)


class _RfDetrSensorBase(CoordinatorEntity[RfDetrVisionCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RfDetrVisionCoordinator, camera_entity_id: str
    ) -> None:
        super().__init__(coordinator)
        self._camera = camera_entity_id

    @property
    def _cam_state(self) -> CameraState:
        return self.coordinator.get_camera_state(self._camera)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class RfDetrConfidenceSensor(_RfDetrSensorBase):
    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: RfDetrVisionCoordinator, cam: str) -> None:
        super().__init__(coordinator, cam)
        safe = cam.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_confidence"
        self._attr_name = f"RF-DETR confidence {cam.split('.')[-1]}"

    @property
    def native_value(self) -> float:
        return round(self._cam_state.confidence * 100, 1)


class RfDetrDetectionCountSensor(_RfDetrSensorBase):
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator: RfDetrVisionCoordinator, cam: str) -> None:
        super().__init__(coordinator, cam)
        safe = cam.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_detection_count"
        self._attr_name = f"RF-DETR detection count {cam.split('.')[-1]}"

    @property
    def native_value(self) -> int:
        return self._cam_state.detection_count


class RfDetrClassesSensor(_RfDetrSensorBase):
    """Comma-separated list of detected class names."""

    _attr_icon = "mdi:tag-multiple"

    def __init__(self, coordinator: RfDetrVisionCoordinator, cam: str) -> None:
        super().__init__(coordinator, cam)
        safe = cam.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_classes"
        self._attr_name = f"RF-DETR classes {cam.split('.')[-1]}"

    @property
    def native_value(self) -> str:
        classes = self._cam_state.classes_detected
        return ", ".join(classes) if classes else "none"


class RfDetrLastDetectedSensor(_RfDetrSensorBase):
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: RfDetrVisionCoordinator, cam: str) -> None:
        super().__init__(coordinator, cam)
        safe = cam.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_last_detected"
        self._attr_name = f"RF-DETR last detected {cam.split('.')[-1]}"

    @property
    def native_value(self) -> str | None:
        ts = self._cam_state.last_seen
        return ts.isoformat() if ts else None


class RfDetrAiSummarySensor(_RfDetrSensorBase):
    _attr_icon = "mdi:text"

    def __init__(self, coordinator: RfDetrVisionCoordinator, cam: str) -> None:
        super().__init__(coordinator, cam)
        safe = cam.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_llm_summary"
        self._attr_name = f"RF-DETR AI summary {cam.split('.')[-1]}"

    @property
    def native_value(self) -> str | None:
        return self._cam_state.llm_result

"""Binary sensor platform for YOLO + LLM Vision."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import YoloConfigEntry
from .const import CONF_CAMERAS, DOMAIN
from .coordinator import CameraState, YoloLLMVisionCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YoloConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    cameras: list[str] = entry.data.get(CONF_CAMERAS, [])
    async_add_entities(
        [YoloDetectionBinarySensor(coordinator, cam_id) for cam_id in cameras]
    )


class YoloDetectionBinarySensor(
    CoordinatorEntity[YoloLLMVisionCoordinator], BinarySensorEntity
):
    """On when the YOLO sidecar detects a configured object class."""

    _attr_device_class = BinarySensorDeviceClass.MOTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: YoloLLMVisionCoordinator, camera_entity_id: str
    ) -> None:
        super().__init__(coordinator)
        self._camera = camera_entity_id
        safe = camera_entity_id.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe}_detected"
        self._attr_name = f"YOLO detection {camera_entity_id.split('.')[-1]}"

    @property
    def _cam_state(self) -> CameraState:
        return self.coordinator.get_camera_state(self._camera)

    @property
    def is_on(self) -> bool:
        return self._cam_state.detected

    @property
    def extra_state_attributes(self) -> dict[str, str | float | int | list[str] | None]:
        cam = self._cam_state
        return {
            "confidence": cam.confidence,
            "detection_count": cam.detection_count,
            "classes_detected": cam.classes_detected,
            "last_seen": cam.last_seen.isoformat() if cam.last_seen else None,
            "llm_summary": cam.llm_result,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

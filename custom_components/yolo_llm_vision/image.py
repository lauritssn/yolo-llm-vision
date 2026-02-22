"""Image platform for YOLO + LLM Vision — annotated snapshot per camera."""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import YoloConfigEntry
from .const import CONF_CAMERAS, DOMAIN
from .coordinator import YoloLLMVisionCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YoloConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    cameras: list[str] = entry.data.get(CONF_CAMERAS, [])
    async_add_entities(
        [YoloAnnotatedImage(coordinator, cam_id) for cam_id in cameras]
    )


class YoloAnnotatedImage(
    CoordinatorEntity[YoloLLMVisionCoordinator], ImageEntity
):
    """Image entity serving the last YOLO-annotated snapshot."""

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"

    def __init__(
        self,
        coordinator: YoloLLMVisionCoordinator,
        camera_entity_id: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._camera_entity_id = camera_entity_id
        safe_id = camera_entity_id.replace(".", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe_id}_annotated"
        state = coordinator.hass.states.get(camera_entity_id)
        cam_name = (
            state.attributes.get("friendly_name")
            if state
            else camera_entity_id.split(".")[-1].replace("_", " ").title()
        )
        self._attr_name = f"{cam_name} YOLO Annotated"
        self._cached_image: bytes | None = None

    async def async_image(self) -> bytes | None:
        cam_state = self.coordinator.get_camera_state(self._camera_entity_id)
        if cam_state.last_image_base64:
            return base64.b64decode(cam_state.last_image_base64)
        return None

    @property
    def image_last_updated(self) -> datetime | None:
        cam_state = self.coordinator.get_camera_state(self._camera_entity_id)
        return cam_state.last_seen or datetime.now(tz=timezone.utc)

    @callback
    def _handle_coordinator_update(self) -> None:
        cam_state = self.coordinator.get_camera_state(self._camera_entity_id)
        if cam_state.last_image_base64:
            self._cached_image = base64.b64decode(cam_state.last_image_base64)
            self._attr_image_last_updated = cam_state.last_seen or datetime.now(
                tz=timezone.utc
            )
        self.async_write_ha_state()

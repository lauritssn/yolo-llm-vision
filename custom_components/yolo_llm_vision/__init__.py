"""YOLO + LLM Vision integration for Home Assistant.

Runs local YOLOv8 object detection via a Docker sidecar. Optionally calls
LLM Vision for rich AI analysis when a relevant object is detected.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import YoloLLMVisionCoordinator

_LOGGER = logging.getLogger(__name__)

type YoloConfigEntry = ConfigEntry[YoloLLMVisionCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_ANALYZE = "analyze"
SERVICE_ANALYZE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("force_llm", default=False): cv.boolean,
    }
)


def _get_coordinator(hass: HomeAssistant) -> YoloLLMVisionCoordinator:
    """Return the first loaded coordinator or raise."""
    entries: list[ConfigEntry] = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_loaded_entries",
        )
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register YOLO + LLM Vision services (once, independent of entries)."""

    async def handle_analyze(call: ServiceCall) -> dict[str, Any]:
        coordinator = _get_coordinator(hass)
        entity_id: str = call.data["entity_id"]
        force_llm: bool = call.data.get("force_llm", False)
        return await coordinator.manual_analyze(entity_id, force_llm=force_llm)

    hass.services.async_register(
        DOMAIN,
        SERVICE_ANALYZE,
        handle_analyze,
        schema=SERVICE_ANALYZE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: YoloConfigEntry) -> bool:
    """Set up YOLO + LLM Vision from a config entry."""
    coordinator = YoloLLMVisionCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_listening()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: YoloConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: YoloConfigEntry
) -> bool:
    """Unload a YOLO + LLM Vision config entry."""
    entry.runtime_data.stop_listening()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

"""YOLO + LLM Vision integration for Home Assistant.

Runs local YOLOv8 object detection via a Docker sidecar. Optionally calls
LLM Vision for rich AI analysis when a relevant object is detected.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL, DOMAIN, PLATFORMS
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
        _LOGGER.debug(
            "Service yolo_llm_vision.analyze called with data: %s",
            dict(call.data),
        )
        try:
            coordinator = _get_coordinator(hass)
        except ServiceValidationError:
            all_entries = hass.config_entries.async_entries(DOMAIN)
            _LOGGER.debug(
                "No loaded config entry: DOMAIN=%s, entries_count=%s, entry_states=%s",
                DOMAIN,
                len(all_entries),
                [(e.entry_id, e.state) for e in all_entries],
            )
            _LOGGER.exception("No loaded config entry for YOLO + LLM Vision")
            raise
        cfg = {**coordinator.config_entry.data, **coordinator.config_entry.options}
        sidecar_url = cfg.get(CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL)
        _LOGGER.debug(
            "Using sidecar URL from config/options: %s",
            sidecar_url,
        )
        entity_id: str = call.data["entity_id"]
        force_llm: bool = call.data.get("force_llm", False)
        _LOGGER.debug(
            "Calling coordinator.manual_analyze(entity_id=%s, force_llm=%s)",
            entity_id,
            force_llm,
        )
        result = await coordinator.manual_analyze(entity_id, force_llm=force_llm)
        if result.get("error"):
            _LOGGER.debug(
                "analyze returned error: true for entity_id=%s; full result: %s",
                entity_id,
                result,
            )
        else:
            _LOGGER.debug(
                "analyze succeeded for entity_id=%s; detected=%s",
                entity_id,
                result.get("detected"),
            )
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_ANALYZE,
        handle_analyze,
        schema=SERVICE_ANALYZE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def _check_sidecar_health(hass: HomeAssistant, sidecar_url: str) -> bool:
    """GET sidecar /health and return True if OK."""
    url = f"{sidecar_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            ok = resp.status_code == 200
            _LOGGER.debug(
                "Sidecar health check %s: GET %s -> status=%s, body=%s",
                "passed" if ok else "failed",
                url,
                resp.status_code,
                resp.text[:200] if resp.text else "",
            )
            return ok
    except Exception:
        _LOGGER.exception(
            "Sidecar health check failed: GET %s",
            url,
        )
        return False


async def async_setup_entry(hass: HomeAssistant, entry: YoloConfigEntry) -> bool:
    """Set up YOLO + LLM Vision from a config entry."""
    _LOGGER.debug(
        "async_setup_entry: entry_id=%s, entry.data=%s, entry.options=%s",
        entry.entry_id,
        dict(entry.data),
        dict(entry.options),
    )
    cfg = {**entry.data, **entry.options}
    sidecar_url = cfg.get(CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL)
    _LOGGER.debug(
        "Extracted sidecar URL: %s",
        sidecar_url,
    )
    coordinator = YoloLLMVisionCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_listening()

    health_ok = await _check_sidecar_health(hass, sidecar_url)
    _LOGGER.debug(
        "Sidecar health check on startup: %s",
        "passed" if health_ok else "failed",
    )

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

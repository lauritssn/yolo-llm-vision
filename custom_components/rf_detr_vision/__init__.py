"""RF-DETR + LLM Vision integration for Home Assistant.

Runs local RF-DETR instance segmentation via a Docker sidecar. Optionally
calls AI Task or LLM Vision when a relevant object is detected.
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

from .const import (
    CONF_SIDECAR_URL,
    DEFAULT_SIDECAR_URL,
    DEFAULT_SNAPSHOT_DELAY,
    DEFAULT_TEST_NOTIFICATION_PREFIX,
    DOMAIN,
    PLATFORMS,
    SERVICE_TEST_PIPELINE,
)
from .coordinator import RfDetrVisionCoordinator

_LOGGER = logging.getLogger(__name__)

type RfDetrConfigEntry = ConfigEntry[RfDetrVisionCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_ANALYZE = "analyze"
SERVICE_ANALYZE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("force_llm", default=False): cv.boolean,
    }
)

SERVICE_TEST_PIPELINE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("send_notifications", default=False): cv.boolean,
        vol.Optional("bypass_detection_gate", default=False): cv.boolean,
        vol.Optional("force_ai", default=True): cv.boolean,
        vol.Optional(
            "notification_prefix",
            default=DEFAULT_TEST_NOTIFICATION_PREFIX,
        ): cv.string,
        vol.Optional(
            "snapshot_delay_seconds",
            default=DEFAULT_SNAPSHOT_DELAY,
        ): vol.All(vol.Coerce(float), vol.Range(min=0, max=30)),
        vol.Optional("use_camera_snapshot", default=True): cv.boolean,
    }
)


def _get_coordinator(hass: HomeAssistant) -> RfDetrVisionCoordinator:
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
    """Register RF-DETR + LLM Vision services (once, independent of entries)."""

    async def handle_analyze(call: ServiceCall) -> dict[str, Any]:
        _LOGGER.debug(
            "Service rf_detr_vision.analyze called with data: %s",
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
            _LOGGER.exception("No loaded config entry for RF-DETR + LLM Vision")
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

    async def handle_test_pipeline(call: ServiceCall) -> dict[str, Any]:
        coordinator = _get_coordinator(hass)
        return await coordinator.test_pipeline(
            call.data["entity_id"],
            send_notifications=call.data.get("send_notifications", False),
            bypass_detection_gate=call.data.get("bypass_detection_gate", False),
            force_ai=call.data.get("force_ai", True),
            notification_prefix=call.data.get(
                "notification_prefix", DEFAULT_TEST_NOTIFICATION_PREFIX
            ),
            snapshot_delay_seconds=call.data.get(
                "snapshot_delay_seconds", DEFAULT_SNAPSHOT_DELAY
            ),
            use_camera_snapshot=call.data.get("use_camera_snapshot", True),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ANALYZE,
        handle_analyze,
        schema=SERVICE_ANALYZE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TEST_PIPELINE,
        handle_test_pipeline,
        schema=SERVICE_TEST_PIPELINE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
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


async def async_setup_entry(hass: HomeAssistant, entry: RfDetrConfigEntry) -> bool:
    """Set up RF-DETR + LLM Vision from a config entry."""
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
    coordinator = RfDetrVisionCoordinator(hass, entry)
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
    hass: HomeAssistant, entry: RfDetrConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: RfDetrConfigEntry
) -> bool:
    """Unload a RF-DETR + LLM Vision config entry."""
    entry.runtime_data.stop_listening()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

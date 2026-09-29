"""Home Assistant Supervisor helpers for RF-DETR sidecar discovery."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import ADDON_PORT, ADDON_SLUG, DATA_DISCOVERED_SIDECAR_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _addon_matches(slug: str) -> bool:
    return slug == ADDON_SLUG or slug.endswith(f"_{ADDON_SLUG}")


async def async_discover_sidecar_url(hass: HomeAssistant) -> str | None:
    """Discover the internal add-on URL via the Supervisor API.

    Home Assistant add-ons are reached on the internal Docker network using the
    hostname from Supervisor (format: ``{repo}-{slug}`` with underscores as
    hyphens), not ``localhost``.
    """
    if "hassio" not in hass.config.components:
        return None

    hassio: Any = hass.data.get("hassio")
    if hassio is None:
        return None

    try:
        addons_payload = await hassio.get_addons()
    except Exception:
        _LOGGER.debug("Could not list Supervisor add-ons", exc_info=True)
        return None

    for addon in addons_payload.get("addons", []):
        slug = addon.get("slug", "")
        if not _addon_matches(slug):
            continue
        hostname = addon.get("hostname") or slug.replace("_", "-")
        url = f"http://{hostname}:{ADDON_PORT}"
        _LOGGER.debug(
            "Discovered RF-DETR sidecar add-on slug=%s hostname=%s url=%s state=%s",
            slug,
            hostname,
            url,
            addon.get("state"),
        )
        return url

    return None


async def async_store_discovered_sidecar_url(hass: HomeAssistant) -> str | None:
    """Discover and cache the sidecar URL on ``hass.data[DOMAIN]``."""
    url = await async_discover_sidecar_url(hass)
    if url:
        hass.data.setdefault(DOMAIN, {})[DATA_DISCOVERED_SIDECAR_URL] = url
    return url


def resolve_sidecar_url(hass: HomeAssistant, configured: str | None) -> str:
    """Return configured URL or Supervisor-discovered internal add-on URL."""
    configured = (configured or "").strip()
    if configured:
        return configured.rstrip("/")

    discovered = hass.data.get(DOMAIN, {}).get(DATA_DISCOVERED_SIDECAR_URL)
    if discovered:
        return str(discovered).rstrip("/")

    return ""

"""Tests for Supervisor-based sidecar URL discovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.rf_detr_vision.const import DATA_DISCOVERED_SIDECAR_URL, DOMAIN
from custom_components.rf_detr_vision.hassio import (
    async_discover_sidecar_url,
    async_store_discovered_sidecar_url,
    resolve_sidecar_url,
)


@pytest.mark.asyncio
async def test_discover_sidecar_url_from_supervisor() -> None:
    hass = MagicMock()
    hass.config.components = {"hassio"}
    hassio = MagicMock()
    hassio.get_addons = AsyncMock(
        return_value={
            "addons": [
                {
                    "slug": "a1b2c3d4_rf_detr_sidecar",
                    "hostname": "a1b2c3d4-rf-detr-sidecar",
                    "state": "started",
                }
            ]
        }
    )
    hass.data = {"hassio": hassio}

    url = await async_discover_sidecar_url(hass)

    assert url == "http://a1b2c3d4-rf-detr-sidecar:8000"


@pytest.mark.asyncio
async def test_discover_sidecar_url_local_addon() -> None:
    hass = MagicMock()
    hass.config.components = {"hassio"}
    hassio = MagicMock()
    hassio.get_addons = AsyncMock(
        return_value={
            "addons": [
                {
                    "slug": "local_rf_detr_sidecar",
                    "hostname": "local-rf-detr-sidecar",
                    "state": "started",
                }
            ]
        }
    )
    hass.data = {"hassio": hassio}

    url = await async_discover_sidecar_url(hass)

    assert url == "http://local-rf-detr-sidecar:8000"


def test_resolve_sidecar_url_prefers_configured() -> None:
    hass = MagicMock()
    hass.data = {DOMAIN: {DATA_DISCOVERED_SIDECAR_URL: "http://discovered:8000"}}

    assert resolve_sidecar_url(hass, "http://manual:9000") == "http://manual:9000"


def test_resolve_sidecar_url_uses_discovered_when_empty() -> None:
    hass = MagicMock()
    hass.data = {DOMAIN: {DATA_DISCOVERED_SIDECAR_URL: "http://discovered:8000"}}

    assert resolve_sidecar_url(hass, "") == "http://discovered:8000"


@pytest.mark.asyncio
async def test_store_discovered_sidecar_url() -> None:
    hass = MagicMock()
    hass.config.components = {"hassio"}
    hassio = MagicMock()
    hassio.get_addons = AsyncMock(
        return_value={
            "addons": [
                {"slug": "local_rf_detr_sidecar", "hostname": "local-rf-detr-sidecar"}
            ]
        }
    )
    hass.data = {"hassio": hassio}

    url = await async_store_discovered_sidecar_url(hass)

    assert url == "http://local-rf-detr-sidecar:8000"
    assert hass.data[DOMAIN][DATA_DISCOVERED_SIDECAR_URL] == url

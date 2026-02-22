"""Config flow for YOLO + LLM Vision."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAMERAS,
    CONF_CONFIDENCE_THRESHOLD,
    CONF_DETECTION_CLASSES,
    CONF_DRAW_BOXES,
    CONF_LLM_PROMPT,
    CONF_LLM_PROVIDER,
    CONF_NOTIFY_SERVICE,
    CONF_SAVE_ANNOTATED,
    CONF_SIDECAR_URL,
    DEFAULT_CONFIDENCE,
    DEFAULT_DETECTION_CLASSES,
    DEFAULT_PROMPT,
    DEFAULT_SIDECAR_URL,
    DETECTION_CLASS_OPTIONS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _has_llmvision(hass: HomeAssistant) -> bool:
    return "llmvision" in hass.config.components or any(
        e.domain == "llmvision" for e in hass.config_entries.async_entries()
    )


def _build_schema(
    defaults: dict[str, Any] | None = None,
    show_llm: bool = False,
) -> vol.Schema:
    d = defaults or {}
    fields: dict[Any, Any] = {}

    fields[
        vol.Required(
            CONF_SIDECAR_URL, default=d.get(CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL)
        )
    ] = selector.TextSelector()

    fields[
        vol.Required(CONF_CAMERAS, default=d.get(CONF_CAMERAS, []))
    ] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="camera", multiple=True)
    )

    fields[
        vol.Optional(
            CONF_CONFIDENCE_THRESHOLD,
            default=d.get(CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=0.1, max=1.0, step=0.05, mode="slider")
    )

    fields[
        vol.Optional(
            CONF_DETECTION_CLASSES,
            default=d.get(CONF_DETECTION_CLASSES, DEFAULT_DETECTION_CLASSES),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=DETECTION_CLASS_OPTIONS,
            multiple=True,
            mode="dropdown",
            sort=True,
        )
    )

    fields[
        vol.Optional(CONF_DRAW_BOXES, default=d.get(CONF_DRAW_BOXES, True))
    ] = selector.BooleanSelector()

    fields[
        vol.Optional(CONF_SAVE_ANNOTATED, default=d.get(CONF_SAVE_ANNOTATED, True))
    ] = selector.BooleanSelector()

    if show_llm:
        fields[
            vol.Optional(CONF_LLM_PROVIDER, default=d.get(CONF_LLM_PROVIDER, ""))
        ] = selector.ConfigEntrySelector(
            selector.ConfigEntrySelectorConfig(integration="llmvision")
        )
        fields[
            vol.Optional(
                CONF_LLM_PROMPT, default=d.get(CONF_LLM_PROMPT, DEFAULT_PROMPT)
            )
        ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))

    fields[
        vol.Optional(CONF_NOTIFY_SERVICE, default=d.get(CONF_NOTIFY_SERVICE, ""))
    ] = selector.TextSelector(selector.TextSelectorConfig(type="text"))

    return vol.Schema(fields)


class YoloLLMVisionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YOLO + LLM Vision."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="YOLO + LLM Vision", data=user_input
            )
        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(show_llm=_has_llmvision(self.hass)),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return YoloLLMVisionOptionsFlow()


class YoloLLMVisionOptionsFlow(OptionsFlow):
    """Handle an options flow for YOLO + LLM Vision."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(
                defaults=current, show_llm=_has_llmvision(self.hass)
            ),
        )

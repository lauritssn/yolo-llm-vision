"""Config flow for RF-DETR + LLM Vision."""

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
    CONF_AI_TASK_ENTITY,
    CONF_AI_TASK_NAME,
    CONF_CAMERAS,
    CONF_CLEAR_TITLE,
    CONF_CONFIDENCE_THRESHOLD,
    CONF_DETECTION_CLASSES,
    CONF_DRAW_BOXES,
    CONF_LLM_PROMPT,
    CONF_LLM_PROVIDER,
    CONF_NOTIFY_INCLUDE_PHOTO,
    CONF_NOTIFY_ON_ALL_CLEAR,
    CONF_NOTIFY_ON_THREAT,
    CONF_NOTIFY_SERVICE,
    CONF_SAVE_ANNOTATED,
    CONF_SIDECAR_URL,
    CONF_THREAT_PHRASE,
    CONF_THREAT_PROMPT,
    CONF_THREAT_TITLE,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CLEAR_TITLE,
    DEFAULT_CONFIDENCE,
    DEFAULT_DETECTION_CLASSES,
    DEFAULT_NOTIFY_INCLUDE_PHOTO,
    DEFAULT_NOTIFY_ON_ALL_CLEAR,
    DEFAULT_NOTIFY_ON_THREAT,
    DEFAULT_SIDECAR_URL,
    DEFAULT_THREAT_PHRASE,
    DEFAULT_THREAT_PROMPT,
    DEFAULT_THREAT_TITLE,
    DETECTION_CLASS_OPTIONS,
    DOMAIN,
)
from .hassio import async_discover_sidecar_url

_LOGGER = logging.getLogger(__name__)

STEP_SIDECAR = "sidecar"
STEP_CAMERAS = "cameras"
STEP_AI = "ai_analysis"
STEP_NOTIFICATIONS = "notifications"
STEP_INIT = "init"


def _merged_config(entry: ConfigEntry | None, draft: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge entry data/options with optional in-progress draft values."""
    base: dict[str, Any] = {}
    if entry is not None:
        base = {**entry.data, **entry.options}
    if draft:
        base.update(draft)
    return base


def _has_llmvision(hass: HomeAssistant) -> bool:
    return "llmvision" in hass.config.components or any(
        e.domain == "llmvision" for e in hass.config_entries.async_entries()
    )


def _sidecar_schema(defaults: dict[str, Any]) -> vol.Schema:
    default_url = defaults.get(CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL)
    return vol.Schema(
        {
            vol.Optional(
                CONF_SIDECAR_URL,
                default=default_url,
            ): selector.TextSelector(),
        }
    )


def _cameras_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_CAMERAS,
                default=defaults.get(CONF_CAMERAS, []),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="camera", multiple=True)
            ),
            vol.Optional(
                CONF_CONFIDENCE_THRESHOLD,
                default=defaults.get(CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.1, max=1.0, step=0.05, mode="slider")
            ),
            vol.Optional(
                CONF_DETECTION_CLASSES,
                default=defaults.get(CONF_DETECTION_CLASSES, DEFAULT_DETECTION_CLASSES),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=DETECTION_CLASS_OPTIONS,
                    multiple=True,
                    mode="dropdown",
                    sort=True,
                )
            ),
            vol.Optional(
                CONF_DRAW_BOXES,
                default=defaults.get(CONF_DRAW_BOXES, True),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_SAVE_ANNOTATED,
                default=defaults.get(CONF_SAVE_ANNOTATED, True),
            ): selector.BooleanSelector(),
        }
    )


def _ai_schema(defaults: dict[str, Any], *, show_llmvision: bool) -> vol.Schema:
    ai_task_key: vol.Optional | vol.Required
    ai_task_entity = defaults.get(CONF_AI_TASK_ENTITY)
    if ai_task_entity:
        ai_task_key = vol.Optional(CONF_AI_TASK_ENTITY, default=ai_task_entity)
    else:
        ai_task_key = vol.Optional(CONF_AI_TASK_ENTITY)

    fields: dict[Any, Any] = {
        ai_task_key: selector.EntitySelector(
            selector.EntitySelectorConfig(domain="ai_task")
        ),
        vol.Optional(
            CONF_AI_TASK_NAME,
            default=defaults.get(CONF_AI_TASK_NAME, DEFAULT_AI_TASK_NAME),
        ): selector.TextSelector(),
        vol.Optional(
            CONF_THREAT_PROMPT,
            default=defaults.get(CONF_THREAT_PROMPT, DEFAULT_THREAT_PROMPT),
        ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Optional(
            CONF_THREAT_PHRASE,
            default=defaults.get(CONF_THREAT_PHRASE, DEFAULT_THREAT_PHRASE),
        ): selector.TextSelector(),
    }
    if show_llmvision:
        fields[
            vol.Optional(
                CONF_LLM_PROVIDER,
                default=defaults.get(CONF_LLM_PROVIDER, ""),
            )
        ] = selector.ConfigEntrySelector(
            selector.ConfigEntrySelectorConfig(integration="llmvision")
        )
        fields[
            vol.Optional(
                CONF_LLM_PROMPT,
                default=defaults.get(CONF_LLM_PROMPT, DEFAULT_THREAT_PROMPT),
            )
        ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
    return vol.Schema(fields)


def _notifications_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_NOTIFY_SERVICE,
                default=defaults.get(CONF_NOTIFY_SERVICE, ""),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NOTIFY_ON_THREAT,
                default=defaults.get(CONF_NOTIFY_ON_THREAT, DEFAULT_NOTIFY_ON_THREAT),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_NOTIFY_ON_ALL_CLEAR,
                default=defaults.get(CONF_NOTIFY_ON_ALL_CLEAR, DEFAULT_NOTIFY_ON_ALL_CLEAR),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_THREAT_TITLE,
                default=defaults.get(CONF_THREAT_TITLE, DEFAULT_THREAT_TITLE),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_CLEAR_TITLE,
                default=defaults.get(CONF_CLEAR_TITLE, DEFAULT_CLEAR_TITLE),
            ): selector.TextSelector(),
            vol.Optional(
                CONF_NOTIFY_INCLUDE_PHOTO,
                default=defaults.get(CONF_NOTIFY_INCLUDE_PHOTO, DEFAULT_NOTIFY_INCLUDE_PHOTO),
            ): selector.BooleanSelector(),
        }
    )


def _build_schema(
    defaults: dict[str, Any] | None = None,
    show_llm: bool = False,
) -> vol.Schema:
    """Single-page schema (used in tests and backward compatibility)."""
    d = defaults or {}
    sidecar = _sidecar_schema(d).schema
    cameras = _cameras_schema(d).schema
    ai = _ai_schema(d, show_llmvision=show_llm).schema
    notifications = _notifications_schema(d).schema
    return vol.Schema({**sidecar, **cameras, **ai, **notifications})


class RfDetrVisionConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RF-DETR + LLM Vision."""

    VERSION = 2

    def __init__(self) -> None:
        self._draft: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the setup wizard."""
        return await self.async_step_sidecar()

    async def async_step_sidecar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_cameras()
        defaults = _merged_config(None, self._draft)
        if not defaults.get(CONF_SIDECAR_URL):
            discovered = await async_discover_sidecar_url(self.hass)
            if discovered:
                defaults[CONF_SIDECAR_URL] = discovered
        return self.async_show_form(
            step_id=STEP_SIDECAR,
            data_schema=_sidecar_schema(defaults),
        )

    async def async_step_cameras(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_ai_analysis()
        defaults = _merged_config(None, self._draft)
        return self.async_show_form(
            step_id=STEP_CAMERAS,
            data_schema=_cameras_schema(defaults),
        )

    async def async_step_ai_analysis(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_notifications()
        defaults = _merged_config(None, self._draft)
        return self.async_show_form(
            step_id=STEP_AI,
            data_schema=_ai_schema(defaults, show_llmvision=_has_llmvision(self.hass)),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._draft.update(user_input)
            return self.async_create_entry(
                title="RF-DETR + LLM Vision",
                data=self._draft,
            )
        defaults = _merged_config(None, self._draft)
        return self.async_show_form(
            step_id=STEP_NOTIFICATIONS,
            data_schema=_notifications_schema(defaults),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return RfDetrVisionOptionsFlow()


class RfDetrVisionOptionsFlow(OptionsFlow):
    """Handle an options flow for RF-DETR + LLM Vision."""

    def __init__(self) -> None:
        self._draft: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            step = user_input["next_step"]
            return await getattr(self, f"async_step_{step}")()
        return self.async_show_form(
            step_id=STEP_INIT,
            data_schema=vol.Schema(
                {
                    vol.Required("next_step"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=STEP_SIDECAR,
                                    label="Sidecar connection",
                                ),
                                selector.SelectOptionDict(
                                    value=STEP_CAMERAS,
                                    label="Cameras & detection",
                                ),
                                selector.SelectOptionDict(
                                    value=STEP_AI,
                                    label="AI threat analysis",
                                ),
                                selector.SelectOptionDict(
                                    value=STEP_NOTIFICATIONS,
                                    label="Notifications",
                                ),
                            ],
                            mode="list",
                        )
                    )
                }
            ),
        )

    async def _save_section(self, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        if user_input is None:
            raise RuntimeError("user_input required")
        current = _merged_config(self.config_entry)
        current.update(user_input)
        return self.async_create_entry(title="", data=current)

    async def async_step_sidecar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save_section(user_input)
        defaults = _merged_config(self.config_entry, self._draft)
        if not defaults.get(CONF_SIDECAR_URL):
            discovered = await async_discover_sidecar_url(self.hass)
            if discovered:
                defaults[CONF_SIDECAR_URL] = discovered
        return self.async_show_form(
            step_id=STEP_SIDECAR,
            data_schema=_sidecar_schema(defaults),
        )

    async def async_step_cameras(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save_section(user_input)
        defaults = _merged_config(self.config_entry, self._draft)
        return self.async_show_form(
            step_id=STEP_CAMERAS,
            data_schema=_cameras_schema(defaults),
        )

    async def async_step_ai_analysis(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save_section(user_input)
        defaults = _merged_config(self.config_entry, self._draft)
        return self.async_show_form(
            step_id=STEP_AI,
            data_schema=_ai_schema(defaults, show_llmvision=_has_llmvision(self.hass)),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save_section(user_input)
        defaults = _merged_config(self.config_entry, self._draft)
        return self.async_show_form(
            step_id=STEP_NOTIFICATIONS,
            data_schema=_notifications_schema(defaults),
        )

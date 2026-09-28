"""DataUpdateCoordinator for YOLO + LLM Vision."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from homeassistant.components.camera import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
    DEFAULT_PROMPT,
    DEFAULT_SIDECAR_URL,
    DEFAULT_THREAT_PHRASE,
    DEFAULT_THREAT_PROMPT,
    DEFAULT_THREAT_TITLE,
    DOMAIN,
    EVENT_DETECTION,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class CameraState:
    """Per-camera detection state."""

    detected: bool = False
    confidence: float = 0.0
    detection_count: int = 0
    classes_detected: list[str] = field(default_factory=list)
    last_image_base64: str | None = None
    last_saved_image_path: str | None = None
    last_seen: datetime | None = None
    llm_result: str | None = None
    threat_detected: bool | None = None
    inference_time_ms: float = 0.0


class YoloLLMVisionCoordinator(DataUpdateCoordinator[dict[str, CameraState]]):
    """Coordinate RF-DETR detection, AI threat analysis, and notifications."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.config_entry = entry
        self._states: dict[str, CameraState] = {}
        self._unsub_listener: Any = None
        self._analyzing: set[str] = set()

    # -- config helpers -------------------------------------------------------

    @property
    def _config(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def sidecar_url(self) -> str:
        return self._config.get(CONF_SIDECAR_URL, DEFAULT_SIDECAR_URL)

    @property
    def confidence_threshold(self) -> float:
        return self._config.get(CONF_CONFIDENCE_THRESHOLD, DEFAULT_CONFIDENCE)

    @property
    def detection_classes(self) -> list[str]:
        return self._config.get(CONF_DETECTION_CLASSES, DEFAULT_DETECTION_CLASSES)

    @property
    def cameras(self) -> list[str]:
        return self._config.get(CONF_CAMERAS, [])

    @property
    def draw_boxes(self) -> bool:
        return self._config.get(CONF_DRAW_BOXES, True)

    @property
    def save_annotated(self) -> bool:
        return self._config.get(CONF_SAVE_ANNOTATED, True)

    @property
    def ai_task_entity(self) -> str:
        return self._config.get(CONF_AI_TASK_ENTITY, "")

    @property
    def ai_task_name(self) -> str:
        return self._config.get(CONF_AI_TASK_NAME, DEFAULT_AI_TASK_NAME)

    @property
    def threat_prompt(self) -> str:
        return self._config.get(CONF_THREAT_PROMPT, DEFAULT_THREAT_PROMPT)

    @property
    def threat_phrase(self) -> str:
        return self._config.get(CONF_THREAT_PHRASE, DEFAULT_THREAT_PHRASE)

    @property
    def llm_provider(self) -> str:
        return self._config.get(CONF_LLM_PROVIDER, "")

    @property
    def llm_prompt(self) -> str:
        return self._config.get(CONF_LLM_PROMPT, DEFAULT_PROMPT)

    @property
    def notify_service(self) -> str:
        return self._config.get(CONF_NOTIFY_SERVICE, "")

    @property
    def notify_on_threat(self) -> bool:
        return self._config.get(CONF_NOTIFY_ON_THREAT, DEFAULT_NOTIFY_ON_THREAT)

    @property
    def notify_on_all_clear(self) -> bool:
        return self._config.get(CONF_NOTIFY_ON_ALL_CLEAR, DEFAULT_NOTIFY_ON_ALL_CLEAR)

    @property
    def threat_title(self) -> str:
        return self._config.get(CONF_THREAT_TITLE, DEFAULT_THREAT_TITLE)

    @property
    def clear_title(self) -> str:
        return self._config.get(CONF_CLEAR_TITLE, DEFAULT_CLEAR_TITLE)

    @property
    def notify_include_photo(self) -> bool:
        return self._config.get(CONF_NOTIFY_INCLUDE_PHOTO, DEFAULT_NOTIFY_INCLUDE_PHOTO)

    @property
    def ai_task_enabled(self) -> bool:
        return bool(self.ai_task_entity)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_provider)

    @property
    def ai_analysis_enabled(self) -> bool:
        return self.ai_task_enabled or self.llm_enabled

    def get_camera_state(self, entity_id: str) -> CameraState:
        if entity_id not in self._states:
            self._states[entity_id] = CameraState()
        return self._states[entity_id]

    # -- coordinator plumbing -------------------------------------------------

    async def _async_update_data(self) -> dict[str, CameraState]:
        return dict(self._states)

    def start_listening(self) -> None:
        if self._unsub_listener is not None:
            return

        @callback
        def _state_changed(event: Event) -> None:
            entity_id = event.data.get("entity_id", "")
            if entity_id not in self.cameras:
                return
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if new_state is None or old_state is None:
                return
            if new_state.state != old_state.state and new_state.state in (
                "recording", "streaming", "motion",
            ):
                self.hass.async_create_task(
                    self.analyze_camera(entity_id),
                    f"yolo_analyze_{entity_id}",
                )

        self._unsub_listener = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, _state_changed
        )

    def stop_listening(self) -> None:
        if self._unsub_listener is not None:
            self._unsub_listener()
            self._unsub_listener = None

    # -- analysis pipeline ----------------------------------------------------

    async def analyze_camera(
        self, entity_id: str, *, force_llm: bool = False
    ) -> dict[str, Any]:
        """Grab a snapshot, run detection, optional AI threat analysis, notify."""
        _LOGGER.debug(
            "analyze_camera start: entity_id=%s, force_llm=%s, sidecar_url=%s",
            entity_id,
            force_llm,
            self.sidecar_url,
        )
        if entity_id in self._analyzing:
            _LOGGER.debug("Already analyzing %s, skipping", entity_id)
            return {}
        self._analyzing.add(entity_id)

        cam = self.get_camera_state(entity_id)
        result: dict[str, Any] = {"entity_id": entity_id}

        try:
            _LOGGER.debug("Fetching camera snapshot for entity_id=%s", entity_id)
            image = await async_get_image(self.hass, entity_id)
            image_b64 = base64.b64encode(image.content).decode("ascii")
            sidecar_result = await self._call_sidecar(image_b64)

            cam.inference_time_ms = sidecar_result.get("inference_time_ms", 0)
            detected = sidecar_result.get("detected", False)
            conf_max = sidecar_result.get("confidence_max", 0.0)
            det_count = sidecar_result.get("detection_count", 0)
            classes = sidecar_result.get("classes_detected", [])
            annotated_b64 = sidecar_result.get("annotated_image_base64")

            if annotated_b64:
                cam.last_image_base64 = annotated_b64

            cam.confidence = conf_max
            cam.detection_count = det_count
            cam.classes_detected = classes

            if not detected or conf_max < self.confidence_threshold:
                cam.detected = False
                cam.threat_detected = None
                result.update({
                    "detected": False,
                    "confidence": conf_max,
                    "detection_count": det_count,
                    "classes_detected": classes,
                })
                self.async_set_updated_data(dict(self._states))
                return result

            cam.detected = True
            cam.last_seen = datetime.now(tz=timezone.utc)

            saved_path: Path | None = None
            if self.save_annotated and annotated_b64:
                saved_path = await self._save_annotated_image(entity_id, annotated_b64)
                if saved_path:
                    cam.last_saved_image_path = str(saved_path)

            ai_text: str | None = None
            threat_detected: bool | None = None
            if self.ai_analysis_enabled or force_llm:
                ai_text = await self._run_ai_analysis(entity_id)
                cam.llm_result = ai_text
                if ai_text is not None:
                    threat_detected = self.threat_phrase in ai_text
                    cam.threat_detected = threat_detected

            result.update({
                "detected": True,
                "confidence": conf_max,
                "detection_count": det_count,
                "classes_detected": classes,
                "last_seen": cam.last_seen.isoformat(),
            })
            if ai_text:
                result["llm_summary"] = ai_text
                result["ai_analysis"] = ai_text
                result["threat_detected"] = threat_detected

            self.hass.bus.async_fire(EVENT_DETECTION, result)

            await self._maybe_send_notifications(
                entity_id=entity_id,
                ai_text=ai_text,
                confidence=conf_max,
                classes=classes,
                threat_detected=threat_detected,
                image_path=cam.last_saved_image_path,
            )

            self.async_set_updated_data(dict(self._states))
            return result

        except Exception as e:
            _LOGGER.exception("Error analyzing camera %s", entity_id)
            error_msg = str(e) or repr(e)
            return {
                "entity_id": entity_id,
                "error": True,
                "message": error_msg,
            }
        finally:
            self._analyzing.discard(entity_id)

    async def manual_analyze(
        self, entity_id: str, *, force_llm: bool = False
    ) -> dict[str, Any]:
        return await self.analyze_camera(entity_id, force_llm=force_llm)

    # -- sidecar call ---------------------------------------------------------

    async def _call_sidecar(self, image_b64: str) -> dict[str, Any]:
        url = f"{self.sidecar_url.rstrip('/')}/detect"
        payload = {
            "image_base64": image_b64,
            "confidence_threshold": self.confidence_threshold,
            "classes": self.detection_classes,
            "draw_boxes": self.draw_boxes,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            if not resp.is_success:
                try:
                    body = resp.json()
                    detail = (
                        body.get("detail")
                        if isinstance(body.get("detail"), str)
                        else resp.text
                    )
                except Exception:
                    detail = resp.text
                msg = detail or f"HTTP {resp.status_code}"
                raise ValueError(f"Sidecar error ({resp.status_code}): {msg}")
            return resp.json()

    # -- AI analysis ----------------------------------------------------------

    async def _run_ai_analysis(self, entity_id: str) -> str | None:
        if self.ai_task_enabled:
            text = await self._call_ai_task(entity_id)
            if text:
                return text
        if self.llm_enabled:
            return await self._call_llm_vision(entity_id)
        return None

    async def _call_ai_task(self, entity_id: str) -> str | None:
        try:
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "entity_id": self.ai_task_entity,
                    "task_name": self.ai_task_name,
                    "instructions": self.threat_prompt,
                    "attachments": [
                        {
                            "media_content_id": f"media-source://camera/{entity_id}",
                            "media_content_type": "image/jpeg",
                        }
                    ],
                },
                blocking=True,
                return_response=True,
            )
            if isinstance(response, dict):
                data = response.get("data")
                if data is not None:
                    return str(data)
                return response.get("response_text", str(response))
            return str(response) if response else None
        except Exception:
            _LOGGER.exception("AI Task call failed for %s", entity_id)
            return None

    async def _call_llm_vision(self, entity_id: str) -> str | None:
        if not self.llm_provider:
            return None
        try:
            response = await self.hass.services.async_call(
                "llmvision",
                "image_analyzer",
                {
                    "provider": self.llm_provider,
                    "message": self.llm_prompt,
                    "image_entity": [entity_id],
                    "max_tokens": 3000,
                    "target_width": 1280,
                    "include_filename": False,
                    "expose_images": False,
                    "generate_title": False,
                },
                blocking=True,
                return_response=True,
            )
            if isinstance(response, dict):
                return response.get("response_text", str(response))
            return str(response) if response else None
        except Exception:
            _LOGGER.exception("LLM Vision call failed for %s", entity_id)
            return None

    # -- helpers --------------------------------------------------------------

    async def _save_annotated_image(
        self, entity_id: str, annotated_b64: str
    ) -> Path | None:
        try:
            media_dir = Path(self.hass.config.path("media", "yolo_llm_vision"))
            media_dir.mkdir(parents=True, exist_ok=True)
            safe_name = entity_id.replace(".", "_")
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            filepath = media_dir / f"{safe_name}_{ts}.jpg"
            await self.hass.async_add_executor_job(
                filepath.write_bytes, base64.b64decode(annotated_b64)
            )
            return filepath
        except Exception:
            _LOGGER.exception("Failed to save annotated image for %s", entity_id)
            return None

    async def _maybe_send_notifications(
        self,
        entity_id: str,
        ai_text: str | None,
        confidence: float,
        classes: list[str],
        threat_detected: bool | None,
        image_path: str | None,
    ) -> None:
        if not self.notify_service:
            return

        class_str = ", ".join(classes) if classes else "object"
        camera_name = entity_id.split(".")[-1].replace("_", " ").title()

        if threat_detected is None:
            if not self.notify_on_threat:
                return
            title = f"{self.threat_title} — {camera_name}"
            message = (
                f"{class_str} detected (confidence: {confidence:.0%})\n\n"
                f"Detection: {class_str}"
            )
        elif threat_detected:
            if not self.notify_on_threat:
                return
            title = f"{self.threat_title} — {camera_name}"
            message = ai_text or f"Threat detected: {class_str} ({confidence:.0%})"
        else:
            if not self.notify_on_all_clear:
                return
            title = f"{self.clear_title} — {camera_name}"
            message = ai_text or f"No threat — {class_str} detected ({confidence:.0%})"

        await self._send_notification(
            title=title,
            message=message,
            image_path=image_path if self.notify_include_photo else None,
        )

    async def _send_notification(
        self,
        title: str,
        message: str,
        image_path: str | None = None,
    ) -> None:
        service_parts = self.notify_service.split(".", 1)
        if len(service_parts) != 2:
            _LOGGER.warning("Invalid notify service: %s", self.notify_service)
            return
        domain, service = service_parts
        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"title": title, "message": message},
                blocking=False,
            )
            if image_path and domain == "telegram_bot" and service == "send_message":
                await self.hass.services.async_call(
                    "telegram_bot",
                    "send_photo",
                    {"file": image_path, "caption": title},
                    blocking=False,
                )
        except Exception:
            _LOGGER.exception("Notification failed for service %s.%s", domain, service)

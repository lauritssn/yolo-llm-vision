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
    last_seen: datetime | None = None
    llm_result: str | None = None
    inference_time_ms: float = 0.0


class YoloLLMVisionCoordinator(DataUpdateCoordinator[dict[str, CameraState]]):
    """Coordinate YOLO detection and optional LLM Vision analysis."""

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
    def llm_provider(self) -> str:
        return self._config.get(CONF_LLM_PROVIDER, "")

    @property
    def llm_prompt(self) -> str:
        return self._config.get(CONF_LLM_PROMPT, DEFAULT_PROMPT)

    @property
    def notify_service(self) -> str:
        return self._config.get(CONF_NOTIFY_SERVICE, "")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_provider)

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
        """Grab a snapshot, run YOLO, optionally call LLM Vision."""
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
            _LOGGER.debug(
                "Snapshot received: entity_id=%s, size_bytes=%s, base64_len=%s",
                entity_id,
                len(image.content),
                len(image_b64),
            )

            yolo = await self._call_sidecar(image_b64)

            cam.inference_time_ms = yolo.get("inference_time_ms", 0)
            detected = yolo.get("detected", False)
            conf_max = yolo.get("confidence_max", 0.0)
            det_count = yolo.get("detection_count", 0)
            classes = yolo.get("classes_detected", [])
            annotated_b64 = yolo.get("annotated_image_base64")

            if annotated_b64:
                cam.last_image_base64 = annotated_b64

            cam.confidence = conf_max
            cam.detection_count = det_count
            cam.classes_detected = classes

            if not detected or conf_max < self.confidence_threshold:
                cam.detected = False
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

            if self.save_annotated and annotated_b64:
                await self._save_annotated_image(entity_id, annotated_b64)

            llm_text: str | None = None
            if self.llm_enabled or force_llm:
                llm_text = await self._call_llm_vision(entity_id)
                cam.llm_result = llm_text

            result.update({
                "detected": True,
                "confidence": conf_max,
                "detection_count": det_count,
                "classes_detected": classes,
                "last_seen": cam.last_seen.isoformat(),
            })
            if llm_text:
                result["llm_summary"] = llm_text

            self.hass.bus.async_fire(EVENT_DETECTION, result)

            if self.notify_service:
                await self._send_notification(
                    entity_id, llm_text, conf_max, classes
                )

            self.async_set_updated_data(dict(self._states))
            return result

        except Exception as e:
            _LOGGER.exception(
                "Error analyzing camera %s (exception above); returning error: true",
                entity_id,
            )
            return {
                "entity_id": entity_id,
                "error": True,
                "message": str(e),
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
        _LOGGER.debug(
            "Sidecar HTTP request: method=POST, url=%s, payload_keys=%s, image_base64_len=%s, confidence_threshold=%s, classes=%s, draw_boxes=%s",
            url,
            list(payload.keys()),
            len(image_b64),
            self.confidence_threshold,
            self.detection_classes,
            self.draw_boxes,
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                _LOGGER.debug(
                    "Sidecar HTTP response: url=%s, status_code=%s, body_preview=%s",
                    url,
                    resp.status_code,
                    (resp.text[:500] if resp.text else "(empty)"),
                )
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
                data = resp.json()
                _LOGGER.debug(
                    "Sidecar response JSON keys: %s",
                    list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                )
                return data
        except httpx.HTTPError as e:
            _LOGGER.exception(
                "Sidecar HTTP error: url=%s, method=POST, exception=%s",
                url,
                type(e).__name__,
            )
            raise
        except Exception as e:
            _LOGGER.exception(
                "Sidecar request failed (non-HTTP): url=%s, exception=%s",
                url,
                type(e).__name__,
            )
            raise

    # -- optional LLM Vision --------------------------------------------------

    async def _call_llm_vision(self, entity_id: str) -> str | None:
        if not self.llm_provider:
            return None
        try:
            response = await self.hass.services.async_call(
                "llmvision", "image_analyzer",
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
    ) -> None:
        try:
            media_dir = Path(self.hass.config.path("media", "yolo_llm_vision"))
            media_dir.mkdir(parents=True, exist_ok=True)
            safe_name = entity_id.replace(".", "_")
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            filepath = media_dir / f"{safe_name}_{ts}.jpg"
            await self.hass.async_add_executor_job(
                filepath.write_bytes, base64.b64decode(annotated_b64)
            )
        except Exception:
            _LOGGER.exception("Failed to save annotated image for %s", entity_id)

    async def _send_notification(
        self,
        entity_id: str,
        llm_text: str | None,
        confidence: float,
        classes: list[str],
    ) -> None:
        service_parts = self.notify_service.split(".", 1)
        if len(service_parts) != 2:
            return
        domain, service = service_parts
        class_str = ", ".join(classes) if classes else "object"
        message = (
            llm_text
            or f"{class_str} detected on {entity_id} (confidence: {confidence:.0%})"
        )
        try:
            await self.hass.services.async_call(
                domain, service,
                {"title": f"Detection — {entity_id}", "message": message},
                blocking=False,
            )
        except Exception:
            _LOGGER.exception("Notification failed for %s", entity_id)

"""DataUpdateCoordinator for RF-DETR + LLM Vision."""

from __future__ import annotations

import asyncio
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
    DEFAULT_SNAPSHOT_DELAY,
    DEFAULT_THREAT_PHRASE,
    DEFAULT_THREAT_PROMPT,
    DEFAULT_THREAT_TITLE,
    DOMAIN,
    DEFAULT_TEST_NOTIFICATION_PREFIX,
    EVENT_DETECTION,
    EVENT_TEST_COMPLETE,
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


class RfDetrVisionCoordinator(DataUpdateCoordinator[dict[str, CameraState]]):
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
                    f"rf_detr_analyze_{entity_id}",
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
                title_prefix="",
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

    async def test_pipeline(
        self,
        entity_id: str,
        *,
        send_notifications: bool = False,
        bypass_detection_gate: bool = False,
        force_ai: bool = True,
        notification_prefix: str = DEFAULT_TEST_NOTIFICATION_PREFIX,
        snapshot_delay_seconds: float = DEFAULT_SNAPSHOT_DELAY,
        use_camera_snapshot: bool = True,
    ) -> dict[str, Any]:
        """Run a step-by-step pipeline test and return a structured report."""
        camera_name = entity_id.split(".")[-1].replace("_", " ").title()
        report: dict[str, Any] = {
            "test": True,
            "entity_id": entity_id,
            "camera": camera_name,
            "steps": {},
            "ok": False,
        }

        health = await self._check_sidecar_health()
        report["steps"]["sidecar_health"] = health
        if not health.get("ok"):
            report["summary"] = "Sidecar health check failed — fix sidecar URL or start the add-on."
            await self._finalize_test_report(
                entity_id, report, send_notifications, notification_prefix, None
            )
            return report

        snapshot_path: str | None = None
        try:
            image_bytes, content_type, snapshot_meta = await self._grab_camera_frame(
                entity_id,
                snapshot_delay_seconds=snapshot_delay_seconds,
                use_camera_snapshot=use_camera_snapshot,
            )
            snapshot_path = snapshot_meta.get("snapshot_path")
            report["steps"]["snapshot"] = {
                "ok": True,
                "bytes": len(image_bytes),
                "content_type": content_type,
                **snapshot_meta,
            }
        except Exception as exc:
            report["steps"]["snapshot"] = {"ok": False, "error": str(exc)}
            report["summary"] = f"Could not grab camera snapshot: {exc}"
            await self._finalize_test_report(
                entity_id, report, send_notifications, notification_prefix, None
            )
            return report

        try:
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            sidecar_result = await self._call_sidecar(image_b64)
        except Exception as exc:
            report["steps"]["detection"] = {"ok": False, "error": str(exc)}
            report["summary"] = f"RF-DETR sidecar error: {exc}"
            await self._finalize_test_report(
                entity_id, report, send_notifications, notification_prefix, None
            )
            return report

        detected = sidecar_result.get("detected", False)
        conf_max = sidecar_result.get("confidence_max", 0.0)
        classes = sidecar_result.get("classes_detected", [])
        gate_passed = detected and conf_max >= self.confidence_threshold

        report["steps"]["detection"] = {
            "ok": True,
            "detected": detected,
            "confidence": conf_max,
            "detection_count": sidecar_result.get("detection_count", 0),
            "classes_detected": classes,
            "inference_time_ms": sidecar_result.get("inference_time_ms", 0),
            "threshold": self.confidence_threshold,
            "gate_passed": gate_passed,
        }
        report["steps"]["detection_gate"] = {
            "passed": gate_passed,
            "bypassed": bypass_detection_gate,
            "active": gate_passed or bypass_detection_gate,
        }

        continue_pipeline = gate_passed or bypass_detection_gate
        ai_text: str | None = None
        threat_detected: bool | None = None
        notify_image_path: str | None = snapshot_path

        annotated_b64 = sidecar_result.get("annotated_image_base64")
        if annotated_b64 and self.save_annotated:
            saved = await self._save_annotated_image(entity_id, annotated_b64)
            if saved and not notify_image_path:
                notify_image_path = str(saved)

        if continue_pipeline and force_ai:
            if self.ai_analysis_enabled:
                ai_text = await self._run_ai_analysis(
                    entity_id, snapshot_path=snapshot_path
                )
                if ai_text is not None:
                    threat_detected = self.threat_phrase in ai_text
                report["steps"]["ai_task"] = {
                    "ok": ai_text is not None,
                    "ran": True,
                    "entity": self.ai_task_entity or self.llm_provider,
                    "threat_detected": threat_detected,
                    "response_preview": (ai_text or "")[:500],
                }
            else:
                report["steps"]["ai_task"] = {
                    "ok": False,
                    "ran": False,
                    "reason": "No AI Task entity or LLM Vision provider configured",
                }
        elif not continue_pipeline:
            report["steps"]["ai_task"] = {
                "ok": True,
                "ran": False,
                "skipped": True,
                "reason": (
                    "Detection gate closed — nothing relevant detected. "
                    "Stand in view of the camera or set bypass_detection_gate: true."
                ),
            }
        else:
            report["steps"]["ai_task"] = {
                "ok": True,
                "ran": False,
                "skipped": True,
                "reason": "force_ai is false",
            }

        notification_step: dict[str, Any] = {
            "configured": bool(self.notify_service),
            "service": self.notify_service or None,
            "sent": False,
        }
        if send_notifications and self.notify_service:
            if continue_pipeline:
                sent = await self._maybe_send_notifications(
                    entity_id=entity_id,
                    ai_text=ai_text,
                    confidence=conf_max,
                    classes=classes,
                    threat_detected=threat_detected,
                    image_path=notify_image_path,
                    title_prefix=notification_prefix,
                )
                notification_step["production_style_sent"] = sent
            summary_sent = await self._send_test_summary_notification(
                entity_id=entity_id,
                report=report,
                prefix=notification_prefix,
                image_path=notify_image_path,
            )
            notification_step["sent"] = bool(
                notification_step.get("production_style_sent") or summary_sent
            )
            notification_step["test_summary_sent"] = summary_sent
        elif send_notifications:
            notification_step["reason"] = "No notify_service configured in integration"
        else:
            notification_step["reason"] = "send_notifications is false (dry run)"

        report["steps"]["notification"] = notification_step
        report["detected"] = detected
        report["confidence"] = conf_max
        report["classes_detected"] = classes
        if ai_text:
            report["ai_analysis"] = ai_text
            report["threat_detected"] = threat_detected

        report["ok"] = (
            health.get("ok")
            and report["steps"]["snapshot"].get("ok")
            and report["steps"]["detection"].get("ok")
            and (
                not send_notifications
                or notification_step.get("sent")
                or not self.notify_service
            )
        )
        report["summary"] = self._build_test_summary(report)
        await self._finalize_test_report(
            entity_id, report, send_notifications, notification_prefix, notify_image_path
        )
        return report

    async def _finalize_test_report(
        self,
        entity_id: str,
        report: dict[str, Any],
        send_notifications: bool,
        notification_prefix: str,
        image_path: str | None,
    ) -> None:
        if send_notifications and "notification" not in report.get("steps", {}):
            sent = await self._send_test_summary_notification(
                entity_id, report, notification_prefix, image_path
            )
            report.setdefault("steps", {})["notification"] = {
                "configured": bool(self.notify_service),
                "service": self.notify_service or None,
                "sent": sent,
                "test_summary_sent": sent,
            }
        self.hass.bus.async_fire(EVENT_TEST_COMPLETE, report)
        _LOGGER.info(
            "Pipeline test for %s (notify=%s): %s",
            report.get("entity_id"),
            send_notifications,
            report.get("summary"),
        )

    @staticmethod
    def _build_test_summary(report: dict[str, Any]) -> str:
        steps = report.get("steps", {})
        lines = [f"Pipeline test — {report.get('camera', 'camera')}"]

        health = steps.get("sidecar_health", {})
        lines.append(
            f"Sidecar: {'OK' if health.get('ok') else 'FAIL'} ({health.get('url', 'n/a')})"
        )

        snapshot = steps.get("snapshot", {})
        if snapshot.get("ok"):
            method = snapshot.get("method", "unknown")
            path = snapshot.get("snapshot_path")
            if path:
                lines.append(f"Snapshot: OK via {method} → {path}")
            else:
                lines.append(f"Snapshot: OK via {method} ({snapshot.get('bytes', 0)} bytes)")

        detection = steps.get("detection", {})
        if detection.get("ok"):
            if detection.get("gate_passed"):
                lines.append(
                    "RF-DETR: detected "
                    f"{', '.join(detection.get('classes_detected') or [])} "
                    f"({detection.get('confidence', 0):.0%})"
                )
            else:
                lines.append("RF-DETR: no relevant detection above threshold")
        elif detection:
            lines.append(f"RF-DETR: error — {detection.get('error', 'unknown')}")

        ai_step = steps.get("ai_task", {})
        if ai_step.get("ran"):
            status = "OK" if ai_step.get("ok") else "FAIL"
            threat = ai_step.get("threat_detected")
            threat_label = (
                "threat" if threat else "all clear" if threat is False else "n/a"
            )
            lines.append(f"AI Task: {status} ({threat_label})")
        elif ai_step.get("skipped"):
            lines.append(f"AI Task: skipped — {ai_step.get('reason', '')}")

        notify = steps.get("notification", {})
        if notify.get("sent"):
            lines.append(f"Notify: sent via {notify.get('service')}")
        elif notify.get("configured") is False:
            lines.append("Notify: not configured")
        else:
            lines.append(f"Notify: {notify.get('reason', 'not sent')}")

        return "\n".join(lines)

    async def _send_test_summary_notification(
        self,
        entity_id: str,
        report: dict[str, Any],
        prefix: str,
        image_path: str | None,
    ) -> bool:
        if not self.notify_service:
            return False
        camera_name = entity_id.split(".")[-1].replace("_", " ").title()
        title = f"{prefix}Pipeline test — {camera_name}"
        message = report.get("summary") or self._build_test_summary(report)
        return await self._send_notification(
            title=title,
            message=message,
            image_path=image_path if self.notify_include_photo else None,
        )

    async def _check_sidecar_health(self) -> dict[str, Any]:
        url = f"{self.sidecar_url.rstrip('/')}/health"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                body: dict[str, Any] = {}
                if resp.is_success:
                    try:
                        parsed = resp.json()
                        if isinstance(parsed, dict):
                            body = parsed
                    except Exception:
                        body = {"raw": resp.text[:200]}
                return {
                    "ok": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "url": url,
                    "body": body,
                }
        except Exception as exc:
            return {"ok": False, "url": url, "error": str(exc)}

    async def _grab_camera_frame(
        self,
        entity_id: str,
        *,
        snapshot_delay_seconds: float = DEFAULT_SNAPSHOT_DELAY,
        use_camera_snapshot: bool = True,
    ) -> tuple[bytes, str, dict[str, Any]]:
        """Grab a frame from the camera — same flow as the security blueprint."""
        meta: dict[str, Any] = {}

        if use_camera_snapshot:
            snapshot_path = self._build_snapshot_path(entity_id, prefix="rf_detr_test")
            meta["snapshot_path"] = snapshot_path
            try:
                await self.hass.services.async_call(
                    "camera",
                    "snapshot",
                    {"entity_id": entity_id, "filename": snapshot_path},
                    blocking=True,
                )
                meta["method"] = "camera.snapshot"
                if snapshot_delay_seconds > 0:
                    meta["delay_seconds"] = snapshot_delay_seconds
                    await asyncio.sleep(snapshot_delay_seconds)

                image_bytes = await self.hass.async_add_executor_job(
                    Path(snapshot_path).read_bytes
                )
                if not image_bytes:
                    raise ValueError(f"Snapshot file is empty: {snapshot_path}")
                meta["bytes"] = len(image_bytes)
                return image_bytes, "image/jpeg", meta
            except Exception as exc:
                meta["snapshot_error"] = str(exc)
                _LOGGER.warning(
                    "camera.snapshot failed for %s, falling back to live frame: %s",
                    entity_id,
                    exc,
                )

        image = await async_get_image(self.hass, entity_id)
        meta["method"] = "async_get_image"
        meta["bytes"] = len(image.content)
        return image.content, image.content_type, meta

    @staticmethod
    def _build_snapshot_path(entity_id: str, *, prefix: str) -> str:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_id = entity_id.replace(".", "_")
        return f"/config/www/{prefix}_{safe_id}_{stamp}.jpg"

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

    async def _run_ai_analysis(
        self, entity_id: str, *, snapshot_path: str | None = None
    ) -> str | None:
        if self.ai_task_enabled:
            text = await self._call_ai_task(entity_id, snapshot_path=snapshot_path)
            if text:
                return text
        if self.llm_enabled:
            return await self._call_llm_vision(entity_id)
        return None

    async def _call_ai_task(
        self, entity_id: str, *, snapshot_path: str | None = None
    ) -> str | None:
        if snapshot_path:
            attachment = {
                "media_content_id": f"/local/{Path(snapshot_path).name}",
                "media_content_type": "image/jpeg",
            }
        else:
            attachment = {
                "media_content_id": f"media-source://camera/{entity_id}",
                "media_content_type": "image/jpeg",
            }
        try:
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "entity_id": self.ai_task_entity,
                    "task_name": self.ai_task_name,
                    "instructions": self.threat_prompt,
                    "attachments": [attachment],
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
            media_dir = Path(self.hass.config.path("media", "rf_detr_vision"))
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
        title_prefix: str = "",
    ) -> bool:
        if not self.notify_service:
            return False

        class_str = ", ".join(classes) if classes else "object"
        camera_name = entity_id.split(".")[-1].replace("_", " ").title()

        if threat_detected is None:
            if not self.notify_on_threat:
                return False
            title = f"{title_prefix}{self.threat_title} — {camera_name}"
            message = (
                f"{class_str} detected (confidence: {confidence:.0%})\n\n"
                f"Detection: {class_str}"
            )
        elif threat_detected:
            if not self.notify_on_threat:
                return False
            title = f"{title_prefix}{self.threat_title} — {camera_name}"
            message = ai_text or f"Threat detected: {class_str} ({confidence:.0%})"
        else:
            if not self.notify_on_all_clear:
                return False
            title = f"{title_prefix}{self.clear_title} — {camera_name}"
            message = ai_text or f"No threat — {class_str} detected ({confidence:.0%})"

        return await self._send_notification(
            title=title,
            message=message,
            image_path=image_path if self.notify_include_photo else None,
        )

    async def _send_notification(
        self,
        title: str,
        message: str,
        image_path: str | None = None,
    ) -> bool:
        service_parts = self.notify_service.split(".", 1)
        if len(service_parts) != 2:
            _LOGGER.warning("Invalid notify service: %s", self.notify_service)
            return False
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
            return True
        except Exception:
            _LOGGER.exception("Notification failed for service %s.%s", domain, service)
            return False

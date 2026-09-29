"""RF-DETR instance-segmentation sidecar — FastAPI + Roboflow RF-DETR-Seg."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
import supervision as sv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator
from rfdetr import (
    RFDETRSegLarge,
    RFDETRSegMedium,
    RFDETRSegNano,
    RFDETRSegSmall,
    from_checkpoint,
)
from rfdetr.assets.coco_classes import COCO_CLASSES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rfdetr_sidecar")

RFDETR_MODEL = os.getenv("RFDETR_MODEL", "nano").lower()
RFDETR_CHECKPOINT = os.getenv("RFDETR_CHECKPOINT", "")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
MODELS_DIR = Path(os.getenv("MODELS_DIR", "/models"))
STATIC_DIR = Path(__file__).resolve().parent / "static"
PORT = int(os.getenv("PORT", "8000"))

# RF-DETR COCO classes are 1-indexed; expose 0-indexed IDs in the API (COCO standard).
COCO_NAMES: dict[int, str] = {idx - 1: name for idx, name in COCO_CLASSES.items()}
COCO_NAME_TO_ID: dict[str, int] = {name: idx - 1 for idx, name in COCO_CLASSES.items()}

MODEL_CLASSES = {
    "nano": RFDETRSegNano,
    "small": RFDETRSegSmall,
    "medium": RFDETRSegMedium,
    "large": RFDETRSegLarge,
}

# Light green overlay for all segmentation masks (BGR for OpenCV, RGB for supervision).
LIGHT_GREEN = sv.Color(r=144, g=238, b=144)
MASK_ANNOTATOR = sv.MaskAnnotator(
    color=LIGHT_GREEN,
    color_lookup=sv.ColorLookup.INDEX,
    opacity=0.45,
)
BOX_ANNOTATOR = sv.BoxAnnotator(
    color=LIGHT_GREEN,
    color_lookup=sv.ColorLookup.INDEX,
    thickness=2,
)

_executor = ThreadPoolExecutor(max_workers=4)
_model: Any | None = None
_active_model_label: str = f"seg-{RFDETR_MODEL}"
_model_ready: bool = False
_model_error: str | None = None


async def _load_model_background() -> None:
    """Load RF-DETR in the background so /health responds before the model is ready."""
    global _model_ready, _model_error  # noqa: PLW0603
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_executor, _load_model)
        _model_ready = True
        logger.info(
            "Sidecar ready — task=segmentation, model=%s, threshold=%.2f",
            _active_model_label,
            CONFIDENCE_THRESHOLD,
        )
    except Exception as exc:
        _model_error = str(exc)
        logger.exception("Model load failed")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    load_task = asyncio.create_task(_load_model_background())
    logger.info(
        "Sidecar HTTP server started — loading RF-DETR model %s in background",
        RFDETR_MODEL,
    )
    yield
    load_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await load_task


def _load_model() -> Any:
    global _model, _active_model_label  # noqa: PLW0603
    if _model is not None:
        return _model

    if RFDETR_CHECKPOINT:
        checkpoint_path = Path(RFDETR_CHECKPOINT)
        if not checkpoint_path.is_absolute():
            checkpoint_path = MODELS_DIR / RFDETR_CHECKPOINT
        if checkpoint_path.is_file():
            logger.info("Loading RF-DETR checkpoint: %s", checkpoint_path)
            _model = from_checkpoint(str(checkpoint_path))
            _active_model_label = checkpoint_path.name
            logger.info("Checkpoint loaded successfully")
            return _model
        logger.warning("Checkpoint not found at %s, falling back to size preset", checkpoint_path)

    model_cls = MODEL_CLASSES.get(RFDETR_MODEL, RFDETRSegNano)
    logger.info("Loading RF-DETR-Seg preset: %s", RFDETR_MODEL)
    _model = model_cls()
    _active_model_label = f"seg-{RFDETR_MODEL}"
    logger.info("Model loaded successfully")
    return _model


app = FastAPI(
    title="RF-DETR Segmentation Sidecar",
    version="2.2.0",
    lifespan=lifespan,
)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root() -> dict[str, str]:
    """Root route to avoid 404 when hitting the sidecar base URL."""
    return {
        "service": "RF-DETR segmentation sidecar",
        "task": "segmentation",
        "try": "/try",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/try")
async def try_demo() -> FileResponse:
    """Interactive demo page for testing segmentation on sample images."""
    page = STATIC_DIR / "try.html"
    if not page.is_file():
        raise HTTPException(status_code=404, detail="Demo page not found")
    return FileResponse(page, media_type="text/html")


class DetectRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None
    entity_id: str | None = None
    ha_url: str | None = None
    ha_token: str | None = None
    confidence_threshold: float | None = None
    classes: list[str] | None = None
    draw_boxes: bool = True

    @model_validator(mode="after")
    def validate_input(self) -> "DetectRequest":
        has_url = self.image_url is not None
        has_b64 = self.image_base64 is not None
        has_entity = self.entity_id is not None
        if not (has_url or has_b64 or has_entity):
            raise ValueError("Provide one of: image_url, image_base64, or entity_id + ha_url + ha_token")
        if has_entity and (self.ha_url is None or self.ha_token is None):
            raise ValueError("entity_id requires ha_url and ha_token")
        return self


async def _fetch_image_bytes(req: DetectRequest) -> bytes:
    if req.image_base64:
        return base64.b64decode(req.image_base64)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:  # noqa: S501
        if req.entity_id:
            url = f"{req.ha_url.rstrip('/')}/api/camera_proxy/{req.entity_id}"
            headers = {"Authorization": f"Bearer {req.ha_token}"}
        else:
            url = req.image_url  # type: ignore[assignment]
            headers = {}
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content


def _resolve_class_ids(class_names: list[str] | None) -> set[int] | None:
    """Convert class name list to 0-indexed COCO class IDs. None = accept all."""
    if not class_names:
        return None
    ids: set[int] = set()
    for name in class_names:
        name_lower = name.strip().lower()
        if name_lower in COCO_NAME_TO_ID:
            ids.add(COCO_NAME_TO_ID[name_lower])
        else:
            logger.warning("Unknown class name '%s', skipping", name)
    return ids if ids else None


def _mask_to_segment(mask: np.ndarray, img_height: int, img_width: int) -> dict[str, Any]:
    """Convert a boolean mask to structured segment metadata."""
    area_pixels = int(mask.sum())
    total_pixels = img_height * img_width
    area_percent = round(100.0 * area_pixels / total_pixels, 2) if total_pixels else 0.0

    if area_pixels == 0:
        return {
            "area_pixels": 0,
            "area_percent": 0.0,
            "centroid": [0.0, 0.0],
            "polygon": [],
        }

    ys, xs = np.where(mask)
    if len(xs) == 0:
        return {
            "area_pixels": 0,
            "area_percent": 0.0,
            "centroid": [0.0, 0.0],
            "polygon": [],
        }

    centroid = [round(float(xs.mean()), 1), round(float(ys.mean()), 1)]
    polygon: list[list[float]] = []
    mask_uint8 = (mask.astype(np.uint8) * 255)
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        epsilon = 0.002 * cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, epsilon, True)
        polygon = [[round(float(p[0][0]), 1), round(float(p[0][1]), 1)] for p in approx]

    return {
        "area_pixels": area_pixels,
        "area_percent": area_percent,
        "centroid": centroid,
        "polygon": polygon,
    }


def _annotate_segmentation(img: np.ndarray, results: sv.Detections) -> np.ndarray:
    """Draw instance segmentation masks, boxes, and labels on the image."""
    labels = [
        f"{COCO_NAMES.get(int(results.class_id[i]) - 1, f'class_{results.class_id[i]}')} {results.confidence[i]:.0%}"
        for i in range(len(results))
    ]
    annotated = MASK_ANNOTATOR.annotate(img.copy(), results)
    annotated = BOX_ANNOTATOR.annotate(annotated, results)
    return sv.LabelAnnotator().annotate(annotated, results, labels)


def _run_inference(
    image_bytes: bytes,
    threshold: float,
    allowed_class_ids: set[int] | None,
    draw_annotations: bool,
) -> dict[str, Any]:
    model = _load_model()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    img_height, img_width = img.shape[:2]

    t0 = time.perf_counter()
    results = model.predict(img, threshold=threshold)
    inference_ms = (time.perf_counter() - t0) * 1000

    kept_indices: list[int] = []
    detections: list[dict[str, Any]] = []
    for i in range(len(results)):
        cls_id_rfdetr = int(results.class_id[i])
        cls_id = cls_id_rfdetr - 1  # 0-indexed for API compatibility
        conf = float(results.confidence[i])
        if conf < threshold:
            continue
        if allowed_class_ids is not None and cls_id not in allowed_class_ids:
            continue
        class_name = COCO_NAMES.get(cls_id, f"class_{cls_id}")
        x1, y1, x2, y2 = [round(float(c), 1) for c in results.xyxy[i]]
        segment: dict[str, Any] | None = None
        if results.mask is not None:
            segment = _mask_to_segment(results.mask[i], img_height, img_width)

        kept_indices.append(i)
        detections.append({
            "id": len(detections),
            "class": class_name,
            "class_id": cls_id,
            "confidence": round(conf, 4),
            "bbox": [x1, y1, x2, y2],
            "segment": segment,
        })

    annotated_b64: str | None = None
    if draw_annotations and kept_indices:
        filtered = results[kept_indices]
        annotated = _annotate_segmentation(img, filtered)
        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

    classes_found = sorted(set(d["class"] for d in detections))
    confidences = [d["confidence"] for d in detections]

    result: dict[str, Any] = {
        "detected": len(detections) > 0,
        "detection_count": len(detections),
        "classes_detected": classes_found,
        "confidence_max": round(max(confidences), 4) if confidences else 0.0,
        "confidence_avg": round(sum(confidences) / len(confidences), 4) if confidences else 0.0,
        "detections": detections,
        "inference_time_ms": round(inference_ms, 1),
        "task": "segmentation",
        "model": {
            "engine": "rf-detr-seg",
            "preset": _active_model_label,
        },
        "image": {
            "width": img_width,
            "height": img_height,
        },
    }
    if annotated_b64:
        result["annotated_image_base64"] = annotated_b64
    return result


def _ensure_model_ready() -> None:
    if _model_error:
        raise HTTPException(
            status_code=503,
            detail=f"Model load failed: {_model_error}",
        )
    if not _model_ready:
        raise HTTPException(
            status_code=503,
            detail="Model still loading — retry in a few minutes on first start",
        )


@app.post("/detect")
async def detect(req: DetectRequest) -> JSONResponse:
    _ensure_model_ready()
    try:
        image_bytes = await _fetch_image_bytes(req)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    threshold = req.confidence_threshold if req.confidence_threshold is not None else CONFIDENCE_THRESHOLD
    allowed_ids = _resolve_class_ids(req.classes)

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _run_inference, image_bytes, threshold, allowed_ids, req.draw_boxes
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}") from exc

    logger.info(
        "Segment: count=%d, classes=%s, conf_max=%.2f, time=%.0fms",
        result["detection_count"],
        result["classes_detected"],
        result["confidence_max"],
        result["inference_time_ms"],
    )
    return JSONResponse(content=result)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — returns 200 while the model loads (status=starting)."""
    if _model_error:
        return {
            "status": "error",
            "error": _model_error,
            "model": _active_model_label,
            "engine": "rf-detr-seg",
            "task": "segmentation",
        }
    if not _model_ready:
        return {
            "status": "starting",
            "model": _active_model_label,
            "engine": "rf-detr-seg",
            "task": "segmentation",
        }
    return {
        "status": "ok",
        "model": _active_model_label,
        "engine": "rf-detr-seg",
        "task": "segmentation",
    }


@app.get("/models")
async def list_models() -> dict[str, Any]:
    available: list[str] = sorted(f.name for f in MODELS_DIR.glob("*.pt")) if MODELS_DIR.exists() else []
    available += sorted(f.name for f in MODELS_DIR.glob("*.pth")) if MODELS_DIR.exists() else []
    return {
        "active": _active_model_label,
        "task": "segmentation",
        "presets": list(MODEL_CLASSES.keys()),
        "checkpoints": sorted(set(available)),
    }


@app.get("/classes")
async def list_classes() -> dict[str, list[str]]:
    """Return all COCO class names the model can detect."""
    return {"classes": list(COCO_NAMES.values())}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)  # noqa: S104

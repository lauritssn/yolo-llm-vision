"""YOLO object-detection sidecar — FastAPI + YOLOv8."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yolo_sidecar")

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
MODELS_DIR = Path("/models")
PORT = int(os.getenv("PORT", "8000"))

# COCO-80 class name lookup (standard YOLOv8)
COCO_NAMES: dict[int, str] = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep",
    19: "cow", 20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe",
    24: "backpack", 25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase",
    29: "frisbee", 30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite",
    34: "baseball bat", 35: "baseball glove", 36: "skateboard", 37: "surfboard",
    38: "tennis racket", 39: "bottle", 40: "wine glass", 41: "cup", 42: "fork",
    43: "knife", 44: "spoon", 45: "bowl", 46: "banana", 47: "apple",
    48: "sandwich", 49: "orange", 50: "broccoli", 51: "carrot", 52: "hot dog",
    53: "pizza", 54: "donut", 55: "cake", 56: "chair", 57: "couch",
    58: "potted plant", 59: "bed", 60: "dining table", 61: "toilet",
    62: "tv", 63: "laptop", 64: "mouse", 65: "remote", 66: "keyboard",
    67: "cell phone", 68: "microwave", 69: "oven", 70: "toaster", 71: "sink",
    72: "refrigerator", 73: "book", 74: "clock", 75: "vase", 76: "scissors",
    77: "teddy bear", 78: "hair drier", 79: "toothbrush",
}
COCO_NAME_TO_ID: dict[str, int] = {v: k for k, v in COCO_NAMES.items()}

BOX_COLORS: dict[str, tuple[int, int, int]] = {
    "person": (0, 255, 0),
    "dog": (255, 165, 0),
    "car": (255, 0, 0),
    "truck": (255, 0, 0),
}
DEFAULT_BOX_COLOR = (0, 200, 255)

_executor = ThreadPoolExecutor(max_workers=4)
_model: YOLO | None = None

app = FastAPI(title="YOLO Object Detection Sidecar", version="2.0.0")


def _load_model() -> YOLO:
    global _model  # noqa: PLW0603
    if _model is not None:
        return _model
    model_path = MODELS_DIR / YOLO_MODEL if (MODELS_DIR / YOLO_MODEL).exists() else YOLO_MODEL
    logger.info("Loading YOLO model: %s", model_path)
    _model = YOLO(str(model_path))
    logger.info("Model loaded successfully")
    return _model


@app.on_event("startup")
async def startup() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _load_model)
    logger.info("Sidecar ready — model=%s, threshold=%.2f", YOLO_MODEL, CONFIDENCE_THRESHOLD)


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
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:  # noqa: S501
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
    """Convert class name list to COCO class IDs. None = accept all."""
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


def _run_inference(
    image_bytes: bytes,
    threshold: float,
    allowed_class_ids: set[int] | None,
    draw_boxes: bool,
) -> dict[str, Any]:
    model = _load_model()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    t0 = time.perf_counter()
    results = model(img, verbose=False)[0]
    inference_ms = (time.perf_counter() - t0) * 1000

    detections: list[dict[str, Any]] = []
    for box in results.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        if conf < threshold:
            continue
        if allowed_class_ids is not None and cls_id not in allowed_class_ids:
            continue
        class_name = COCO_NAMES.get(cls_id, f"class_{cls_id}")
        x1, y1, x2, y2 = [float(c) for c in box.xyxy[0]]
        detections.append({
            "class": class_name,
            "class_id": cls_id,
            "confidence": round(conf, 4),
            "bbox": [x1, y1, x2, y2],
        })

    annotated_b64: str | None = None
    if draw_boxes and detections:
        annotated = img.copy()
        for det in detections:
            bx1, by1, bx2, by2 = [int(c) for c in det["bbox"]]
            color = BOX_COLORS.get(det["class"], DEFAULT_BOX_COLOR)
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, 2)
            label = f"{det['class']} {det['confidence']:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(annotated, (bx1, by1 - th - 8), (bx1 + tw, by1), color, -1)
            cv2.putText(annotated, label, (bx1, by1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
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
    }
    if annotated_b64:
        result["annotated_image_base64"] = annotated_b64
    return result


@app.post("/detect")
async def detect(req: DetectRequest) -> JSONResponse:
    try:
        image_bytes = await _fetch_image_bytes(req)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch image: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    threshold = req.confidence_threshold if req.confidence_threshold is not None else CONFIDENCE_THRESHOLD
    allowed_ids = _resolve_class_ids(req.classes)

    try:
        # Run in main thread so torch/numpy are available (executor threads can hit
        # "Numpy is not available" with torch 2.2 + numpy 2.x or thread init order).
        result = _run_inference(image_bytes, threshold, allowed_ids, req.draw_boxes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}") from exc

    logger.info(
        "Detect: count=%d, classes=%s, conf_max=%.2f, time=%.0fms",
        result["detection_count"],
        result["classes_detected"],
        result["confidence_max"],
        result["inference_time_ms"],
    )
    return JSONResponse(content=result)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": YOLO_MODEL}


@app.get("/models")
async def list_models() -> dict[str, list[str]]:
    models: list[str] = []
    if MODELS_DIR.exists():
        models = [f.name for f in MODELS_DIR.glob("*.pt")]
    return {"models": sorted(models)}


@app.get("/classes")
async def list_classes() -> dict[str, list[str]]:
    """Return all COCO class names the model can detect."""
    return {"classes": list(COCO_NAMES.values())}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)  # noqa: S104

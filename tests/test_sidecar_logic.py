"""Tests for sidecar pure logic and /health, /classes endpoints (no RF-DETR model)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = ROOT / "sidecar"
if str(SIDECAR) not in sys.path:
    sys.path.insert(0, str(SIDECAR))

_rfdetr = types.ModuleType("rfdetr")
_rfdetr.RFDETRSegNano = MagicMock(return_value=MagicMock())
_rfdetr.RFDETRSegSmall = MagicMock(return_value=MagicMock())
_rfdetr.RFDETRSegMedium = MagicMock(return_value=MagicMock())
_rfdetr.RFDETRSegLarge = MagicMock(return_value=MagicMock())
_rfdetr.from_checkpoint = MagicMock(return_value=MagicMock())

_coco = types.ModuleType("rfdetr.assets.coco_classes")
_coco.COCO_CLASSES = {i + 1: name for i, name in enumerate([
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog",
])}

_sv = MagicMock()
_cv2 = MagicMock()
_numpy = MagicMock()
with patch.dict(
    sys.modules,
    {
        "rfdetr": _rfdetr,
        "rfdetr.assets.coco_classes": _coco,
        "supervision": _sv,
        "cv2": _cv2,
        "numpy": _numpy,
    },
):
    import main as sidecar_main  # noqa: E402


def test_resolve_class_ids_person_dog() -> None:
    assert sidecar_main._resolve_class_ids(["person", "dog"]) == {0, 16}


def test_resolve_class_ids_unknown_returns_none() -> None:
    assert sidecar_main._resolve_class_ids(["unknown_class"]) is None


def test_resolve_class_ids_none_input_returns_none() -> None:
    assert sidecar_main._resolve_class_ids(None) is None


def test_resolve_class_ids_empty_list_returns_none() -> None:
    assert sidecar_main._resolve_class_ids([]) is None


def test_detect_request_requires_one_of_image_url_base64_entity_id() -> None:
    with pytest.raises(ValidationError):
        sidecar_main.DetectRequest()
    with pytest.raises(ValidationError):
        sidecar_main.DetectRequest(image_url=None, image_base64=None, entity_id=None)


def test_detect_request_entity_id_requires_ha_url_and_token() -> None:
    with pytest.raises(ValidationError):
        sidecar_main.DetectRequest(entity_id="camera.test", ha_url=None, ha_token=None)
    with pytest.raises(ValidationError):
        sidecar_main.DetectRequest(entity_id="camera.test", ha_url="http://ha", ha_token=None)
    with pytest.raises(ValidationError):
        sidecar_main.DetectRequest(entity_id="camera.test", ha_url=None, ha_token="token")


def test_detect_request_valid_image_url() -> None:
    r = sidecar_main.DetectRequest(image_url="http://example.com/img.jpg")
    assert r.image_url == "http://example.com/img.jpg"
    assert r.entity_id is None


def test_detect_request_valid_image_base64() -> None:
    r = sidecar_main.DetectRequest(image_base64="YWJj")
    assert r.image_base64 == "YWJj"


def test_detect_request_valid_entity_id_with_ha() -> None:
    r = sidecar_main.DetectRequest(
        entity_id="camera.door",
        ha_url="http://homeassistant:8123",
        ha_token="secret",
    )
    assert r.entity_id == "camera.door"
    assert r.ha_url == "http://homeassistant:8123"
    assert r.ha_token == "secret"


def test_coco_names_and_name_to_id_consistent() -> None:
    for idx, name in sidecar_main.COCO_NAMES.items():
        assert sidecar_main.COCO_NAME_TO_ID[name] == idx
    for name, idx in sidecar_main.COCO_NAME_TO_ID.items():
        assert sidecar_main.COCO_NAMES[idx] == name


def test_root_endpoint() -> None:
    """GET / returns service info and avoids 404."""
    client = TestClient(sidecar_main.app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "segmentation" in data.get("service", "")
    assert data.get("task") == "segmentation"
    assert data.get("try") == "/try"
    assert data.get("docs") == "/docs"
    assert data.get("health") == "/health"


def test_try_demo_page() -> None:
    """GET /try serves the interactive demo HTML."""
    client = TestClient(sidecar_main.app)
    resp = client.get("/try")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Try RF-DETR Segmentation" in resp.text


def test_health_endpoint() -> None:
    client = TestClient(sidecar_main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "starting")
    assert data["engine"] == "rf-detr-seg"
    assert data["task"] == "segmentation"
    assert "model" in data


def test_classes_endpoint() -> None:
    client = TestClient(sidecar_main.app)
    resp = client.get("/classes")
    assert resp.status_code == 200
    data = resp.json()
    assert "classes" in data
    assert isinstance(data["classes"], list)
    assert "person" in data["classes"]
    assert "dog" in data["classes"]


def test_mask_to_segment_empty_mask() -> None:
    import numpy as real_np

    segment = sidecar_main._mask_to_segment(real_np.zeros((10, 10), dtype=bool), 10, 10)
    assert segment["area_pixels"] == 0
    assert segment["polygon"] == []


import json

import pytest

from impad.tools.ocr_extract import OCRExtractInput, _ocr_extract_core, ocr_extract
from impad.tools.vision_context import VisionContext


def _context():
    return VisionContext.model_validate({
        "image_id": "sha256:test", "image_name": "promotion.jpg", "objects": [],
        "texts": [
            {"text": "限时 ￥99 已售100", "confidence": 0.95,
             "bbox": [10, 20, 120, 45]},
            {"text": "LOW", "confidence": 0.1, "bbox": [2, 2, 5, 5]},
        ],
        "focus": {"focus_point": [50, 50], "confidence": 0.8,
                  "method": "weighted_center", "num_objects": 0},
        "model_version": "YOLO11nano+EasyOCR-test",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    })


def test_ocr_extract_filters_blocks_and_keeps_bbox_evidence():
    result = _ocr_extract_core(OCRExtractInput(
        image_path="promotion.jpg", vision_context=_context(),
        min_confidence=0.3, detect_qr=False))
    assert result.status == "ok"
    assert result.payload["full_text"] == "限时 ￥99 已售100"
    assert len(result.payload["text_blocks"]) == 1
    assert result.evidence[0].bbox == [10, 20, 120, 45]
    assert {item["type"] for item in result.payload["sales_signals"]} >= {
        "price", "sales_volume", "promotion"}
    assert result.payload["context_reused"] is True
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_ocr_tool_invokes_with_serialized_context():
    result = ocr_extract.invoke({"image_path": "promotion.jpg",
        "vision_context": _context().model_dump(mode="json"), "detect_qr": False})
    assert result["tool_name"] == "ocr_extract"
    assert result["payload"]["vision_context"]["texts"][0]["bbox"] == [10, 20, 120, 45]


def test_ocr_missing_local_file_is_safe_error():
    result = _ocr_extract_core(OCRExtractInput(image_path="missing-local-image.jpg"))
    assert result.status == "error"
    assert result.score is None
    assert "missing-local-image.jpg" not in " ".join(result.warnings)


def test_ocr_input_rejects_remote_url():
    with pytest.raises(ValueError):
        OCRExtractInput(image_path="https://example.com/promo.jpg")

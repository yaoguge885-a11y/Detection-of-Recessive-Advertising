import json

import pytest

from impad.tools.detect_logo_product import (
    DetectLogoProductInput, _detect_logo_product_core, detect_logo_product,
)
from impad.tools.vision_context import VisionContext


def _context(objects=None, texts=None):
    return VisionContext.model_validate({
        "image_id": "sha256:product", "image_name": "product.jpg",
        "objects": objects or [], "texts": texts or [],
        "focus": {"focus_point": [50, 50], "confidence": 0.9,
                  "method": "weighted_center", "num_objects": len(objects or [])},
        "model_version": "YOLO11nano+EasyOCR-test",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    })


def test_detect_product_separates_objects_brand_candidates_and_logos():
    context = _context(
        objects=[
            {"class_name": "bottle", "confidence": 0.91,
             "bbox": [1, 2, 20, 40], "center": [10, 20]},
            {"class_name": "person", "confidence": 0.8,
             "bbox": [30, 2, 70, 90], "center": [50, 46]},
        ],
        texts=[{"text": "LANCOME", "confidence": 0.88, "bbox": [4, 5, 18, 12]}],
    )
    result = _detect_logo_product_core(DetectLogoProductInput(
        image_path="product.jpg", vision_context=context))
    assert result.status == "ok"
    assert [item["class_name"] for item in result.payload["commercial_objects"]] == ["bottle"]
    assert result.payload["brand_candidates"][0]["name"] == "LANCOME"
    assert result.payload["logo_candidates"] == []
    assert result.payload["capabilities"]["logo_detection"] == "none"
    assert any(item.bbox == [1, 2, 20, 40] for item in result.evidence)
    assert result.payload["context_reused"] is True
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False)


def test_detect_product_tool_invokes_independently():
    result = detect_logo_product.invoke({
        "image_path": "product.jpg",
        "vision_context": _context().model_dump(mode="json")})
    assert result["tool_name"] == "detect_logo_product"
    assert result["score"] == 0


def test_detect_product_rejects_remote_url():
    with pytest.raises(ValueError):
        DetectLogoProductInput(image_path="https://example.com/product.jpg")

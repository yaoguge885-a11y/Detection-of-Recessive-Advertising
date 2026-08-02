import json

import pytest

from impad.tools.image_text_consistency import (
    ImageTextConsistencyInput, _image_text_consistency_core, image_text_consistency,
)
from impad.tools.vision_context import VisionContext


def _context(*, ocr_text="", object_name=None):
    objects = []
    if object_name:
        objects.append({"class_name": object_name, "confidence": 0.9,
                        "bbox": [1, 2, 20, 40], "center": [10, 20]})
    texts = []
    if ocr_text:
        texts.append({"text": ocr_text, "confidence": 0.9, "bbox": [4, 5, 80, 20]})
    return VisionContext.model_validate({
        "image_id": "sha256:consistency", "image_name": "consistency.jpg",
        "objects": objects, "texts": texts,
        "focus": {"focus_point": [10, 20], "confidence": 0.9,
                  "method": "weighted_center", "num_objects": len(objects)},
        "model_version": "YOLO11nano+EasyOCR-test",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    })


def test_consistency_aligned_scores_above_random_mismatch():
    aligned = _image_text_consistency_core(ImageTextConsistencyInput(
        text="今天带小狗去公园散步", image_path="consistency.jpg",
        vision_context=_context(ocr_text="带小狗去公园散步", object_name="dog")))
    mismatch = _image_text_consistency_core(ImageTextConsistencyInput(
        text="今天带小狗去公园散步", image_path="consistency.jpg",
        vision_context=_context(ocr_text="面霜限时优惠扫码下单", object_name="bottle")))
    assert aligned.status == "degraded"
    assert aligned.payload["relation"] == "aligned"
    assert mismatch.payload["relation"] == "conflicting"
    assert aligned.score > mismatch.score
    assert aligned.payload["context_reused"] is True
    assert mismatch.payload["conflicting_evidence"]


def test_consistency_insufficient_visual_evidence_is_skipped():
    result = _image_text_consistency_core(ImageTextConsistencyInput(
        text="普通生活记录", image_path="consistency.jpg", vision_context=_context()))
    assert result.status == "skipped"
    assert result.score is None
    assert result.payload["relation"] == "insufficient"


def test_consistency_empty_text_is_skipped():
    result = _image_text_consistency_core(ImageTextConsistencyInput(
        text="", image_path="consistency.jpg", vision_context=_context(ocr_text="促销")))
    assert result.status == "skipped"


def test_consistency_tool_is_json_serializable_and_has_no_ad_verdict():
    result = image_text_consistency.invoke({
        "text": "手机拍照效果很好", "image_path": "consistency.jpg",
        "vision_context": _context(object_name="cell phone").model_dump(mode="json")})
    assert result["tool_name"] == "image_text_consistency"
    assert "verdict" not in result["payload"]
    json.dumps(result, ensure_ascii=False)


def test_consistency_rejects_remote_url():
    with pytest.raises(ValueError):
        ImageTextConsistencyInput(text="x", image_path="https://example.com/image.jpg")

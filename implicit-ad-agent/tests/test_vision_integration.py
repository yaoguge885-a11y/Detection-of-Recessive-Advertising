"""Opt-in tests for the installed YOLO/EasyOCR stack on real images."""
from __future__ import annotations

import json

import pytest

import impad.tools.vision as vision
from impad.tools.detect_logo_product import (
    DetectLogoProductInput,
    _detect_logo_product_core,
)
from impad.tools.image_text_consistency import (
    ImageTextConsistencyInput,
    _image_text_consistency_core,
)
from impad.tools.ocr_extract import OCRExtractInput, _ocr_extract_core
from impad.tools.vision_context import build_vision_context, clear_vision_context_cache


pytestmark = pytest.mark.vision_integration


def test_real_yolo_detects_dog_in_fixed_sample():
    clear_vision_context_cache()
    context = build_vision_context(
        "samples/images/test_dog.jpg", enable_ocr=True, use_cache=False
    )

    assert context.capabilities["object_detection"] is True
    assert context.capabilities["ocr"] is True
    dog = next(item for item in context.objects if item.class_name == "dog")
    assert dog.confidence >= 0.7
    assert len(dog.bbox) == 4
    json.dumps(context.model_dump(mode="json"), ensure_ascii=False)


def test_real_ocr_and_three_tools_reuse_one_context(tmp_path, monkeypatch):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    image_path = tmp_path / "sale-99.png"
    image = np.full((360, 1000, 3), 255, dtype=np.uint8)
    cv2.putText(
        image, "SALE 99", (70, 225), cv2.FONT_HERSHEY_SIMPLEX,
        4, (0, 0, 0), 10, cv2.LINE_AA,
    )
    assert cv2.imwrite(str(image_path), image)

    clear_vision_context_cache()
    context = build_vision_context(str(image_path), enable_ocr=True, use_cache=False)
    assert context.capabilities["ocr"] is True
    assert any("SALE" in block.text.upper() and "99" in block.text for block in context.texts)

    # Once the context exists, none of the three tools may invoke YOLO/OCR again.
    monkeypatch.setattr(
        vision,
        "analyze_image",
        lambda *args, **kwargs: pytest.fail("visual inference was repeated"),
    )
    ocr = _ocr_extract_core(OCRExtractInput(
        image_path=str(image_path), vision_context=context, detect_qr=False,
    ))
    products = _detect_logo_product_core(DetectLogoProductInput(
        image_path=str(image_path), vision_context=context,
    ))
    consistency = _image_text_consistency_core(ImageTextConsistencyInput(
        text="SALE 99", image_path=str(image_path), vision_context=context,
    ))

    assert ocr.status == "ok"
    assert products.status == "ok"
    assert consistency.status == "degraded"
    assert consistency.payload["relation"] == "aligned"
    for result in (ocr, products, consistency):
        assert result.payload["context_reused"] is True
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

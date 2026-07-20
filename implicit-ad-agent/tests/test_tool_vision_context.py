import pytest

import impad.tools.vision as vision
from impad.tools.vision_context import (
    VisionContext,
    build_vision_context,
    clear_vision_context_cache,
    resolve_vision_context,
    validate_local_image_path,
)


def test_context_keeps_structured_findings_and_reuses_result(tmp_path, monkeypatch):
    image = tmp_path / "sample.jpg"
    image.write_bytes(b"stable-image-content")
    calls = []
    monkeypatch.setattr(vision, "vision_available", lambda: True)

    def fake_analyze(path, model_size="nano", enable_ocr=True):
        calls.append(path)
        return {
            "model_version": "YOLO11nano+EasyOCR-test", "ocr_available": True,
            "objects": [{"class_name": "bottle", "confidence": 0.9,
                         "bbox": [1, 2, 11, 22], "class_id": 39, "center": [6, 12]}],
            "texts": [{"text": "TEST", "confidence": 0.8, "bbox": [2, 3, 8, 9]}],
            "focus": {"focus_point": [6, 12], "confidence": 0.9,
                      "method": "weighted_center", "num_objects": 1},
        }

    monkeypatch.setattr(vision, "analyze_image", fake_analyze)
    clear_vision_context_cache()
    first = build_vision_context(str(image))
    second = build_vision_context(str(image))
    assert first == second
    assert len(calls) == 1
    assert first.image_id.startswith("sha256:")
    assert first.objects[0].bbox == [1, 2, 11, 22]
    assert first.texts[0].bbox == [2, 3, 8, 9]
    assert first.focus.focus_point == [6, 12]
    assert first.model_version == "YOLO11nano+EasyOCR-test"


@pytest.mark.parametrize("source", ["https://example.com/a.jpg", "data:image/png;base64,AA"])
def test_context_rejects_remote_sources(source):
    with pytest.raises(ValueError):
        validate_local_image_path(source)


def test_context_accepts_windows_local_path():
    assert validate_local_image_path(r"C:\images\a.jpg") == r"C:\images\a.jpg"


def test_context_cannot_be_reused_for_a_different_image_name():
    context = VisionContext(image_id="sha256:test", image_name="first.jpg",
                            model_version="test-v1")
    with pytest.raises(ValueError):
        resolve_vision_context("second.jpg", context)

import json
from pathlib import Path

from impad.tools.image_text_consistency import (
    ImageTextConsistencyInput, _image_text_consistency_core,
)
from impad.tools.vision_context import VisionContext


DATASET = Path(__file__).parents[1] / "samples" / "vision_consistency_sanity.json"


def _context(case):
    return VisionContext.model_validate({
        "image_id": f"sha256:{case['case_id']}",
        "image_name": f"{case['case_id']}.jpg",
        "objects": [{"class_name": case["object"], "confidence": 0.9,
                     "bbox": [10, 20, 180, 300], "center": [95, 160]}],
        "texts": [{"text": case["ocr_text"], "confidence": 0.9,
                   "bbox": [20, 30, 160, 70]}],
        "focus": {"focus_point": [95, 160], "confidence": 0.9,
                  "method": "weighted_center", "num_objects": 1},
        "model_version": "synthetic-sanity-v1",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    })


def test_thirty_pair_sanity_set_has_correct_score_direction():
    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(cases) == 30
    scores = {"aligned": [], "conflicting": []}
    for case in cases:
        result = _image_text_consistency_core(ImageTextConsistencyInput(
            text=case["text"], image_path=f"{case['case_id']}.jpg",
            vision_context=_context(case)))
        assert result.status == "degraded"
        assert result.payload["relation"] == case["expected"]
        scores[case["expected"]].append(result.score)
    aligned_mean = sum(scores["aligned"]) / len(scores["aligned"])
    conflicting_mean = sum(scores["conflicting"]) / len(scores["conflicting"])
    assert aligned_mean > conflicting_mean + 0.35

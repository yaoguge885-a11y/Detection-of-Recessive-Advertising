from __future__ import annotations

import json
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "validate_qwen_calibration_reviews.py"
SPEC = importlib.util.spec_from_file_location("validate_qwen_calibration_reviews", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
validate = MODULE.validate


def write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = {
        "dataset_fingerprint_sha256": "abc",
        "items": [{"post_id": "p1"}, {"post_id": "p2"}],
    }
    base_items = [
        {
            "number": number,
            "post_id": post_id,
            "label": "非广",
            "reasonable": "yes",
            "saved_time": "no",
            "error_type": "none",
            "reviewed": True,
            "notes": "人工证据说明",
        }
        for number, post_id in enumerate(("p1", "p2"), start=1)
    ]
    def review(reviewer: str) -> dict:
        return {
            "status": "completed_independent_human_review",
            "reviewer": reviewer,
            "dataset_fingerprint_sha256": "abc",
            "sample_count": 2,
            "items": base_items,
        }
    return (
        write(tmp_path / "manifest.json", manifest),
        write(tmp_path / "a.json", review("A")),
        write(tmp_path / "b.json", review("B")),
    )


def test_valid_pair_produces_comparison(tmp_path: Path) -> None:
    manifest, a_path, b_path = fixtures(tmp_path)
    result = validate(manifest, {"A": a_path, "B": b_path})
    assert result["passed"] is True
    assert result["comparison"]["human_label_agreement_count"] == 2
    assert result["comparison"]["final_model_choice"] == "pending_A_B_joint_decision"


def test_blank_note_fails(tmp_path: Path) -> None:
    manifest, a_path, _ = fixtures(tmp_path)
    payload = json.loads(a_path.read_text(encoding="utf-8"))
    payload["items"][0]["notes"] = ""
    write(a_path, payload)
    result = validate(manifest, {"A": a_path})
    assert result["passed"] is False
    assert any("notes must not be blank" in error for error in result["errors"])

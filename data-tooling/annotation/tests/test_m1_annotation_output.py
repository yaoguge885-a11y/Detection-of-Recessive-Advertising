from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "m1_annotation_output.py"
SPEC = importlib.util.spec_from_file_location("m1_annotation_output", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_stream(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n\n".join(json.dumps(row, ensure_ascii=False, indent=2) for row in rows), encoding="utf-8")
    return path


def inputs(tmp_path: Path) -> tuple[Path, Path, list[dict]]:
    batch = write_stream(tmp_path / "batch.jsonl", [{"post_id": "p1"}, {"post_id": "p2"}])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"status": "locked", "post_ids": ["p1", "p2"]}), encoding="utf-8")
    annotations = [
        {
            "post_id": post_id,
            "annotator_id": "B",
            "annotation_method": "human",
            "label": "非广",
            "confidence": 0.8,
        }
        for post_id in ("p1", "p2")
    ]
    return batch, manifest, annotations


def validate(tmp_path: Path, rows: list[dict], allow_partial: bool = False) -> dict:
    batch, manifest, _ = inputs(tmp_path)
    annotation = write_stream(tmp_path / "B.json", rows)
    return MODULE.validate_annotation(
        batch_path=batch,
        manifest_path=manifest,
        annotation_path=annotation,
        annotator_id="B",
        expected_count=2,
        allow_partial=allow_partial,
        require_locked=True,
        mode="human_only",
    )


def test_complete_human_stream_passes(tmp_path: Path) -> None:
    _, _, rows = inputs(tmp_path)
    result = validate(tmp_path, rows)
    assert result["passed"] is True
    assert result["remaining_count"] == 0


def test_partial_must_be_prefix(tmp_path: Path) -> None:
    _, _, rows = inputs(tmp_path)
    assert validate(tmp_path, rows[:1], allow_partial=True)["passed"] is True
    result = validate(tmp_path, rows[1:], allow_partial=True)
    assert result["passed"] is False
    assert any("exact prefix" in error for error in result["errors"])


def test_auto_accepted_is_rejected(tmp_path: Path) -> None:
    _, _, rows = inputs(tmp_path)
    rows[0]["annotation_method"] = "auto_accepted"
    result = validate(tmp_path, rows)
    assert result["passed"] is False
    assert any("annotation_method" in error for error in result["errors"])

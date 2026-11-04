from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "m1_gold_metadata.py"
SPEC = importlib.util.spec_from_file_location("m1_gold_metadata", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return path


def test_attach_metadata_passes(tmp_path: Path) -> None:
    gold = write_jsonl(tmp_path / "gold.jsonl", [{"post_id": "p1", "label": "明广"}])
    canonical = write_jsonl(
        tmp_path / "canonical.jsonl",
        [{"post_id": "p1", "blogger_id": "b1", "content_group_id": "g1"}],
    )
    rows, report = MODULE.attach_metadata(gold_path=gold, canonical_path=canonical, minimum_count=1)
    assert report["passed"] is True
    assert rows[0]["blogger_id"] == "b1"
    assert rows[0]["content_group_id"] == "g1"


def test_missing_blogger_is_rejected(tmp_path: Path) -> None:
    gold = write_jsonl(tmp_path / "gold.jsonl", [{"post_id": "p1", "label": "非广"}])
    canonical = write_jsonl(tmp_path / "canonical.jsonl", [{"post_id": "p1", "blogger_id": ""}])
    _, report = MODULE.attach_metadata(gold_path=gold, canonical_path=canonical, minimum_count=1)
    assert report["passed"] is False
    assert any("blogger_id" in error for error in report["errors"])

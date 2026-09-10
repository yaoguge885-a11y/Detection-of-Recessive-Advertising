from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "m1_downstream_readiness.py"
SPEC = importlib.util.spec_from_file_location("m1_downstream_readiness", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_empty_repo_is_blocked_without_mutation(tmp_path: Path) -> None:
    before = set(tmp_path.rglob("*"))
    report = MODULE.evaluate(tmp_path)
    after = set(tmp_path.rglob("*"))
    assert report["all_downstream_stages_ready"] is False
    assert report["first_blocked_stage"] == "stage5_lock_batches"
    assert before == after


def test_current_formal_v2_paths_close_stage3_gate(tmp_path: Path) -> None:
    formal_root = tmp_path / "data" / "reports" / "m1" / "privacy" / "formal_3312_v2"
    formal_root.mkdir(parents=True)
    candidates = formal_root / "formal_eligible_candidates.jsonl"
    candidates.write_text(
        "".join(json.dumps({"post_id": f"p{i}"}) + "\n" for i in range(2050)),
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidates.read_bytes()).hexdigest()
    (formal_root / "formalization_report.json").write_text(
        json.dumps(
            {
                "status": "formal_materialized",
                "formal_candidates": {
                    "sha256": digest,
                    "record_count": 2050,
                },
            }
        ),
        encoding="utf-8",
    )

    report = MODULE.evaluate(tmp_path)
    blockers = report["stages"]["stage5_lock_batches"]["blockers"]
    assert blockers == ["missing/invalid A/B calibration summary"]
    assert report["stages"]["stage5_lock_batches"]["evidence"]["formal_candidate_count"] == 2050

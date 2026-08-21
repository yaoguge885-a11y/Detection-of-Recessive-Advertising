from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "m1_privacy_cohort.py"
SPEC = importlib.util.spec_from_file_location("m1_privacy_cohort", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def cohort_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        "\n".join(json.dumps({"post_id": pid}) for pid in ("p1", "p2", "p3"))
        + "\n",
        encoding="utf-8",
    )
    approval = tmp_path / "approval.json"
    write_json(
        approval,
        {
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "post_ids": ["p1", "p2"],
            "excluded": [{"post_id": "p3", "reason": "risk"}],
        },
    )
    allowlist = tmp_path / "allowlist.json"
    write_json(allowlist, {"total_approved": 2, "post_ids": ["p1", "p2"]})
    return dataset, approval, allowlist


def test_partition_and_hash_ready(tmp_path: Path) -> None:
    dataset, approval, allowlist = cohort_fixture(tmp_path)
    report = MODULE.audit_cohort(
        dataset_path=dataset, approval_path=approval, allowlist_path=allowlist
    )
    assert report["partition_passed"] is True
    assert report["formal_materialization_ready"] is True


def test_hash_mismatch_is_warning_but_blocks_formalization(tmp_path: Path) -> None:
    dataset, approval, allowlist = cohort_fixture(tmp_path)
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["dataset_sha256"] = "0" * 64
    write_json(approval, payload)
    report = MODULE.audit_cohort(
        dataset_path=dataset, approval_path=approval, allowlist_path=allowlist
    )
    assert report["partition_passed"] is True
    assert report["formal_materialization_ready"] is False
    assert report["warnings"]


def test_partition_gap_fails(tmp_path: Path) -> None:
    dataset, approval, allowlist = cohort_fixture(tmp_path)
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["excluded"] = []
    write_json(approval, payload)
    report = MODULE.audit_cohort(
        dataset_path=dataset, approval_path=approval, allowlist_path=allowlist
    )
    assert report["partition_passed"] is False
    assert any("partition misses" in error for error in report["errors"])


def test_materialize_requires_completed_spotcheck(tmp_path: Path) -> None:
    dataset, approval, allowlist = cohort_fixture(tmp_path)
    validation = tmp_path / "spotcheck_validation.json"
    write_json(validation, {"passed": False})
    try:
        MODULE.materialize(
            dataset_path=dataset,
            approval_path=approval,
            allowlist_path=allowlist,
            spotcheck_validation_path=validation,
            output_dir=tmp_path / "formal",
            preview=False,
            audit_options={},
        )
    except ValueError as exc:
        assert "spotcheck validation has not passed" in str(exc)
    else:
        raise AssertionError("formal materialization should have been refused")


def test_preview_is_marked_non_formal(tmp_path: Path) -> None:
    dataset, approval, allowlist = cohort_fixture(tmp_path)
    validation = tmp_path / "spotcheck_validation.json"
    write_json(validation, {"passed": False})
    report = MODULE.materialize(
        dataset_path=dataset,
        approval_path=approval,
        allowlist_path=allowlist,
        spotcheck_validation_path=validation,
        output_dir=tmp_path / "preview",
        preview=True,
        audit_options={},
    )
    assert report["status"] == "preview_not_formal"
    assert report["spotcheck_validation_passed"] is False
    assert report["candidate_count"] == 2

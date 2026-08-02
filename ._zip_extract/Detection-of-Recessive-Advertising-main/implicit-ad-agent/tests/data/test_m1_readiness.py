from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "data-tooling" / "m1_readiness.py"
MIRROR_PATH = REPO_ROOT / "implicit-ad-agent" / "scripts" / "data" / "m1_readiness.py"


def load_readiness_module() -> ModuleType:
    if not MODULE_PATH.exists():
        pytest.fail(f"M1 readiness module is missing: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("m1_readiness_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json_stream(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def complete_evidence() -> dict[str, object]:
    return {
        "candidate_unique_count": 3000,
        "gold_count": 1500,
        "guide_edge_case_count": 20,
        "second_round_kappa": 0.6,
        "second_round_formal": True,
        "creator_leakage_count": 0,
        "near_duplicate_leakage_count": 0,
        "privacy_approved": True,
        "terms_complete": True,
        "dataset_card_complete": True,
    }


def test_load_json_stream_rejects_corrupt_trailing_object(tmp_path: Path) -> None:
    readiness = load_readiness_module()
    path = tmp_path / "records.jsonl"
    path.write_text('{"post_id":"p1"}\n{"post_id":', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        readiness.load_json_stream(path)


def test_load_json_stream_rejects_non_object_record(tmp_path: Path) -> None:
    readiness = load_readiness_module()
    path = tmp_path / "records.jsonl"
    path.write_text('{"post_id":"p1"}\n[1,2,3]\n', encoding="utf-8")

    with pytest.raises(TypeError, match="record 1 must be an object"):
        readiness.load_json_stream(path)


def test_audit_counts_unique_posts_and_suppresses_identifiers(tmp_path: Path) -> None:
    readiness = load_readiness_module()
    posts = [
        {
            "post_id": "private_post_1",
            "blogger_id": "private_blogger_1",
            "platform": "wechat_official_account",
            "media": [],
        },
        {
            "post_id": "private_post_1",
            "blogger_id": "private_blogger_1",
            "platform": "wechat_official_account",
            "media": [],
        },
        {
            "post_id": "private_post_2",
            "blogger_id": "private_blogger_2",
            "platform": "xiaohongshu",
            "media": [],
        },
    ]
    write_json_stream(tmp_path / "anonymized_postsn.jsonl", posts)
    (tmp_path / "annotations").mkdir()

    report = readiness.audit_dataset(tmp_path)

    assert report["candidates"] == {
        "rows": 3,
        "unique_posts": 2,
        "duplicate_post_rows": 1,
        "unique_creators": 2,
        "platform_counts": {
            "wechat_official_account": 2,
            "xiaohongshu": 1,
        },
    }
    serialized = json.dumps(report, ensure_ascii=False)
    assert "private_post_1" not in serialized
    assert "private_blogger_1" not in serialized
    assert str(tmp_path) not in serialized


def test_audit_reports_annotation_overlap_without_annotator_ids(tmp_path: Path) -> None:
    readiness = load_readiness_module()
    write_json_stream(
        tmp_path / "anonymized_postsn.jsonl",
        [
            {
                "post_id": "p1",
                "blogger_id": "b1",
                "platform": "wechat_official_account",
                "media": [],
            },
            {
                "post_id": "p2",
                "blogger_id": "b1",
                "platform": "wechat_official_account",
                "media": [],
            },
        ],
    )
    write_json_stream(
        tmp_path / "annotations" / "a.json",
        [
            {"post_id": "p1", "annotator_id": "secret_a", "label": "明广"},
            {"post_id": "p2", "annotator_id": "secret_a", "label": "uncertain"},
        ],
    )
    write_json_stream(
        tmp_path / "annotations" / "b.json",
        [
            {"post_id": "p1", "annotator_id": "secret_b", "label": "明广"},
            {"post_id": "p2", "text": "raw candidate, not an annotation"},
        ],
    )

    report = readiness.audit_dataset(tmp_path)

    assert report["annotations"]["file_count"] == 2
    assert report["annotations"]["rows_per_file"] == [2, 1]
    assert report["annotations"]["unique_posts_per_file"] == [2, 1]
    assert report["annotations"]["common_posts"] == 1
    assert "secret_a" not in json.dumps(report, ensure_ascii=False)


def test_gate_fails_missing_and_insufficient_evidence() -> None:
    readiness = load_readiness_module()
    result = readiness.evaluate_m1_gate(
        {
            "candidate_unique_count": 282,
            "gold_count": 36,
            "guide_edge_case_count": 24,
            "second_round_kappa": 1.0,
            "second_round_formal": False,
            "creator_leakage_count": None,
            "near_duplicate_leakage_count": None,
            "privacy_approved": False,
            "terms_complete": False,
            "dataset_card_complete": False,
        }
    )

    assert result["passed"] is False
    assert result["checks"]["candidate_pool"]["status"] == "failed"
    assert result["checks"]["gold"]["status"] == "failed"
    assert result["checks"]["annotation_guide"]["status"] == "passed"
    assert result["checks"]["split_leakage"]["status"] == "missing"
    assert result["checks"]["compliance"]["status"] == "review_required"


def test_gate_passes_only_complete_evidence_fixture() -> None:
    readiness = load_readiness_module()
    result = readiness.evaluate_m1_gate(complete_evidence())

    assert result["passed"] is True
    assert all(check["status"] == "passed" for check in result["checks"].values())


def test_gate_rejects_kappa_that_is_only_pilot_evidence() -> None:
    readiness = load_readiness_module()
    evidence = complete_evidence()
    evidence["second_round_formal"] = False
    result = readiness.evaluate_m1_gate(evidence)

    assert result["passed"] is False
    assert result["checks"]["agreement"]["status"] == "review_required"


def test_count_guide_edge_cases_counts_unique_ids(tmp_path: Path) -> None:
    readiness = load_readiness_module()
    guide = tmp_path / "guide.md"
    guide.write_text(
        "### EC-01 first\n\n### EC-01 duplicate\n\n### EC-02 second\n",
        encoding="utf-8",
    )

    assert readiness.count_guide_edge_cases(guide) == 2


def test_runtime_mirror_matches_data_tooling_entrypoint() -> None:
    assert MIRROR_PATH.exists(), f"runtime mirror is missing: {MIRROR_PATH}"
    assert MIRROR_PATH.read_bytes() == MODULE_PATH.read_bytes()

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.data.annotation import build_gold_dataset
from scripts.data.annotation import calculate_agreement
from scripts.data.annotation import lock_annotation_batch
from scripts.data.annotation import privacy_scan
from scripts.data.annotation import split_by_blogger
from scripts.data.annotation import validate_schema


AGENT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = AGENT_ROOT.parent
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "data_schema_v1.json"
SYNTHETIC_PATH = REPO_ROOT / "data" / "synthetic" / "simulated_posts_v1.json"


@pytest.fixture
def schema_v1() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def valid_v1_record() -> dict:
    dataset = json.loads(SYNTHETIC_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(dataset["content_records"][0])


def test_validate_record_rejects_additional_property(
    valid_v1_record: dict, schema_v1: dict
) -> None:
    valid_v1_record["_migration_meta"] = {}

    errors = validate_schema.validate_record(valid_v1_record, schema_v1)

    assert any(error.startswith("additionalProperties:") for error in errors)


def test_validate_record_rejects_bad_datetime(
    valid_v1_record: dict, schema_v1: dict
) -> None:
    valid_v1_record["provenance"]["collected_at"] = "not-a-date"

    errors = validate_schema.validate_record(valid_v1_record, schema_v1)

    assert any(error.startswith("format:") for error in errors)


def test_validate_record_accepts_nullable_formatted_fields(
    valid_v1_record: dict, schema_v1: dict
) -> None:
    valid_v1_record["published_at"] = None
    valid_v1_record["provenance"]["terms_checked_at"] = None

    errors = validate_schema.validate_record(valid_v1_record, schema_v1)

    assert not any(error.startswith("format:") for error in errors)


def test_validate_record_rejects_nested_missing_media_ref(
    valid_v1_record: dict, schema_v1: dict
) -> None:
    del valid_v1_record["media"][0]["ref"]

    errors = validate_schema.validate_record(valid_v1_record, schema_v1)

    assert any("required:" in error and "media/0" in error for error in errors)


def test_validate_json_stream_rejects_corrupt_trailing_object(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"post_id":"p1"}\n{"post_id":', encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        list(validate_schema.load_jsonl(path))


def test_schema_cli_writes_aggregate_report_and_returns_nonzero_for_invalid(
    tmp_path: Path, valid_v1_record: dict
) -> None:
    valid_v1_record["_migration_meta"] = {}
    input_path = tmp_path / "invalid.jsonl"
    report_path = tmp_path / "schema_report.json"
    input_path.write_text(
        json.dumps(valid_v1_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path(validate_schema.__file__)),
            str(input_path),
            "--target-schema",
            "1.0",
            "--schema",
            str(SCHEMA_PATH),
            "--report",
            str(report_path),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2, (result.stdout + result.stderr).decode(
        errors="replace"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total_records"] == 1
    assert report["invalid_records"] == 1
    assert report["validator_counts"]["additionalProperties"] == 1
    assert "text" not in report


def test_schema_main_writes_relative_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    valid_v1_record: dict,
) -> None:
    input_path = tmp_path / "valid.jsonl"
    input_path.write_text(
        json.dumps(valid_v1_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(validate_schema, "_repository_root", lambda: tmp_path)

    exit_code = validate_schema.main(
        str(input_path),
        schema_path=str(SCHEMA_PATH),
        report_path="reports/schema.json",
    )

    assert exit_code == 0
    report = json.loads(
        (tmp_path / "reports" / "schema.json").read_text(encoding="utf-8")
    )
    assert report["valid_records"] == 1


def test_privacy_classification_defaults_to_interim_without_human_approval(
    valid_v1_record: dict,
) -> None:
    assert privacy_scan.classify_record(valid_v1_record, []) == "interim"


def test_privacy_classification_requires_approval_terms_and_safe_flags(
    valid_v1_record: dict,
) -> None:
    approved = {valid_v1_record["post_id"]}

    assert privacy_scan.classify_record(valid_v1_record, [], approved) == "public"

    valid_v1_record["provenance"]["terms_checked_at"] = None
    assert privacy_scan.classify_record(valid_v1_record, [], approved) == "interim"


def test_privacy_classification_keeps_sensitive_record_interim_when_approved(
    valid_v1_record: dict,
) -> None:
    valid_v1_record["privacy"]["contains_sensitive_data"] = True

    assert (
        privacy_scan.classify_record(
            valid_v1_record,
            [],
            {valid_v1_record["post_id"]},
        )
        == "interim"
    )


def test_privacy_classification_keeps_critical_finding_raw(
    valid_v1_record: dict,
) -> None:
    findings = [
        {
            "field": "text",
            "type": "身份证号",
            "match": "110101199001011234",
            "severity": "critical",
        }
    ]

    assert (
        privacy_scan.classify_record(
            valid_v1_record,
            findings,
            {valid_v1_record["post_id"]},
        )
        == "raw"
    )


def test_privacy_classification_allows_approved_record_with_low_finding(
    valid_v1_record: dict,
) -> None:
    findings = [
        {
            "field": "text",
            "type": "高熵文本（疑似编码/加密内容）",
            "match": "entropy=5.60, length=120",
            "severity": "low",
        }
    ]

    assert (
        privacy_scan.classify_record(
            valid_v1_record,
            findings,
            {valid_v1_record["post_id"]},
        )
        == "public"
    )


def test_privacy_scan_ignores_normalized_opaque_media_reference(
    valid_v1_record: dict,
) -> None:
    valid_v1_record["media"] = [
        {"ref": "media/post_0123456789abcdef/00.webp"},
        {"ref": "media/a844971983d0bf7fcfb4e3bf/01.jpg"},
        {"ref": "media/a844971983d0bf7fcfb4e3bf/100.jpg"},
    ]

    assert privacy_scan.scan_record(valid_v1_record) == []


def test_privacy_scan_still_checks_noncanonical_media_reference(
    valid_v1_record: dict,
) -> None:
    valid_v1_record["media"] = [
        {"ref": "media/uploads/contact_test@example.com.png"}
    ]

    findings = privacy_scan.scan_record(valid_v1_record)

    assert any(finding["type"] == "邮箱地址" for finding in findings)


def test_redact_finding_removes_cleartext_match() -> None:
    finding = {
        "field": "text",
        "type": "API 密钥模式",
        "match": "sk-a-secret-that-must-not-leak",
        "severity": "high",
    }

    redacted = privacy_scan.redact_finding(finding)

    assert "match" not in redacted
    assert redacted["match_length"] == len(finding["match"])
    assert redacted["match_hash"] == privacy_scan.hashlib.sha256(
        finding["match"].encode("utf-8")
    ).hexdigest()
    assert finding["match"] not in json.dumps(redacted, ensure_ascii=False)


def test_public_allowlist_contains_only_explicitly_approved_safe_ids(
    valid_v1_record: dict,
) -> None:
    second = copy.deepcopy(valid_v1_record)
    second["post_id"] = "not-approved"
    records = [valid_v1_record, second]
    findings_map = {record["post_id"]: [] for record in records}

    allowlist = privacy_scan.generate_public_allowlist(
        records,
        findings_map,
        {valid_v1_record["post_id"]},
    )

    assert allowlist == [valid_v1_record["post_id"]]


@pytest.mark.parametrize(
    "script_name",
    ["calculate_agreement.py", "build_gold_dataset.py"],
)
def test_annotation_governance_script_mirrors_match(script_name: str) -> None:
    canonical = REPO_ROOT / "data-tooling" / "annotation" / script_name
    runtime = AGENT_ROOT / "scripts" / "data" / "annotation" / script_name

    assert runtime.read_bytes() == canonical.read_bytes()


def test_agreement_excludes_special_and_unknown_labels() -> None:
    report = calculate_agreement.calculate_agreement(
        {
            "p1": {"label": "明广", "annotator_id": "a", "annotation_method": "human"},
            "p2": {"label": "uncertain", "annotator_id": "a", "annotation_method": "human"},
            "p3": {"label": "bad", "annotator_id": "a", "annotation_method": "human"},
        },
        {
            "p1": {"label": "明广", "annotator_id": "b", "annotation_method": "human"},
            "p2": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
            "p3": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
        },
    )

    assert report["valid_pair_count"] == 1
    assert report["kappa"] == 1.0
    assert report["excluded_pair_count"] == 2


def test_agreement_loader_rejects_corrupt_trailing_object(tmp_path: Path) -> None:
    path = tmp_path / "annotations.jsonl"
    path.write_text(
        '{"post_id":"p1","label":"明广"}\n{"post_id":',
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        calculate_agreement.load_annotations(path)


def test_agreement_loader_skips_non_annotation_objects(tmp_path: Path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text(
        '{"post_id":"raw-only","text":"candidate"}\n'
        '{"post_id":"p1","label":"明广"}\n',
        encoding="utf-8",
    )

    annotations = calculate_agreement.load_annotations(path)

    assert annotations == {"p1": {"post_id": "p1", "label": "明广"}}


def test_agreement_excludes_automated_or_non_independent_pairs() -> None:
    report = calculate_agreement.calculate_agreement(
        {
            "auto": {
                "label": "明广",
                "annotator_id": "system",
                "annotation_method": "auto_accepted",
            },
            "same": {
                "label": "非广",
                "annotator_id": "annotator-a",
                "annotation_method": "human",
            },
            "missing_method": {
                "label": "明广",
                "annotator_id": "annotator-a",
            },
            "missing_id": {
                "label": "非广",
                "annotation_method": "human",
            },
            "whitespace_id": {
                "label": "明广",
                "annotator_id": "   ",
                "annotation_method": "human",
            },
            "normalized_same": {
                "label": "非广",
                "annotator_id": "annotator-a",
                "annotation_method": "human",
            },
            "system_space": {
                "label": "明广",
                "annotator_id": "system ",
                "annotation_method": "human",
            },
        },
        {
            "auto": {
                "label": "明广",
                "annotator_id": "system",
                "annotation_method": "auto_accepted",
            },
            "same": {
                "label": "非广",
                "annotator_id": "annotator-a",
                "annotation_method": "human",
            },
            "missing_method": {
                "label": "明广",
                "annotator_id": "annotator-b",
            },
            "missing_id": {
                "label": "非广",
                "annotator_id": "annotator-b",
                "annotation_method": "human",
            },
            "whitespace_id": {
                "label": "明广",
                "annotator_id": "annotator-b",
                "annotation_method": "human",
            },
            "normalized_same": {
                "label": "非广",
                "annotator_id": " annotator-a ",
                "annotation_method": "human",
            },
            "system_space": {
                "label": "明广",
                "annotator_id": "annotator-b",
                "annotation_method": "human",
            },
        },
        formal_second_round=True,
    )

    assert report["valid_pair_count"] == 0
    assert report["ineligible_pair_count"] == 7
    assert report["excluded_reason_counts"] == {
        "automated_annotation": 2,
        "missing_annotator_id": 2,
        "non_human_method": 1,
        "same_annotator": 2,
    }
    assert report["kappa"] is None
    assert report["formal_second_round"] is False
    assert report["formal_second_round_requested"] is True


def test_agreement_keeps_formal_flag_for_distinct_human_annotators() -> None:
    report = calculate_agreement.calculate_agreement(
        {
            "p1": {
                "label": "明广",
                "annotator_id": "annotator-a",
                "annotation_method": "human",
            },
        },
        {
            "p1": {
                "label": "明广",
                "annotator_id": "annotator-b",
                "annotation_method": "human",
            },
        },
        formal_second_round=True,
    )

    assert report["valid_pair_count"] == 1
    assert report["kappa"] == 1.0
    assert report["formal_second_round"] is True


def test_agreement_cli_has_one_entrypoint_and_writes_json(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    output = tmp_path / "agreement.json"
    record = json.dumps(
        {
            "post_id": "p1",
            "label": "明广",
            "annotator_id": "annotator-a",
            "annotation_method": "human",
        },
        ensure_ascii=False,
    )
    second_record = json.dumps(
        {
            "post_id": "p1",
            "label": "明广",
            "annotator_id": "annotator-b",
            "annotation_method": "human",
        },
        ensure_ascii=False,
    )
    path_a.write_text(record + "\n", encoding="utf-8")
    path_b.write_text(second_record + "\n", encoding="utf-8")
    script = REPO_ROOT / "data-tooling" / "annotation" / "calculate_agreement.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(path_a),
            str(path_b),
            "--output",
            str(output),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (result.stdout + result.stderr).decode(
        errors="replace"
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["valid_pair_count"] == 1
    assert report["formal_second_round"] is False


def test_shared_content_group_connects_entire_creators() -> None:
    records = [
        {"post_id": "a1", "blogger_id": "a", "content_group_id": None},
        {"post_id": "a2", "blogger_id": "a", "content_group_id": "g"},
        {"post_id": "b1", "blogger_id": "b", "content_group_id": "g"},
        {"post_id": "b2", "blogger_id": "b", "content_group_id": None},
    ]

    groups = split_by_blogger.build_split_groups(records)

    assert len(groups) == 1
    assert sorted(next(iter(groups.values()))) == ["a1", "a2", "b1", "b2"]


def test_split_leakage_validator_counts_creator_and_content_group_overlap() -> None:
    records = [
        {"post_id": "a1", "blogger_id": "a", "content_group_id": "g1"},
        {"post_id": "a2", "blogger_id": "a", "content_group_id": None},
        {"post_id": "b1", "blogger_id": "b", "content_group_id": "g1"},
    ]
    assignments = {
        "train": ["a1"],
        "dev": ["a2"],
        "test": ["a1", "b1"],
    }

    leakage = split_by_blogger.validate_split_leakage(records, assignments)

    assert leakage["post_leakage_count"] == 1
    assert leakage["creator_leakage_count"] == 1
    assert leakage["near_duplicate_leakage_count"] == 1


def test_gold_merge_enforces_agreement_adjudication_and_exclusions() -> None:
    ann_a = {
        "agreed": {"label": "明广", "annotator_id": "a", "annotation_method": "human"},
        "disputed": {"label": "明广", "annotator_id": "a", "annotation_method": "human"},
        "adjudicated": {"label": "暗广", "annotator_id": "a", "annotation_method": "human"},
        "uncertain": {"label": "uncertain", "annotator_id": "a", "annotation_method": "human"},
        "out": {"label": "out_of_scope", "annotator_id": "a", "annotation_method": "human"},
        "missing": {"label": "非广", "annotator_id": "a", "annotation_method": "human"},
    }
    ann_b = {
        "agreed": {"label": "明广", "annotator_id": "b", "annotation_method": "human"},
        "disputed": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
        "adjudicated": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
        "uncertain": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
        "out": {"label": "非广", "annotator_id": "b", "annotation_method": "human"},
    }
    adjudication = {
        "adjudicated": {
            "label": "暗广",
            "arbiter": "reviewer",
            "conflict_reason": "evidence review",
        }
    }

    gold, excluded = build_gold_dataset.merge_annotations(
        ann_a,
        ann_b,
        adjudication,
    )

    assert [(record["post_id"], record["label"]) for record in gold] == [
        ("adjudicated", "暗广"),
        ("agreed", "明广"),
    ]
    reasons = {record["post_id"]: record["reason"] for record in excluded}
    assert reasons["disputed"] == "disagreement_not_adjudicated"
    assert reasons["missing"] == "missing_one_annotator"
    assert reasons["uncertain"] == "uncertain_or_out_of_scope"
    assert reasons["out"] == "uncertain_or_out_of_scope"


def test_gold_excludes_automated_and_same_annotator_records() -> None:
    ann_a = {
        "auto": {
            "label": "明广",
            "annotator_id": "system",
            "annotation_method": "auto_accepted",
        },
        "same": {
            "label": "非广",
            "annotator_id": "annotator-a",
            "annotation_method": "human",
        },
        "missing_method": {
            "label": "明广",
            "annotator_id": "annotator-a",
        },
        "missing_id": {
            "label": "非广",
            "annotation_method": "human",
        },
        "whitespace_id": {
            "label": "明广",
            "annotator_id": "   ",
            "annotation_method": "human",
        },
        "normalized_same": {
            "label": "非广",
            "annotator_id": "annotator-a",
            "annotation_method": "human",
        },
        "system_space": {
            "label": "明广",
            "annotator_id": "system ",
            "annotation_method": "human",
        },
    }
    ann_b = {
        "auto": {
            "label": "明广",
            "annotator_id": "system",
            "annotation_method": "auto_accepted",
        },
        "same": {
            "label": "非广",
            "annotator_id": "annotator-a",
            "annotation_method": "human",
        },
        "missing_method": {
            "label": "明广",
            "annotator_id": "annotator-b",
        },
        "missing_id": {
            "label": "非广",
            "annotator_id": "annotator-b",
            "annotation_method": "human",
        },
        "whitespace_id": {
            "label": "明广",
            "annotator_id": "annotator-b",
            "annotation_method": "human",
        },
        "normalized_same": {
            "label": "非广",
            "annotator_id": " annotator-a ",
            "annotation_method": "human",
        },
        "system_space": {
            "label": "明广",
            "annotator_id": "annotator-b",
            "annotation_method": "human",
        },
    }

    gold, excluded = build_gold_dataset.merge_annotations(ann_a, ann_b, {})

    assert gold == []
    assert {record["post_id"]: record["reason"] for record in excluded} == {
        "auto": "automated_annotation",
        "missing_id": "missing_annotator_id",
        "missing_method": "non_human_method",
        "normalized_same": "same_annotator",
        "same": "same_annotator",
        "system_space": "automated_annotation",
        "whitespace_id": "missing_annotator_id",
    }


def test_gold_cli_writes_safe_aggregate_report(tmp_path: Path) -> None:
    ann_a = tmp_path / "a.jsonl"
    ann_b = tmp_path / "b.jsonl"
    adjudication = tmp_path / "adjudication.jsonl"
    gold = tmp_path / "gold.jsonl"
    report = tmp_path / "gold_report.json"
    ann_a.write_text(
        json.dumps(
            {
                "post_id": "private-post-1",
                "annotator_id": "annotator-a",
                "annotation_method": "human",
                "label": "明广",
                "confidence": 0.9,
                "evidence": ["private evidence text"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    ann_b.write_text(
        json.dumps(
            {
                "post_id": "private-post-1",
                "annotator_id": "annotator-b",
                "annotation_method": "human",
                "label": "明广",
                "confidence": 0.9,
                "evidence": ["different private evidence text"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    adjudication.write_text("", encoding="utf-8")
    script = REPO_ROOT / "data-tooling" / "annotation" / "build_gold_dataset.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            str(ann_a),
            str(ann_b),
            str(adjudication),
            str(gold),
            "--report",
            str(report),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (result.stdout + result.stderr).decode(
        errors="replace"
    )
    assert len(gold.read_text(encoding="utf-8").splitlines()) == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload == {
        "gold_count": 1,
        "excluded_count": 0,
        "label_distribution": {"明广": 1},
        "adjudicated_count": 0,
        "low_confidence_count": 0,
    }
    report_text = report.read_text(encoding="utf-8")
    for forbidden in (
        "private-post-1",
        "annotator-a",
        "annotator-b",
        "private evidence text",
    ):
        assert forbidden not in report_text


def test_annotation_batch_lock_is_auditable_and_second_round_is_disjoint(
    tmp_path: Path,
) -> None:
    candidates = tmp_path / "candidates.jsonl"
    records = [
        {"post_id": "p1", "platform": "xiaohongshu", "blogger_id": "a", "media": [{"ref": "a.jpg"}]},
        {"post_id": "p2", "platform": "bilibili", "blogger_id": "b", "media": []},
        {"post_id": "p3", "platform": "xiaohongshu", "blogger_id": "c", "media": [{"ref": "c.jpg"}]},
        {"post_id": "p4", "platform": "bilibili", "blogger_id": "d", "media": []},
    ]
    candidates.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    guide = REPO_ROOT / "docs" / "annotation_guide_v1.md"
    first = lock_annotation_batch.build_manifest(
        candidates_path=candidates,
        guide_path=guide,
        batch_id="round1-20260728",
        count=2,
        seed=42,
        batch_kind="pilot",
        formal_second_round=False,
        required_platforms=("xiaohongshu", "bilibili"),
        required_media_states=("available", "missing"),
    )
    first_path = tmp_path / "round1_manifest.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second = lock_annotation_batch.build_manifest(
        candidates_path=candidates,
        guide_path=guide,
        batch_id="round2-20260728",
        count=2,
        seed=42,
        batch_kind="formal_kappa",
        formal_second_round=True,
        previous_manifest=first_path,
    )

    assert first["guide_version"] == "1.0"
    assert first["sample_count"] == 2
    assert first["creator_count"] == 2
    assert first["platform_counts"] == {"bilibili": 1, "xiaohongshu": 1}
    assert first["media_state_counts"] == {"available": 1, "missing": 1}
    assert first["input_sha256"] == lock_annotation_batch.sha256_file(candidates)
    assert first["sample_sha256"]
    assert second["formal_second_round"] is True
    assert second["overlap_with_previous_count"] == 0
    assert not (set(first["post_ids"]) & set(second["post_ids"]))


def test_annotation_batch_lock_requires_manual_boundary_anchors_to_be_eligible(
    tmp_path: Path,
) -> None:
    candidates = tmp_path / "candidates.jsonl"
    candidates.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in (
                {"post_id": "p1", "platform": "xiaohongshu", "blogger_id": "a", "media": []},
                {"post_id": "p2", "platform": "bilibili", "blogger_id": "b", "media": []},
                {"post_id": "p3", "platform": "xiaohongshu", "blogger_id": "c", "media": []},
            )
        ),
        encoding="utf-8",
    )
    guide = REPO_ROOT / "docs" / "annotation_guide_v1.md"

    manifest = lock_annotation_batch.build_manifest(
        candidates_path=candidates,
        guide_path=guide,
        batch_id="boundary-anchors-20260728",
        count=2,
        seed=42,
        batch_kind="pilot",
        formal_second_round=False,
        required_post_ids=("p2",),
    )

    assert "p2" in manifest["post_ids"]
    assert manifest["selection"]["manual_include_count"] == 1
    assert manifest["selection"]["manual_include_sha256"]
    with pytest.raises(ValueError, match="missing from eligible candidates"):
        lock_annotation_batch.build_manifest(
            candidates_path=candidates,
            guide_path=guide,
            batch_id="invalid-boundary-anchor-20260728",
            count=2,
            seed=42,
            batch_kind="pilot",
            formal_second_round=False,
            required_post_ids=("unknown",),
        )

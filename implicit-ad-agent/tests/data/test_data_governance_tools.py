from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.data.annotation import build_gold_dataset
from scripts.data.annotation import calculate_agreement
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


def test_agreement_excludes_special_and_unknown_labels() -> None:
    report = calculate_agreement.calculate_agreement(
        {"p1": "明广", "p2": "uncertain", "p3": "bad"},
        {"p1": "明广", "p2": "非广", "p3": "非广"},
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

    assert annotations == {"p1": "明广"}


def test_agreement_cli_has_one_entrypoint_and_writes_json(tmp_path: Path) -> None:
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    output = tmp_path / "agreement.json"
    record = json.dumps(
        {"post_id": "p1", "label": "明广"},
        ensure_ascii=False,
    )
    path_a.write_text(record + "\n", encoding="utf-8")
    path_b.write_text(record + "\n", encoding="utf-8")
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
        "agreed": {"label": "明广", "annotator_id": "a"},
        "disputed": {"label": "明广", "annotator_id": "a"},
        "adjudicated": {"label": "暗广", "annotator_id": "a"},
        "uncertain": {"label": "uncertain", "annotator_id": "a"},
        "out": {"label": "out_of_scope", "annotator_id": "a"},
        "missing": {"label": "非广", "annotator_id": "a"},
    }
    ann_b = {
        "agreed": {"label": "明广", "annotator_id": "b"},
        "disputed": {"label": "非广", "annotator_id": "b"},
        "adjudicated": {"label": "非广", "annotator_id": "b"},
        "uncertain": {"label": "非广", "annotator_id": "b"},
        "out": {"label": "非广", "annotator_id": "b"},
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

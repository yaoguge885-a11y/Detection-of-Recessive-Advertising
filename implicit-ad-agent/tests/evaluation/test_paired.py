from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from impad.evaluation.paired import PairingError, evaluate_paired


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "compare_agent_predictions.py"


def _rows(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [
        {"post_id": post_id, "label": gold, "predicted_label": predicted}
        for post_id, gold, predicted in items
    ]


def test_literal_metrics_and_transition_ids_are_label_only():
    before = _rows(
        ("a", "明广", "明广"),
        ("b", "暗广", "需复核"),
        ("c", "非广", "明广"),
        ("d", "非广", "需复核"),
        ("e", "暗广", "明广"),
    )
    after = _rows(
        ("a", "明广", "暗广"),
        ("b", "暗广", "暗广"),
        ("c", "非广", "暗广"),
        ("d", "非广", "非广"),
        ("e", "暗广", "暗广"),
    )

    report = evaluate_paired(list(reversed(before)), list(reversed(after)))

    assert report["before"]["n"] == 5
    assert report["before"]["correct"] == 1
    assert report["before"]["accuracy"] == pytest.approx(0.2)
    assert report["before"]["macro_f1"] == pytest.approx(1 / 6)
    assert report["before"]["dark_recall"] == 0
    assert report["before"]["overt_recall"] == 1
    assert report["before"]["normal_commercial_false_positive_count"] == 1
    assert report["before"]["normal_commercial_false_positive_rate"] == pytest.approx(0.5)
    assert report["before"]["review_count"] == 2
    assert report["before"]["review_rate"] == pytest.approx(0.4)

    assert report["after"]["correct"] == 3
    assert report["after"]["macro_f1"] == pytest.approx(4 / 9)
    assert report["after"]["dark_recall"] == 1
    assert report["after"]["overt_recall"] == 0
    assert report["after"]["review_count"] == 0
    assert report["overall"]["changed_ids"] == ["a", "b", "c", "d", "e"]
    assert report["overall"]["corrected"] == 3
    assert report["overall"]["corrected_ids"] == ["b", "d", "e"]
    assert report["overall"]["regressed"] == 1
    assert report["overall"]["regressed_ids"] == ["a"]
    assert report["overall"]["review_reduction"] == 2
    assert report["overall"]["review_reduced_ids"] == ["b", "d"]
    assert report["by_gold_label"]["暗广"]["corrected_ids"] == ["b", "e"]
    assert report["by_gold_label"]["明广"]["regressed_ids"] == ["a"]


def test_pairing_rejects_mismatched_ids_and_gold_conflicts():
    with pytest.raises(PairingError, match="cohort mismatch"):
        evaluate_paired(
            _rows(("a", "非广", "非广"), ("b", "非广", "非广")),
            _rows(("a", "非广", "非广")),
        )

    with pytest.raises(PairingError, match="gold label conflict"):
        evaluate_paired(
            _rows(("a", "非广", "非广")),
            _rows(("a", "暗广", "非广")),
        )

    with pytest.raises(PairingError, match="duplicate post_id"):
        evaluate_paired(
            _rows(("a", "非广", "非广"), ("a", "非广", "非广")),
            _rows(("a", "非广", "非广")),
        )


def test_expanded_rows_use_selected_arms_and_reject_mixed_rows():
    expanded = [
        {
            "post_id": "a",
            "gold_label": "暗广",
            "predictions": {"current": "需复核", "own_3": "暗广"},
        }
    ]
    report = evaluate_paired(
        expanded,
        expanded,
        before_arm="current",
        after_arm="own_3",
    )
    assert report["before"]["review_count"] == 1
    assert report["after"]["correct"] == 1

    mixed = [
        {"post_id": "a", "label": "非广", "predicted_label": "非广"},
        {
            "post_id": "b",
            "gold_label": "非广",
            "predictions": {"current": "非广"},
        },
    ]
    with pytest.raises(PairingError, match="mixed expanded/minimal"):
        evaluate_paired(mixed, mixed, before_arm="current", after_arm="current")


def test_cli_writes_report_for_minimal_jsonl(tmp_path):
    before_path = tmp_path / "before.jsonl"
    after_path = tmp_path / "after.jsonl"
    output_path = tmp_path / "nested" / "report.json"
    before = _rows(
        ("a", "明广", "明广"),
        ("b", "暗广", "需复核"),
        ("c", "非广", "明广"),
    )
    after = _rows(
        ("a", "明广", "明广"),
        ("b", "暗广", "暗广"),
        ("c", "非广", "非广"),
    )
    before_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in before),
        encoding="utf-8-sig",
    )
    after_path.write_text(
        json.dumps(after, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["before"]["correct"] == 1
    assert report["after"]["correct"] == 3
    assert report["overall"]["corrected_ids"] == ["b", "c"]
    assert report["source_hashes"]["before"]
    assert report["schema_manifest"]["before"]["schema"] == "minimal_rows"
    assert report["cohort_manifest"]["post_ids"] == ["a", "b", "c"]


def test_cli_refuses_mismatched_json_cohort_without_output(tmp_path):
    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    output_path = tmp_path / "report.json"
    before_path.write_text(
        json.dumps(_rows(("a", "非广", "非广"), ("b", "非广", "非广")), ensure_ascii=False),
        encoding="utf-8",
    )
    after_path.write_text(
        json.dumps(_rows(("a", "非广", "非广")), ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before_path),
            "--after",
            str(after_path),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode != 0
    assert "cohort mismatch" in completed.stderr
    assert not output_path.exists()

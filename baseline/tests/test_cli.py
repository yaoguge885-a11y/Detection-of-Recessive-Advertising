"""Subprocess-level tests for the isolated baseline command line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PYTHON = sys.executable


def _common_args(
    output: Path,
    *,
    gate: Path | None = None,
    content: Path | None = None,
    fixture_dir: Path | None = None,
) -> list[str]:
    source_dir = fixture_dir or FIXTURES
    return [
        "--content",
        str(content or (source_dir / "synthetic_content.jsonl")),
        "--gold",
        str(source_dir / "synthetic_gold.jsonl"),
        "--train-ids",
        str(source_dir / "train_ids.txt"),
        "--dev-ids",
        str(source_dir / "dev_ids.txt"),
        "--test-ids",
        str(source_dir / "test_ids.txt"),
        "--split-report",
        str(source_dir / "synthetic_split_report.json"),
        "--m1-gate",
        str(gate or (source_dir / "synthetic_gate.json")),
        "--output",
        str(output),
    ]


def _run_cli(
    mode: str,
    *,
    output: Path,
    gate: Path | None = None,
    fixture_dir: Path | None = None,
    evaluation_split: str | None = None,
    confirm_test_evaluation: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        PYTHON,
        "-m",
        "baseline.cli",
        mode,
        *_common_args(output, gate=gate, fixture_dir=fixture_dir),
    ]
    if mode == "synthetic":
        command.extend(
            ["--fixture-metadata", str(FIXTURES / "fixture_metadata.json")]
        )
    if evaluation_split is not None:
        command.extend(["--evaluation-split", evaluation_split])
    if confirm_test_evaluation:
        command.append("--confirm-test-evaluation")
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _formal_content_row(
    post_id: str,
    blogger_id: str,
    published_at: str,
    text: str,
    history_refs: list[str],
) -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "post_id": post_id,
        "platform": "synthetic",
        "source_type": "synthetic",
        "blogger_id": blogger_id,
        "published_at": published_at,
        "text": text,
        "media": [],
        "comments": [],
        "blogger_history_refs": history_refs,
        "content_group_id": None,
        "provenance": {
            "source_ref_hash": "formal-fixture",
            "collected_at": "2024-01-01T00:00:00+00:00",
            "collector": "fixture",
            "terms_checked_at": None,
        },
        "privacy": {"anonymized": True, "contains_sensitive_data": False},
    }


def _write_formal_fixture(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    labels = ("明广", "暗广", "非广")
    content_rows: list[dict[str, object]] = []
    gold_rows: list[dict[str, str]] = []
    split_ids: dict[str, list[str]] = {"train": [], "dev": [], "test": []}
    for split_index, split in enumerate(split_ids):
        for label_index, label in enumerate(labels):
            target_id = f"post_formal_{split}_{label_index}"
            blogger_id = f"blogger_formal_{split}_{label_index}"
            target_day = split_index * 10 + label_index + 4
            history_refs = [f"{target_id}_history_{i}" for i in range(1, 4)]
            content_rows.append(
                _formal_content_row(
                    target_id,
                    blogger_id,
                    f"2024-01-{target_day:02d}T12:00:00+00:00",
                    f"formal fixture {label}",
                    history_refs,
                )
            )
            for history_index, history_id in enumerate(history_refs, start=1):
                content_rows.append(
                    _formal_content_row(
                        history_id,
                        blogger_id,
                        f"2024-01-{target_day - history_index:02d}T12:00:00+00:00",
                        "formal fixture history",
                        [],
                    )
                )
            gold_rows.append({"post_id": target_id, "label": label})
            split_ids[split].append(target_id)

    (directory / "synthetic_content.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in content_rows
        ),
        encoding="utf-8",
    )
    (directory / "synthetic_gold.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in gold_rows
        ),
        encoding="utf-8",
    )
    for split, ids in split_ids.items():
        (directory / f"{split}_ids.txt").write_text(
            "\n".join(ids) + "\n", encoding="utf-8"
        )
    (directory / "synthetic_split_report.json").write_text(
        json.dumps(
            {
                "post_leakage_count": 0,
                "creator_leakage_count": 0,
                "content_group_leakage_count": 0,
                "near_duplicate_leakage_count": 0,
                "near_duplicate_check_status": "passed",
            }
        ),
        encoding="utf-8",
    )
    (directory / "synthetic_gate.json").write_text(
        json.dumps({"gate": "M1", "passed": True}), encoding="utf-8"
    )
    return directory


def test_synthetic_cli_runs_four_methods_and_marks_no_research_claim(tmp_path: Path):
    output = tmp_path / "report.json"
    completed = _run_cli("synthetic", output=output)

    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "synthetic"
    assert report["dataset_kind"] == "synthetic_fixture"
    assert report["research_claims_allowed"] is False
    assert tuple(report["methods"]) == (
        "single_post",
        "history_mean",
        "history_max",
        "history_ema",
    )
    serialized = output.read_text(encoding="utf-8")
    assert "新品推荐，优惠价格" not in serialized
    assert "fixture_creator_" not in serialized


def test_formal_cli_rejects_current_repository_gate_before_training(tmp_path: Path):
    output = tmp_path / "report.json"
    current_gate = ROOT / "data" / "reports" / "m1" / "m1_gate_report.json"
    completed = _run_cli("formal", output=output, gate=current_gate)

    assert completed.returncode == 2
    assert "M1 gate has not passed" in completed.stderr
    assert not output.exists()


def test_formal_test_evaluation_requires_confirmation(tmp_path: Path):
    output = tmp_path / "report.json"
    formal_fixture = _write_formal_fixture(tmp_path / "formal-fixture")
    blocked = _run_cli(
        "formal",
        output=output,
        fixture_dir=formal_fixture,
        evaluation_split="test",
        confirm_test_evaluation=False,
    )

    assert blocked.returncode == 2
    assert "test evaluation requires explicit confirmation" in blocked.stderr
    assert not output.exists()

    allowed = _run_cli(
        "formal",
        output=output,
        fixture_dir=formal_fixture,
        evaluation_split="test",
        confirm_test_evaluation=True,
    )
    assert allowed.returncode == 0, allowed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "formal"
    assert report["evaluation_split"] == "test"
    assert report["confirm_test_evaluation"] is True


def test_formal_test_guard_works_with_copied_fixture_inputs(tmp_path: Path):
    copied = _write_formal_fixture(tmp_path / "fixtures")

    output = tmp_path / "report.json"
    command = [
        PYTHON,
        "-m",
        "baseline.cli",
        "formal",
        "--content",
        str(copied / "synthetic_content.jsonl"),
        "--gold",
        str(copied / "synthetic_gold.jsonl"),
        "--train-ids",
        str(copied / "train_ids.txt"),
        "--dev-ids",
        str(copied / "dev_ids.txt"),
        "--test-ids",
        str(copied / "test_ids.txt"),
        "--split-report",
        str(copied / "synthetic_split_report.json"),
        "--m1-gate",
        str(copied / "synthetic_gate.json"),
        "--evaluation-split",
        "test",
        "--output",
        str(output),
    ]
    blocked = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert blocked.returncode == 2
    assert "test evaluation requires explicit confirmation" in blocked.stderr

    allowed = subprocess.run(
        [*command, "--confirm-test-evaluation"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert allowed.returncode == 0, allowed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["confirm_test_evaluation"] is True


def test_input_failure_does_not_create_or_overwrite_output(tmp_path: Path):
    output = tmp_path / "report.json"
    output.write_text("sentinel", encoding="utf-8")
    missing_content = tmp_path / "missing.jsonl"
    command = [
        PYTHON,
        "-m",
        "baseline.cli",
        "synthetic",
        *_common_args(output, content=missing_content),
        "--fixture-metadata",
        str(FIXTURES / "fixture_metadata.json"),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )

    assert completed.returncode == 2
    assert completed.stderr.startswith("baseline blocked: ")
    assert completed.stdout == ""
    assert output.read_text(encoding="utf-8") == "sentinel"

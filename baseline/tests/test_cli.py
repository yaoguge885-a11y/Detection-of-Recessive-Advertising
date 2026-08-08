"""Subprocess-level tests for the isolated baseline command line interface."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PYTHON = sys.executable


def _common_args(
    output: Path, *, gate: Path | None = None, content: Path | None = None
) -> list[str]:
    return [
        "--content",
        str(content or (FIXTURES / "synthetic_content.jsonl")),
        "--gold",
        str(FIXTURES / "synthetic_gold.jsonl"),
        "--train-ids",
        str(FIXTURES / "train_ids.txt"),
        "--dev-ids",
        str(FIXTURES / "dev_ids.txt"),
        "--test-ids",
        str(FIXTURES / "test_ids.txt"),
        "--split-report",
        str(FIXTURES / "synthetic_split_report.json"),
        "--m1-gate",
        str(gate or (FIXTURES / "synthetic_gate.json")),
        "--output",
        str(output),
    ]


def _run_cli(
    mode: str,
    *,
    output: Path,
    gate: Path | None = None,
    evaluation_split: str | None = None,
    confirm_test_evaluation: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [PYTHON, "-m", "baseline.cli", mode, *_common_args(output, gate=gate)]
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
    blocked = _run_cli(
        "formal",
        output=output,
        evaluation_split="test",
        confirm_test_evaluation=False,
    )

    assert blocked.returncode == 2
    assert "test evaluation requires explicit confirmation" in blocked.stderr
    assert not output.exists()

    allowed = _run_cli(
        "formal",
        output=output,
        evaluation_split="test",
        confirm_test_evaluation=True,
    )
    assert allowed.returncode == 0, allowed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "formal"
    assert report["evaluation_split"] == "test"
    assert report["confirm_test_evaluation"] is True


def test_formal_test_guard_works_with_copied_fixture_inputs(tmp_path: Path):
    copied = tmp_path / "fixtures"
    copied.mkdir()
    for source in FIXTURES.iterdir():
        shutil.copy2(source, copied / source.name)

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

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "evaluate_p4.py"
CREATOR_SHIFT_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "creator_shift_eval_v1.json"
)
CALIBRATION_FIXTURE = (
    PROJECT_ROOT / "tests" / "fixtures" / "calibration_eval_v1.json"
)


def test_creator_shift_cli_runs_from_an_unrelated_working_directory(
    tmp_path: Path,
):
    output = tmp_path / "reports" / "creator_shift.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "creator-shift",
            "--fixture",
            str(CREATOR_SHIFT_FIXTURE),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == "synthetic-creator-shift-v1"
    assert payload["methods"] == ["mean", "max", "ema"]
    assert payload["case_count"] == 4


def test_calibration_cli_writes_seeded_selective_report(tmp_path: Path):
    output = tmp_path / "reports" / "calibration.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "calibration",
            "--predictions",
            str(CALIBRATION_FIXTURE),
            "--output",
            str(output),
            "--bootstrap-resamples",
            "100",
            "--bootstrap-seed",
            "20260730",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["benchmark_version"] == "synthetic-calibration-v1"
    assert payload["bootstrap_resamples"] == 100
    assert payload["bootstrap_seed"] == 20260730
    assert payload["risk_coverage"][-1]["coverage"] == 1

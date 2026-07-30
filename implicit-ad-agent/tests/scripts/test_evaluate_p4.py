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

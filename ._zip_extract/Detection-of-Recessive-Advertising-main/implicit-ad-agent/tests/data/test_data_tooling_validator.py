from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_data_tooling_validator_resolves_repository_assets() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    validator = repo_root / "data-tooling" / "validate_submission_assets.py"

    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output.decode(errors="replace")
    assert b"VALIDATION PASSED" in result.stdout

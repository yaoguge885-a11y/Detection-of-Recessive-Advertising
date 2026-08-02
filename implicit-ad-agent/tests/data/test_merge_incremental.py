from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "merge_incremental.py"
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "data_schema_v1_2.json"
FIXTURE_PATH = REPO_ROOT / "data" / "synthetic" / "simulated_posts_v1.json"


def _v1_1_record() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    record = copy.deepcopy(payload["content_records"][0])
    record["schema_version"] = "1.1"
    return record


def _run_merge(tmp_path: Path, record: dict) -> tuple[subprocess.CompletedProcess, Path]:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "anonymized_posts.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--target",
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result, target / "anonymized_posts.jsonl"


def test_incremental_merge_upgrades_v1_1_to_schema_valid_v1_2(tmp_path: Path) -> None:
    result, output = _run_merge(tmp_path, _v1_1_record())

    assert result.returncode == 0, result.stdout + result.stderr
    merged = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(merged)
    assert merged["schema_version"] == "1.2"
    assert "is_content" not in merged["media"][0]
    assert "llm_summary" not in merged["provenance"]
    assert "llm_extracted_at" not in merged["provenance"]


def test_incremental_merge_rejects_invalid_record_before_writing(tmp_path: Path) -> None:
    record = _v1_1_record()
    record["unexpected"] = "not allowed"

    result, output = _run_merge(tmp_path, record)

    assert result.returncode != 0
    assert not output.exists()

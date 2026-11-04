import json
from pathlib import Path
import subprocess
import sys

import pytest

from impad.security.artifact_scan import scan_artifacts


def test_scanner_reports_only_hash_length_rule_and_location(tmp_path):
    secret = "scanner-secret-123"
    artifact = tmp_path / "unsafe.json"
    artifact.write_text(
        json.dumps({"authorization": f"Bearer {secret}"}),
        encoding="utf-8",
    )

    findings = scan_artifacts([artifact])
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in findings]
    )

    assert len(findings) == 1
    assert findings[0].path == str(artifact)
    assert findings[0].rule_id == "authorization_value"
    assert findings[0].line_number == 1
    assert findings[0].match_length > 0
    assert len(findings[0].match_hash) == 64
    assert secret not in serialized
    assert not hasattr(findings[0], "match")


def test_scanner_accepts_sanitized_json_markdown_and_log_files(tmp_path):
    for name in ("run.json", "report.md", "service.log"):
        (tmp_path / name).write_text(
            "https://example.test/post [REDACTED]",
            encoding="utf-8",
        )

    assert scan_artifacts([tmp_path]) == []


@pytest.mark.parametrize(
    "name,content,expected_rule",
    [
        ("cookie.log", "Cookie: sid=cookie-value", "cookie_value"),
        (
            "set-cookie.log",
            "Set-Cookie: sid=set-cookie-value; HttpOnly",
            "set_cookie_value",
        ),
        (
            "bearer.jsonl",
            '{"authorization":"Bearer bearer-value"}',
            "authorization_value",
        ),
        (
            "basic.md",
            "Authorization: Basic basic-value",
            "authorization_value",
        ),
        (
            "url.log",
            "https://user:pass@example.test:8443/post?token=value#frag",
            "sensitive_url",
        ),
        (
            "encoded.log",
            "token%3Dencoded-token-value",
            "encoded_sensitive_assignment",
        ),
    ],
)
def test_scanner_detects_supported_sensitive_artifact_patterns(
    tmp_path,
    name,
    content,
    expected_rule,
):
    artifact = tmp_path / "nested" / name
    artifact.parent.mkdir()
    artifact.write_text(content, encoding="utf-8")

    findings = scan_artifacts([tmp_path])

    assert expected_rule in {item.rule_id for item in findings}
    assert content not in json.dumps([
        item.model_dump(mode="json") for item in findings
    ])


def test_scanner_ignores_unsupported_extensions(tmp_path):
    (tmp_path / "raw.bin").write_text(
        "Authorization: Bearer unsupported-secret",
        encoding="utf-8",
    )

    assert scan_artifacts([tmp_path]) == []


def test_scanner_turns_read_error_into_safe_finding(
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / "unreadable.log"
    artifact.write_text("not returned", encoding="utf-8")
    original = Path.read_text

    def fail_for_artifact(path, *args, **kwargs):
        if path == artifact:
            raise OSError("raw-file-content-must-not-escape")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_for_artifact)

    findings = scan_artifacts([artifact])
    serialized = json.dumps([
        item.model_dump(mode="json") for item in findings
    ])

    assert len(findings) == 1
    assert findings[0].rule_id == "read_error"
    assert findings[0].match_length == 0
    assert "raw-file-content-must-not-escape" not in serialized


def test_scanner_cli_exit_codes_do_not_echo_secret(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "scripts" / "security" / "scan_p5_7_artifacts.py"
    unsafe = tmp_path / "unsafe.log"
    secret = "cli-secret-must-not-escape"
    unsafe.write_text(
        f"Authorization: Bearer {secret}",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), "--path", str(unsafe)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 1
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert json.loads(result.stdout)[0]["rule_id"] == "authorization_value"

    safe = tmp_path / "safe.json"
    safe.write_text('{"authorization":"[REDACTED]"}', encoding="utf-8")
    clean = subprocess.run(
        [sys.executable, str(script), "--path", str(safe)],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert clean.returncode == 0
    assert json.loads(clean.stdout) == []

# P5.7 Security Acceptance

> Implementation date: 2026-08-08. Final verification refreshed: 2026-08-09.

## Verdict

Engineering gate: PASS

This verdict covers P5.7 only. It does not complete real A2A (P5.5), real
platform adapters (P5.3/P5.4), the local/A2A comparison (P5.6), M1, M4, or
M5.

## Evidence matrix

| Requirement | Test evidence | Result |
| --- | --- | --- |
| Redirect target revalidation | `tests/security/test_p5_7_acceptance.py::test_p5_7_redirect_targets_are_revalidated` | PASS |
| DNS change/private blocking | `tests/security/test_p5_7_acceptance.py::test_p5_7_dns_private_answers_are_blocked_and_public_ip_is_pinned` | PASS |
| URL component redaction | `tests/security/test_p5_7_acceptance.py::test_p5_7_sensitive_url_components_never_leave_boundaries` | PASS |
| Prompt-injection isolation | `tests/security/test_p5_7_acceptance.py::test_p5_7_untrusted_page_text_stays_in_user_data` | PASS |
| Platform body cannot become system instruction | `tests/security/test_p5_7_acceptance.py::test_p5_7_platform_text_does_not_authorize_tool_calls` | PASS |
| Path traversal and abnormal media references | `tests/security/test_p5_7_acceptance.py::test_p5_7_media_traversal_and_abnormal_refs_fail_closed` | PASS |
| MCP/fake-A2A timeout, forgery, authorization | `tests/security/test_p5_7_acceptance.py::test_p5_7_mcp_and_fake_a2a_remote_policy_fail_closed` | PASS |
| Log/report/run secrecy | `tests/security/test_p5_7_acceptance.py::test_p5_7_generated_artifacts_are_secret_free` plus artifact-scanner CLI | PASS |

Every rejection test checks that the disallowed next transport, media
validator, tool gateway, remote client, or local fallback was not called. The
MCP transport-timeout case separately verifies exactly one audited local
fallback.

## Commands and observed output

Run from `implicit-ad-agent` unless stated otherwise.

Focused P5.7 suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest `
  tests\adapters\platforms\test_url_safety.py `
  tests\adapters\platforms\test_safe_fetch.py `
  tests\adapters\platforms\test_media_safety.py `
  tests\adapters\platforms\test_url_import.py `
  tests\orchestration\test_remote_policy.py `
  tests\orchestration\test_mcp_gateway.py `
  tests\orchestration\test_function_calling.py `
  tests\protocols\mcp tests\security -q
```

```text
144 passed in 5.31s
exit code: 0
```

Full default zero-key suite:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q
```

```text
495 passed, 2 skipped, 1 warning in 12.71s
exit code: 0
```

The one warning is the pre-existing Starlette/httpx `TestClient` deprecation
warning. The two installed YOLO/EasyOCR integration tests remain deliberate
opt-in skips.

Static and dependency checks:

```powershell
& '.\.venv\Scripts\python.exe' -m compileall -q impad scripts\security
& '.\.venv\Scripts\python.exe' -m pip check
```

```text
compileall exit code: 0
No broken requirements found.
pip check exit code: 0
```

From the repository root:

```powershell
git diff --check
git status --short
git diff --name-only 1928d3f..HEAD
```

```text
git diff --check exit code: 0
The inspected committed range contained only P5.7 files; counting the design
commit at `1928d3f`, P5.7 consists of eight scoped commits. Pre-existing
unrelated P4/P5.2 working-tree changes remain unstaged and were not included.
```

Clean generated acceptance run scanned by the production CLI:

```powershell
& '.\.venv\Scripts\python.exe' scripts\security\scan_p5_7_artifacts.py `
  --path 'C:\Users\31729\AppData\Local\Temp\pytest-of-31729\pytest-349\test_p5_7_generated_artifacts_0\runs'
```

```text
[]
exit code: 0
```

Unsafe synthetic fixture control:

```powershell
& '.\.venv\Scripts\python.exe' scripts\security\scan_p5_7_artifacts.py `
  --path 'C:\Users\31729\AppData\Local\Temp\pytest-of-31729\pytest-349\test_scanner_cli_exit_codes_do0\unsafe.log'
```

```text
one authorization_value finding; line 1; only match length and SHA-256 shown
exit code: 1
synthetic secret absent from stdout and stderr
```

The committed production diff contains policy code and no real platform URL,
Cookie, token, raw media, or user data. Generated runtime artifacts and public
status documents contain none of the four fixed acceptance markers; test
sources and the historical implementation-plan snippets are not generated
artifacts.

## Residual boundary

- No real platform network request was used; all DNS, redirects, transports,
  media references, MCP peers, and A2A operations in this acceptance were
  deterministic fakes.
- Fake A2A transport proves the shared security policy only.
- Real P5.3/P5.4 adapters, P5.5 discovery/task exchange/deployment, and P5.6
  local/A2A comparison remain pending.
- P5.7 engineering PASS does not change the current M1, M4, or M5 gates.

# P1/M1 Integration into P3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the latest P1 data-engineering branch into P3, remove local/generated artifacts, make the P3 input chain strictly support Schema v1.0/v1.1/v1.2, and audit the supplied local dataset ZIP without committing private data.

**Architecture:** Work on an isolated branch created from P3, perform a non-fast-forward merge with review before the merge commit, and keep raw data under ignored `data/run_outputs/`. Route P1 records to a cached JSON Schema validator selected by `schema_version`; keep P3 runtime contracts narrow while preserving extended v1.2 fields in source records and data reports.

**Tech Stack:** Git worktrees, Python 3.10, Pydantic, jsonschema Draft 2020-12, pytest, PowerShell/.NET ZIP APIs.

## Global Constraints

- Do not modify or delete `C:\Users\31729\Desktop\merged_20260728.zip`.
- Do not commit raw JSONL, media, source URLs, account lists, private mappings, or human-review materials.
- Preserve P3 `AnalysisService`, P4 engineering admission, and P5.2 workbench behavior.
- Preserve M1 thresholds: unique candidates `>=3000`, formal Gold `>=1500`, second-round Cohen kappa `>=0.6`, zero creator/near-duplicate leakage, complete terms/privacy approval, and complete Dataset Card.
- Automatic annotations never count as formal double annotation, kappa, or Gold.
- Use the project venv at `D:\AAA Jobs\Detection-of-Recessive-Advertising\implicit-ad-agent\.venv\Scripts\python.exe`.
- Synchronize `HANDOFF.md` and `docs/已有功能测试指令库.md` with the final verified facts and unfinished boundaries.

---

### Task 1: Isolated P3 baseline

**Files:**
- Local-only: `.git/info/exclude`
- Worktree: `.worktrees/codex-p1-m1-into-p3/`
- Branch: `codex/p1-m1-into-p3`

**Interfaces:**
- Consumes: local `P3` at `ba0ab5802b75ddb58967bbf66b83eb360c395e77`.
- Produces: clean isolated branch and fresh baseline evidence.

- [x] **Step 1: Add `.worktrees/` to local Git exclude**

Run: `git check-ignore -v --no-index .worktrees/probe.txt`

Expected: `.git/info/exclude` reports `.worktrees/` as the matching rule.

- [x] **Step 2: Create the isolated branch**

Run: `git worktree add .worktrees/codex-p1-m1-into-p3 -b codex/p1-m1-into-p3 P3`

Expected: worktree HEAD is `ba0ab58` on `codex/p1-m1-into-p3`.

- [x] **Step 3: Verify the baseline**

Run from `implicit-ad-agent/`:

```powershell
$Python = 'D:\AAA Jobs\Detection-of-Recessive-Advertising\implicit-ad-agent\.venv\Scripts\python.exe'
& $Python -m pip check
& $Python -m compileall -q impad tests scripts app.py run_demo.py run_tools_demo.py
& $Python -m pytest -q
```

Expected: no broken requirements; compilation exits 0; `390 passed, 2 skipped, 1 warning`.

---

### Task 2: Merge P1 while preserving both histories

**Files:**
- Merge: all tracked differences from `origin/P1-·-数据地基与标注规范`
- Resolve: `HANDOFF.md`
- Resolve: `docs/已有功能测试指令库.md`

**Interfaces:**
- Consumes: P3 integration branch and P1 commit `43c59ac11770ea29b87c0612da31ab02d579e165`.
- Produces: a merge state whose eventual commit has P3 and P1 as parents.

- [ ] **Step 1: Start a reviewable non-fast-forward merge**

Run:

```powershell
git merge --no-ff --no-commit 'origin/P1-·-数据地基与标注规范'
git status --short
git diff --name-only --diff-filter=U
```

Expected: merge stops before commit; any unmerged paths are explicitly listed.

- [ ] **Step 2: Reconstruct both document intents**

For every unmerged path, inspect:

```powershell
git show ':1:HANDOFF.md'
git show ':2:HANDOFF.md'
git show ':3:HANDOFF.md'
git show ':1:docs/已有功能测试指令库.md'
git show ':2:docs/已有功能测试指令库.md'
git show ':3:docs/已有功能测试指令库.md'
```

Keep P3's latest P3/P4/P5 facts and add only verified P1/M1 facts. Remove every conflict marker and do not restore claims that P3 is unstarted.

- [ ] **Step 3: Verify the merge ancestry before commit**

Run: `git status --short --branch`

Expected: merge is active, no unexplained unmerged paths remain after resolution, and the working tree contains both P3 and P1 deliverables.

---

### Task 3: Remove generated and machine-local artifacts

**Files:**
- Modify: `.gitignore`
- Remove: `data/annotations/cli_test_20260731_222647.json`
- Remove: `data/annotations/preannotated/auto_20260731_231054.jsonl`
- Remove: `data/annotations/preannotated/stats_20260731_231054.json`
- Remove: `data/bili_urls.txt`
- Remove: `data/bili_urls2.txt`
- Remove: `data/wechat_authors.txt`
- Remove: `data/wechat_authors2.txt`
- Remove: `data/wechat_authors3.txt`
- Remove: `diagnose_jsonl.py`
- Remove: `temp_analyze_merge.py`
- Remove: `temp_check_media.py`
- Remove: `scripts/merge_log.txt`
- Remove: `scripts/merge_output.txt`
- Remove: `scripts/validate_result.txt`

**Interfaces:**
- Consumes: uncommitted merge result from Task 2.
- Produces: reviewable repository tree containing reusable code but no local run artifacts.

- [ ] **Step 1: Remove the exact non-product paths from the merge result**

Use `git rm --ignore-unmatch -- <exact paths above>` so no external file is touched.

- [ ] **Step 2: Add narrow ignore rules**

Append these repository rules:

```gitignore
# Local collection inputs and annotation trial outputs
data/*_urls*.txt
data/*_authors*.txt
data/annotations/cli_test_*.json
data/annotations/preannotated/
scripts/*_output.txt
scripts/validate_result.txt
temp_*.py
diagnose_jsonl.py
```

Existing `data/run_outputs/`, `*.log`, `*.bak`, and `*.zip` rules remain authoritative.

- [ ] **Step 3: Verify cleanup behavior**

Run:

```powershell
git ls-files | rg '(^data/(bili_urls|wechat_authors)|data/annotations/(cli_test|preannotated)|^temp_|^diagnose_jsonl|scripts/(merge_log|merge_output|validate_result))'
git check-ignore -v data/run_outputs/merged_20260728/anonymized_posts.jsonl
git diff --check
```

Expected: the tracked-path search returns no matches; local run output is ignored; diff check exits 0.

- [ ] **Step 4: Complete the merge commit**

Run:

```powershell
git add -- .gitignore HANDOFF.md docs/已有功能测试指令库.md
git status --short
git commit -m "merge: integrate P1 data foundation into P3"
```

Expected: one merge commit with two parents; P1 head is an ancestor of HEAD.

---

### Task 4: Add strict Schema v1.2 runtime compatibility with TDD

**Files:**
- Modify: `implicit-ad-agent/tests/adapters/test_p1_schema_adapter.py`
- Modify: `implicit-ad-agent/tests/test_agents.py`
- Modify: `implicit-ad-agent/impad/adapters/p1_schema.py`
- Modify: `implicit-ad-agent/impad/agents/supervisor.py`
- Verify: `data/schema/data_schema_v1.json`
- Verify: `data/schema/data_schema_v1_2.json`
- Verify: `data-tooling/schema/data_schema_v1_2.json`

**Interfaces:**
- Consumes: content records with `schema_version` equal to `1.0`, `1.1`, or `1.2`.
- Produces: `post_record_from_content_record(record: dict) -> PostRecord` with strict version-routed validation.

- [ ] **Step 1: Write the failing v1.2 adapter test**

Add this literal helper and test to `test_p1_schema_adapter.py`:

```python
def _v12_content_record(schema_version: str = "1.2") -> dict:
    return {
        "schema_version": schema_version,
        "post_id": "post_v12_bilibili_001",
        "platform": "bilibili",
        "source_type": "manual_public_collection",
        "blogger_id": "blogger_v12_001",
        "published_at": "2026-07-28T12:00:00+08:00",
        "title": "测试视频",
        "content_group_id": None,
        "text": "本期视频介绍测试产品",
        "media": [{
            "media_id": "media_v12_001",
            "type": "image",
            "ref": "media/post_v12_bilibili_001/00.jpg",
            "sha256": None,
            "phash": None,
            "ocr_text": None,
            "source_url": None,
            "caption": "封面",
            "is_content": True,
        }],
        "comments": [],
        "blogger_history_refs": [],
        "provenance": {
            "source_ref_hash": "source-v12-001",
            "collected_at": "2026-07-28T12:01:00+08:00",
            "collector": "A",
            "terms_checked_at": "2026-07-28",
            "llm_mode": None,
            "llm_confidence": None,
            "llm_needs_review": False,
            "llm_notes": None,
        },
        "privacy": {
            "anonymized": True,
            "contains_sensitive_data": False,
        },
    }


def test_p1_adapter_validates_and_maps_schema_v12_record():
    post = post_record_from_content_record(_v12_content_record())
    assert post.schema_version == "1.2"
    assert post.platform == "bilibili"
    assert post.creator_id == "blogger_v12_001"
    assert post.media[0].ref == "media/post_v12_bilibili_001/00.jpg"
```

The break this catches: routing every P1 record through the v1.0 schema.

- [ ] **Step 2: Verify RED**

Run:

```powershell
& $Python -m pytest tests/adapters/test_p1_schema_adapter.py::test_p1_adapter_validates_and_maps_schema_v12_record -q
```

Expected: FAIL because v1.0 rejects schema version `1.2` and v1.2 fields.

- [ ] **Step 3: Add failing version and strictness tests**

Add tests asserting:

```python
def test_p1_adapter_accepts_schema_v11_through_v12_validator():
    assert post_record_from_content_record(
        _v12_content_record("1.1")
    ).schema_version == "1.1"


def test_p1_adapter_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match=r"unsupported schema_version: 9.9"):
        post_record_from_content_record(_v12_content_record("9.9"))


def test_p1_adapter_rejects_unknown_v12_fields():
    record = _v12_content_record()
    record["invented_field"] = "must fail"
    with pytest.raises(ValueError, match=r"invented_field"):
        post_record_from_content_record(record)
```

Run the three tests and confirm they fail only because version routing is absent.

- [ ] **Step 4: Implement minimal version-routed validators**

In `p1_schema.py`, replace the single schema path/validator with:

```python
_SCHEMA_PATHS = {
    "1.0": _REPO_ROOT / "data/schema/data_schema_v1.json",
    "1.1": _REPO_ROOT / "data/schema/data_schema_v1_2.json",
    "1.2": _REPO_ROOT / "data/schema/data_schema_v1_2.json",
}


@lru_cache(maxsize=len(_SCHEMA_PATHS))
def _load_validator(schema_version: str) -> Draft202012Validator:
    try:
        schema_path = _SCHEMA_PATHS[schema_version]
    except KeyError as exc:
        raise ValueError(
            f"unsupported schema_version: {schema_version}"
        ) from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())
```

Call `_load_validator(str(record.get("schema_version", "")))` from validation. Keep existing error-path formatting.

In `supervisor.py`, use the explicit supported set `{"1.0", "1.1", "1.2"}` while retaining the structural P1 detection for compatible records.

- [ ] **Step 5: Verify GREEN and existing v1.0 behavior**

Run:

```powershell
& $Python -m pytest tests/adapters/test_p1_schema_adapter.py tests/test_agents.py -q
& $Python ..\scripts\data\validate_submission_assets.py
& $Python ..\data-tooling\validate_submission_assets.py
```

Expected: all adapter/agent tests pass and both v1.0 synthetic asset validators print `VALIDATION PASSED`.

- [ ] **Step 6: Verify schema mirrors and commit**

Run:

```powershell
$a=(Get-FileHash ..\data\schema\data_schema_v1_2.json -Algorithm SHA256).Hash
$b=(Get-FileHash ..\data-tooling\schema\data_schema_v1_2.json -Algorithm SHA256).Hash
if ($a -ne $b) { throw 'Schema v1.2 mirrors differ' }
git diff --check
git add -- implicit-ad-agent/impad/adapters/p1_schema.py implicit-ad-agent/impad/agents/supervisor.py implicit-ad-agent/tests/adapters/test_p1_schema_adapter.py implicit-ad-agent/tests/test_agents.py
git commit -m "feat: accept P1 schema v1.2 in P3 runtime"
```

Expected: hashes match and commit succeeds.

---

### Task 5: Safely extract and audit the supplied local dataset

**Files:**
- Read-only input: `C:\Users\31729\Desktop\merged_20260728.zip`
- Ignored output: `data/run_outputs/merged_20260728/`
- Update: `data/reports/m1/dataset_full_audit.json`
- Update: `data/reports/m1/merged_20260728_schema_validate.json`
- Update: `data/reports/m1/merged_20260728_audit_report.md`
- Update: `data/reports/m1/dataset_card_status.json`
- Update: `data/reports/m1/m1_gate_report.json` only after supplying current structured gate inputs; otherwise retain `passed=false` and document why it was not regenerated.

**Interfaces:**
- Consumes: safe ZIP with `anonymized_posts.jsonl` and `media/`.
- Produces: aggregate-only audit facts and an ignored local dataset directory.

- [ ] **Step 1: Re-run ZIP safety checks**

Open the central directory with `[System.IO.Compression.ZipFile]::OpenRead()` and assert:

```powershell
$unsafe=@($zip.Entries | Where-Object {
  $_.FullName -match '(^|[\\/])\.\.([\\/]|$)' -or
  [System.IO.Path]::IsPathRooted($_.FullName)
})
if ($unsafe.Count -ne 0) { throw "Unsafe ZIP entries: $($unsafe.Count)" }
```

Expected: 16,577 entries and 0 unsafe entries.

- [ ] **Step 2: Extract to the ignored run directory**

Run `Expand-Archive` into `data/run_outputs/merged_20260728/` after asserting the resolved destination remains inside the worktree. Never extract over the external ZIP.

- [ ] **Step 3: Validate Schema v1.2**

Run from repository root:

```powershell
& $Python data-tooling/annotation/validate_schema.py `
  data/run_outputs/merged_20260728/anonymized_posts.jsonl `
  --target-schema 1.2 `
  --schema data-tooling/schema/data_schema_v1_2.json `
  --report data/reports/m1/merged_20260728_schema_validate.json
```

Expected: the report gives exact total/valid/invalid counts; invalid count must be reported, not hidden.

- [ ] **Step 4: Run the aggregate M1 audit**

Inspect `python data-tooling/m1_readiness.py audit --help`, then call the current CLI with the extracted dataset directory, candidate JSONL, media directory, and aggregate report path. Do not pass `.bak` or `anonymized_posts_fixed.jsonl` as additional candidate batches.

Expected report fields: candidate rows, unique posts, duplicates, creators, platform counts, media references, available references, missing references, terms counts, privacy claims, annotation file count, and dataset fingerprint.

- [ ] **Step 5: Interpret the candidate threshold literally**

Assert from the generated JSON:

```powershell
$audit=Get-Content -Raw -Encoding UTF8 data/reports/m1/dataset_full_audit.json | ConvertFrom-Json
if ($audit.candidates.unique_posts -lt 3000) {
  Write-Output "M1 candidate gate failed: $($audit.candidates.unique_posts)/3000"
} else {
  Write-Output "M1 candidate gate passed: $($audit.candidates.unique_posts)/3000"
}
```

This step succeeds when it reports the true state; it must not pad or lower the threshold.

- [ ] **Step 6: Update aggregate documentation and commit only safe reports**

Update the audit Markdown, `HANDOFF.md`, and test runbook with exact generated counts, command lines, and remaining M1 gates. Before staging, scan report diffs for source URLs, post text, creator IDs, annotator IDs, tokens, and secrets.

Commit only aggregate reports and factual docs with:

```powershell
git add -- data/reports/m1 HANDOFF.md docs/已有功能测试指令库.md
git diff --cached --stat
git diff --cached --check
git commit -m "docs: record integrated M1 dataset audit"
```

---

### Task 6: Completion verification for requested steps 1–5

**Files:**
- Verify: whole integration branch

**Interfaces:**
- Consumes: completed Tasks 1–5.
- Produces: requirement-by-requirement evidence without claiming formal M1 unless every gate passes.

- [ ] **Step 1: Verify branch ancestry and merge shape**

```powershell
git merge-base --is-ancestor P3 HEAD
git merge-base --is-ancestor 'origin/P1-·-数据地基与标注规范' HEAD
git log --oneline --decorate --graph -12
```

- [ ] **Step 2: Run focused and full verification**

```powershell
& $Python -m pip check
& $Python -m compileall -q impad tests scripts app.py run_demo.py run_tools_demo.py
& $Python -m pytest tests/adapters/test_p1_schema_adapter.py tests/data/test_m1_readiness.py tests/data/test_data_governance_tools.py -q
& $Python -m pytest -q
```

- [ ] **Step 3: Verify privacy boundaries and clean Git state**

```powershell
git status --short --branch
git ls-files data/run_outputs
git diff --check
```

Expected: no tracked runtime data, no uncommitted task changes, and no whitespace errors.

- [ ] **Step 4: Audit each requested item**

Record evidence separately for: integration branch, P1 merge ancestry, artifact cleanup, Schema v1.2 runtime compatibility, and local dataset audit. A green test suite does not substitute for missing data-governance evidence.


# M1 Data Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete every code- and documentation-side M1 prerequisite that the current real dataset can support, run the authoritative gate, and update HANDOFF without claiming that insufficient data passed M1.

**Architecture:** Treat the external `dataset_full` directory as read-only input. Add a small mirrored M1 readiness module for safe aggregate auditing and gate evaluation, repair existing migration/Schema/privacy/annotation tools in place, and produce repository-safe aggregate reports. Formal readiness remains a conjunction of code checks and real evidence thresholds.

**Tech Stack:** Python 3.10, standard library, `jsonschema>=4.22,<5`, pytest 8, PowerShell, JSON/JSONL, Markdown.

## Global Constraints

- Do not lower M1 thresholds: unique candidates ≥3000, formal gold ≥1500, guide edge cases ≥20, second-round κ≥0.6.
- Do not count duplicate rows, synthetic fixtures, LLM suggestions, `uncertain`, or `out_of_scope` as formal gold.
- Do not copy the 1.723 GiB external media tree into the repository.
- Do not print or persist raw post text, clear source URLs, account identifiers, or sensitive matches in aggregate reports.
- Use Schema v1.0 as the authoritative M1 target; v1.1 remains an unapproved compatibility candidate.
- Missing or unverifiable evidence is `missing` or `review_required`, never a pass.
- Keep `data-tooling/` and `implicit-ad-agent/scripts/data/` mirror files byte-identical where both copies exist.
- Preserve all unrelated dirty-worktree changes.
- Do not stage or commit; replace commit steps with diff checkpoints because no Git integration action was requested.

---

## File Structure

### Create

- `data-tooling/m1_readiness.py` — safe dataset audit, evidence model, M1 gate evaluator, and CLI.
- `implicit-ad-agent/scripts/data/m1_readiness.py` — byte-identical runtime mirror.
- `implicit-ad-agent/tests/data/test_m1_readiness.py` — audit/gate/unit and mirror-consistency tests.
- `implicit-ad-agent/tests/data/test_data_governance_tools.py` — migration, strict Schema, privacy, agreement, gold, and split regression tests.
- `docs/annotation_guide_v1.md` — executable v1.0 guide with 24 edge cases.
- `docs/dataset_card_current.md` — current dataset card with explicit incomplete compliance and scale boundaries.
- `data/reports/m1/dataset_full_audit.json` — aggregate real-data audit without raw content.
- `data/reports/m1/dataset_card_status.json` — machine-readable Dataset Card completion evidence.
- `data/reports/m1/m1_gate_report.json` — authoritative current gate result.
- `data/reports/m1/trial_agreement.json` — aggregate pilot agreement result.

### Modify

- `.gitignore` — ignore local `data/interim/` and private M1 reports.
- `data-tooling/annotation/migrate_p1_candidates_to_v1.py` — conservative v1.0 migration and sidecar metadata.
- `implicit-ad-agent/scripts/data/annotation/migrate_p1_candidates_to_v1.py` — exact mirror.
- `data-tooling/annotation/validate_schema.py` — full Draft 2020-12 validation.
- `implicit-ad-agent/scripts/data/annotation/validate_schema.py` — exact mirror.
- `data-tooling/annotation/privacy_scan.py` — explicit human approval requirement and redacted findings.
- `implicit-ad-agent/scripts/data/annotation/privacy_scan.py` — exact mirror.
- `data-tooling/annotation/calculate_agreement.py` — structured report, strict parsing, and single CLI entry.
- `implicit-ad-agent/scripts/data/annotation/calculate_agreement.py` — exact mirror.
- `data-tooling/annotation/build_gold_dataset.py` — strict parsing/output directory handling if tests expose gaps.
- `implicit-ad-agent/scripts/data/annotation/build_gold_dataset.py` — exact mirror if modified.
- `data-tooling/annotation/split_by_blogger.py` — connected creator/content-group components and explicit leakage report.
- `implicit-ad-agent/scripts/data/annotation/split_by_blogger.py` — exact mirror.
- `data-tooling/README.md` — current commands and phase boundaries.
- `HANDOFF.md` — verified outputs, commands, current gate failures, and P3 boundary.

---

### Task 1: Safe Dataset Audit and M1 Gate Core

**Files:**
- Create: `data-tooling/m1_readiness.py`
- Create: `implicit-ad-agent/scripts/data/m1_readiness.py`
- Create: `implicit-ad-agent/tests/data/test_m1_readiness.py`

**Interfaces:**
- Produces: `load_json_stream(path: Path) -> list[dict[str, Any]]`
- Produces: `audit_dataset(dataset_root: Path) -> dict[str, Any]`
- Produces: `evaluate_m1_gate(evidence: Mapping[str, Any]) -> dict[str, Any]`
- Produces: CLI subcommands `audit` and `gate`

- [ ] **Step 1: Write failing strict-stream and aggregate-audit tests**

```python
import json
from pathlib import Path

import pytest

from scripts.data import m1_readiness as readiness


def write_dataset(root: Path, posts: list[dict]) -> None:
    (root / "annotations").mkdir(parents=True)
    (root / "interim").mkdir()
    with (root / "anonymized_postsn.jsonl").open("w", encoding="utf-8") as stream:
        for post in posts:
            stream.write(json.dumps(post, ensure_ascii=False) + "\n")


def test_load_json_stream_rejects_corrupt_trailing_object(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"post_id":"a"}\\n{"post_id":', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        readiness.load_json_stream(path)


def test_audit_counts_unique_posts_not_rows(tmp_path: Path) -> None:
    write_dataset(
        tmp_path,
        posts=[
            {"post_id": "p1", "blogger_id": "b1", "platform": "wechat_official_account", "media": []},
            {"post_id": "p1", "blogger_id": "b1", "platform": "wechat_official_account", "media": []},
            {"post_id": "p2", "blogger_id": "b2", "platform": "xiaohongshu", "media": []},
        ],
    )
    report = readiness.audit_dataset(tmp_path)
    assert report["candidates"]["rows"] == 3
    assert report["candidates"]["unique_posts"] == 2
    assert report["candidates"]["duplicate_post_rows"] == 1
    assert "dataset_root" not in report
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_m1_readiness.py -q
```

Expected: collection/import failure because `scripts.data.m1_readiness` does not exist.

- [ ] **Step 3: Implement strict parsing and privacy-safe audit**

Core parser:

```python
def load_json_stream(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        value, position = decoder.raw_decode(text, position)
        if not isinstance(value, dict):
            raise TypeError(f"record {len(records)} must be an object")
        records.append(value)
    return records
```

`audit_dataset()` must discover only known relative files, calculate row/unique/duplicate counts, annotation overlap, platform counts, media-reference coverage, and safe file digests. It must not include raw values for `text`, source URL, blogger IDs, annotator IDs, or matched secrets.

- [ ] **Step 4: Write failing gate truth-table tests**

```python
def complete_evidence() -> dict[str, object]:
    return {
        "candidate_unique_count": 3000,
        "gold_count": 1500,
        "guide_edge_case_count": 20,
        "second_round_kappa": 0.6,
        "creator_leakage_count": 0,
        "near_duplicate_leakage_count": 0,
        "privacy_approved": True,
        "terms_complete": True,
        "dataset_card_complete": True,
    }


def test_gate_fails_missing_and_insufficient_evidence() -> None:
    result = readiness.evaluate_m1_gate({
        "candidate_unique_count": 282,
        "gold_count": 36,
        "guide_edge_case_count": 24,
        "second_round_kappa": 1.0,
        "creator_leakage_count": None,
        "near_duplicate_leakage_count": None,
        "privacy_approved": False,
        "terms_complete": False,
        "dataset_card_complete": False,
    })
    assert result["passed"] is False
    assert result["checks"]["candidate_pool"]["status"] == "failed"
    assert result["checks"]["split_leakage"]["status"] == "missing"


def test_gate_passes_only_complete_real_evidence_fixture() -> None:
    result = readiness.evaluate_m1_gate(complete_evidence())
    assert result["passed"] is True
    assert all(check["status"] == "passed" for check in result["checks"].values())
```

- [ ] **Step 5: Implement explicit gate checks and CLI exit codes**

Each check has:

```python
{
    "status": "passed" | "failed" | "missing" | "review_required",
    "observed": JSON_scalar_or_null,
    "required": JSON_scalar_or_description,
}
```

`audit` returns 0 on successful audit. `gate` returns 0 only when every check passes and 2 for a valid failing report.

- [ ] **Step 6: Mirror, verify GREEN, and checkpoint**

Copy the finalized source exactly into both locations using `Copy-Item`, then run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_m1_readiness.py -q
git diff --check -- ../data-tooling/m1_readiness.py scripts/data/m1_readiness.py tests/data/test_m1_readiness.py
```

Expected: all focused tests pass and mirror hash assertion passes.

---

### Task 2: Conservative v1.0 Candidate Migration

**Files:**
- Modify: `data-tooling/annotation/migrate_p1_candidates_to_v1.py`
- Modify: `implicit-ad-agent/scripts/data/annotation/migrate_p1_candidates_to_v1.py`
- Modify: `implicit-ad-agent/tests/data/test_migrate_p1_candidates.py`

**Interfaces:**
- Keeps: `migrate_record(...) -> tuple[dict[str, Any] | None, str]`
- Produces: `build_migration_meta(record, status, original_post_id) -> dict[str, Any]`
- Produces: CLI `--input-file`, `--report`, default `--target-schema 1.0`

- [ ] **Step 1: Replace permissive expectations with failing conservative tests**

```python
def test_provenance_preserves_hash_and_never_emits_clear_url(old_format_record):
    old_format_record["_collected"]["source_ref_hash"] = "known_hash"
    provenance = migrate_provenance(old_format_record)
    assert provenance["source_ref_hash"] == "known_hash"
    assert "https://" not in json.dumps(provenance)


def test_missing_required_provenance_is_rejected(old_format_record_no_collected):
    migrated, status = migrate_record(
        old_format_record_no_collected, {}, "salt", Path("data"), "1.0", True
    )
    assert migrated is None
    assert status == "rejected"


def test_privacy_defaults_are_conservative(old_format_record):
    assert migrate_privacy(old_format_record) == {
        "anonymized": False,
        "contains_sensitive_data": True,
    }


def test_migration_metadata_is_not_embedded_in_content_record(old_format_record):
    migrated, _ = migrate_record(old_format_record, {}, "salt", Path("data"), "1.0", True)
    assert "_migration_meta" not in migrated
```

- [ ] **Step 2: Run migration tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_migrate_p1_candidates.py -q
```

Expected: failures on fabricated provenance/privacy and embedded `_migration_meta`.

- [ ] **Step 3: Implement minimal conservative semantics**

```python
def migrate_provenance(record: dict[str, Any]) -> dict[str, Any] | None:
    collected = record.get("_collected")
    if not isinstance(collected, dict):
        return None
    source_hash = collected.get("source_ref_hash")
    if not source_hash and collected.get("source_url"):
        source_hash = hashlib.sha256(
            collected["source_url"].encode("utf-8")
        ).hexdigest()
    if not source_hash or not collected.get("collected_at") or not collected.get("collector"):
        return None
    return {
        "source_ref_hash": source_hash,
        "collected_at": collected["collected_at"],
        "collector": collected["collector"],
        "terms_checked_at": collected.get("terms_checked_at"),
    }
```

Remove the SHA-prefix pseudo-pHash. Preserve `sha256=None` and `phash=None` when media is skipped. Keep migration metadata only in the sidecar report.

- [ ] **Step 4: Add CLI single-file input and aggregate sidecar**

`--input-file` bypasses directory discovery. The report includes row count, unique IDs, rejected/degraded/success counts, duplicate IDs, missing fields, and media-hash coverage without raw text or URLs.

- [ ] **Step 5: Mirror, run tests, and checkpoint**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_migrate_p1_candidates.py -q
git diff --check -- ../data-tooling/annotation/migrate_p1_candidates_to_v1.py scripts/data/annotation/migrate_p1_candidates_to_v1.py tests/data/test_migrate_p1_candidates.py
```

Expected: focused tests pass and both production copies are byte-identical.

---

### Task 3: Full JSON Schema Validation

**Files:**
- Modify: `data-tooling/annotation/validate_schema.py`
- Modify: `implicit-ad-agent/scripts/data/annotation/validate_schema.py`
- Create or modify: `implicit-ad-agent/tests/data/test_data_governance_tools.py`

**Interfaces:**
- Produces: `resolve_schema_path(version: str, explicit: Path | None = None) -> Path`
- Keeps: `validate_record(record: dict[str, Any], schema: dict[str, Any]) -> list[str]`
- Produces: CLI `--schema`, `--report`, nonzero exit on invalid records

- [ ] **Step 1: Write failing strict-validator tests**

```python
import copy
import json
from pathlib import Path

import pytest

from scripts.data.annotation import validate_schema


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def schema_v1(repo_root: Path) -> dict:
    return json.loads(
        (repo_root.parent / "data" / "schema" / "data_schema_v1.json").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture
def valid_v1_record(repo_root: Path) -> dict:
    dataset = json.loads(
        (repo_root.parent / "data" / "synthetic" / "simulated_posts_v1.json").read_text(
            encoding="utf-8"
        )
    )
    return copy.deepcopy(dataset["content_records"][0])


def test_validate_record_rejects_additional_property(valid_v1_record, schema_v1):
    valid_v1_record["_migration_meta"] = {}
    errors = validate_schema.validate_record(valid_v1_record, schema_v1)
    assert any("additionalProperties" in error for error in errors)


def test_validate_record_rejects_bad_datetime(valid_v1_record, schema_v1):
    valid_v1_record["provenance"]["collected_at"] = "not-a-date"
    errors = validate_schema.validate_record(valid_v1_record, schema_v1)
    assert any("format" in error for error in errors)
```

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_data_governance_tools.py -q
```

Expected: hand-written validator misses at least the extra property or format violation.

- [ ] **Step 3: Replace hand-written structure checks with Draft 2020-12**

```python
from jsonschema import Draft202012Validator, FormatChecker


def validate_record(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{error.validator}: {'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path))
    ]
```

The report groups errors by validator and record index, never by raw record content.

- [ ] **Step 4: Mirror, run focused tests, and checkpoint**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_data_governance_tools.py -q
git diff --check -- ../data-tooling/annotation/validate_schema.py scripts/data/annotation/validate_schema.py
```

Expected: strict validation tests pass.

---

### Task 4: Privacy Scan Requires Human Approval

**Files:**
- Modify: `data-tooling/annotation/privacy_scan.py`
- Modify: `implicit-ad-agent/scripts/data/annotation/privacy_scan.py`
- Modify: `implicit-ad-agent/tests/data/test_data_governance_tools.py`

**Interfaces:**
- Produces: `classify_record(record, findings, approved_post_ids=frozenset()) -> str`
- Produces: `redact_finding(finding: Mapping[str, Any]) -> dict[str, Any]`
- Produces: CLI `--approval-file`

- [ ] **Step 1: Write failing classification and redaction tests**

```python
import json

from scripts.data.annotation import privacy_scan


def safe_record(*, terms_checked_at: str | None) -> dict:
    return {
        "post_id": "post_safe",
        "privacy": {
            "anonymized": True,
            "contains_sensitive_data": False,
        },
        "provenance": {
            "terms_checked_at": terms_checked_at,
        },
    }


def test_no_findings_without_human_approval_is_interim():
    record = safe_record(terms_checked_at="2026-07-26")
    assert privacy_scan.classify_record(record, [], set()) == "interim"


def test_public_requires_terms_privacy_flags_and_explicit_approval():
    record = safe_record(terms_checked_at="2026-07-26")
    assert privacy_scan.classify_record(record, [], {record["post_id"]}) == "public"


def test_report_does_not_retain_sensitive_match():
    finding = {"field": "text", "type": "手机号", "match": "13800138000", "severity": "critical"}
    redacted = privacy_scan.redact_finding(finding)
    assert "13800138000" not in json.dumps(redacted, ensure_ascii=False)
    assert "match_hash" in redacted
```

- [ ] **Step 2: Run and verify RED**

Run the focused governance test; expect the current implementation to auto-classify no-findings records as public and retain raw matches.

- [ ] **Step 3: Implement explicit approval and safe findings**

`public` requires all of:

```python
privacy.get("anonymized") is True
privacy.get("contains_sensitive_data") is False
bool(provenance.get("terms_checked_at"))
post_id in approved_post_ids
not findings
```

All other no-critical records are `interim`; critical findings are `raw`. Store only rule, field, severity, match length, and SHA-256 digest.

- [ ] **Step 4: Mirror, run tests, and checkpoint**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_data_governance_tools.py -q
git diff --check -- ../data-tooling/annotation/privacy_scan.py scripts/data/annotation/privacy_scan.py
```

Expected: focused tests pass and no clear sensitive example appears in generated reports.

---

### Task 5: Agreement, Gold, and Leakage-Safe Split

**Files:**
- Modify: `data-tooling/annotation/calculate_agreement.py`
- Modify: `implicit-ad-agent/scripts/data/annotation/calculate_agreement.py`
- Modify if required: `data-tooling/annotation/build_gold_dataset.py`
- Modify if required: `implicit-ad-agent/scripts/data/annotation/build_gold_dataset.py`
- Modify: `data-tooling/annotation/split_by_blogger.py`
- Modify: `implicit-ad-agent/scripts/data/annotation/split_by_blogger.py`
- Modify: `implicit-ad-agent/tests/data/test_data_governance_tools.py`

**Interfaces:**
- Produces: `calculate_agreement(a: Mapping[str, str], b: Mapping[str, str]) -> dict[str, Any]`
- Keeps: `merge_annotations(...) -> tuple[list[dict], list[dict]]`
- Produces: `build_split_groups(records) -> dict[str, list[str]]`
- Produces: `validate_split_leakage(records, assignments) -> dict[str, int]`

- [ ] **Step 1: Write failing agreement regression tests**

```python
import subprocess
import sys

from scripts.data.annotation import calculate_agreement, split_by_blogger


def test_agreement_excludes_special_and_unknown_labels():
    report = calculate_agreement.calculate_agreement(
        {"p1": "明广", "p2": "uncertain", "p3": "bad"},
        {"p1": "明广", "p2": "非广", "p3": "非广"},
    )
    assert report["valid_pair_count"] == 1
    assert report["kappa"] == 1.0
    assert report["excluded_pair_count"] == 2


def test_agreement_cli_has_one_entrypoint_and_writes_json(tmp_path, repo_root):
    path_a = tmp_path / "a.jsonl"
    path_b = tmp_path / "b.jsonl"
    output = tmp_path / "agreement.json"
    path_a.write_text(
        json.dumps({"post_id": "p1", "label": "明广"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    path_b.write_text(
        json.dumps({"post_id": "p1", "label": "明广"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    script = repo_root.parent / "data-tooling" / "annotation" / "calculate_agreement.py"
    result = subprocess.run(
        [sys.executable, str(script), str(path_a), str(path_b), "--output", str(output)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8"))["valid_pair_count"] == 1
```

- [ ] **Step 2: Implement structured agreement and remove duplicate `__main__` block**

Return counts, κ, bootstrap interval, confusion matrix, per-class agreement, and excluded/special-label counts. Do not include post IDs in the aggregate report.

- [ ] **Step 3: Write failing creator/content-group component tests**

```python
def test_shared_content_group_connects_entire_creators():
    records = [
        {"post_id": "a1", "blogger_id": "a", "content_group_id": None},
        {"post_id": "a2", "blogger_id": "a", "content_group_id": "g"},
        {"post_id": "b1", "blogger_id": "b", "content_group_id": "g"},
        {"post_id": "b2", "blogger_id": "b", "content_group_id": None},
    ]
    groups = split_by_blogger.build_split_groups(records)
    assert len(groups) == 1
    assert sorted(next(iter(groups.values()))) == ["a1", "a2", "b1", "b2"]
```

- [ ] **Step 4: Implement connected components and explicit leakage validation**

Use a small union-find over creator IDs and `content_group_id` nodes. Every connected component contains all posts belonging to its creators. After assignment, verify zero post, creator, and content-group overlap across train/dev/test.

- [ ] **Step 5: Verify gold rules with focused tests**

Cover agreed valid labels, unresolved disagreements, `uncertain`, `out_of_scope`, missing annotator, and adjudicated valid labels. Modify `build_gold_dataset.py` only if a test exposes an actual contract violation.

- [ ] **Step 6: Mirror, run tests, and checkpoint**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_data_governance_tools.py -q
git diff --check -- ../data-tooling/annotation scripts/data/annotation tests/data/test_data_governance_tools.py
```

Expected: agreement/gold/split tests pass and mirror copies match.

---

### Task 6: Annotation Guide and Current Dataset Card

**Files:**
- Create: `docs/annotation_guide_v1.md`
- Create: `docs/dataset_card_current.md`
- Modify: `implicit-ad-agent/tests/data/test_m1_readiness.py`

**Interfaces:**
- Guide edge cases use headings `### EC-01` through `### EC-24`
- Dataset Card has sections: purpose, composition, collection, labeling, privacy/terms, leakage, limitations, allowed use
- Produces: `count_guide_edge_cases(path: Path) -> int`
- Produces: `data/reports/m1/dataset_card_status.json`

- [ ] **Step 1: Write failing gate-consumer tests**

```python
def test_gate_counts_unique_structured_edge_cases(tmp_path: Path):
    guide = tmp_path / "guide.md"
    guide.write_text(
        "### EC-01 first\n\n### EC-01 duplicate\n\n### EC-02 second\n",
        encoding="utf-8",
    )
    assert readiness.count_guide_edge_cases(guide) == 2


def test_incomplete_dataset_card_status_cannot_pass_gate():
    evidence = complete_evidence()
    evidence["dataset_card_complete"] = False
    result = readiness.evaluate_m1_gate(evidence)
    assert result["checks"]["dataset_card"]["status"] == "failed"
    assert result["passed"] is False
```

- [ ] **Step 2: Run and verify RED**

Expected: missing `count_guide_edge_cases` behavior fails the focused test.

- [ ] **Step 3: Write the 24-case guide**

Each case specifies observable evidence, expected primary label or governance status, counterexample, missing-evidence behavior, and whether it enters κ/gold.

- [ ] **Step 4: Write the current Dataset Card and structured status**

Document only verified aggregate facts. Mark source terms, public-release approval, ≥3000 candidates, ≥1500 gold, formal split, and full privacy review as incomplete.

Write `data/reports/m1/dataset_card_status.json` with `terms_complete`, `privacy_approved`, `split_complete`, and `dataset_card_complete`; each remains false until supported by external evidence.

- [ ] **Step 5: Run tests and checkpoint**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/data/test_m1_readiness.py -q
git diff --check -- ../docs/annotation_guide_v1.md ../docs/dataset_card_current.md
```

Expected: gate-consumer tests pass; the actual guide is counted as 24 unique structured cases.

---

### Task 7: Run the Real Dataset Trial and Produce Safe Reports

**Files:**
- Modify: `.gitignore`
- Create: `data/reports/m1/dataset_full_audit.json`
- Create: `data/reports/m1/trial_agreement.json`
- Create: `data/reports/m1/m1_gate_report.json`

**Interfaces:**
- Consumes: all preceding CLIs
- Produces: aggregate, repository-safe evidence artifacts

- [ ] **Step 1: Add local-data ignore boundaries**

Add:

```gitignore
data/interim/
data/reports/m1/private/
```

- [ ] **Step 2: Run the safe external-data audit**

From repository root:

```powershell
$datasetRootM1 = 'C:\Users\31729\Desktop\dataset_full'
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\m1_readiness.py audit `
  --dataset-root $datasetRootM1 `
  --output .\data\reports\m1\dataset_full_audit.json
```

Expected: exit 0; report shows 282 unique candidates, 15 creators, 36 common valid annotation IDs, and no raw text/URLs/identifiers.

- [ ] **Step 3: Run conservative migration into ignored interim storage**

```powershell
$datasetRootM1 = 'C:\Users\31729\Desktop\dataset_full'
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\annotation\migrate_p1_candidates_to_v1.py `
  --input-file "$datasetRootM1\anonymized_postsn.jsonl" `
  --output .\data\interim\m1\candidates_v1.jsonl `
  --id-map .\data\interim\m1\id_mapping_v1.json `
  --report .\data\reports\m1\private\migration_report.json `
  --media-base "$datasetRootM1" `
  --target-schema 1.0 `
  --skip-media-hash
```

Expected: no input files changed; no clear URLs in outputs; rejected/degraded records reported rather than fabricated.

- [ ] **Step 4: Run strict Schema and privacy scans**

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\annotation\validate_schema.py `
  .\data\interim\m1\candidates_v1.jsonl `
  --target-schema 1.0 `
  --report .\data\reports\m1\private\schema_report.json

.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\annotation\privacy_scan.py `
  --input .\data\interim\m1\candidates_v1.jsonl `
  --output-dir .\data\reports\m1\private
```

Expected: Schema command passes for emitted records; privacy command produces zero public approvals without an explicit human approval file.

- [ ] **Step 5: Run pilot agreement**

```powershell
$datasetRootM1 = 'C:\Users\31729\Desktop\dataset_full'
$annotationFilesM1 = Get-ChildItem -File -LiteralPath "$datasetRootM1\annotations" | Sort-Object Name
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\annotation\calculate_agreement.py `
  $annotationFilesM1[0].FullName `
  $annotationFilesM1[1].FullName `
  --output .\data\reports\m1\trial_agreement.json
```

Expected: aggregate report covers 36 common valid annotation IDs, uses 22 three-class pairs for κ, and clearly labels it as pilot evidence.

- [ ] **Step 6: Run the M1 gate and verify intentional failure**

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe .\data-tooling\m1_readiness.py gate `
  --audit .\data\reports\m1\dataset_full_audit.json `
  --guide .\docs\annotation_guide_v1.md `
  --agreement .\data\reports\m1\trial_agreement.json `
  --dataset-card-status .\data\reports\m1\dataset_card_status.json `
  --output .\data\reports\m1\m1_gate_report.json
$gateExitM1 = $LASTEXITCODE
if ($gateExitM1 -ne 2) { throw "Expected current real-data M1 gate to fail with exit 2, got $gateExitM1" }
```

Expected failures include candidate scale, gold scale, formal split evidence, privacy approval, terms completion, and Dataset Card completion; guide count passes.

- [ ] **Step 7: Scan reports for forbidden raw content and checkpoint**

Use a test that asserts report keys are allowlisted and no `text`, `source_url`, `blogger_id`, `annotator_id`, or raw match values occur. Then run `git diff --check`.

---

### Task 8: Documentation, Full Regression, and Handoff

**Files:**
- Modify: `data-tooling/README.md`
- Modify: `HANDOFF.md`
- Modify if acceptance facts changed: `docs/隐性广告识别项目_分阶段计划表.md`

**Interfaces:**
- Consumes: current reports and fresh command output
- Produces: reproducible handoff with no overstated phase claim

- [ ] **Step 1: Update data-tooling commands**

Document PowerShell-safe commands for audit, migration, strict Schema, privacy, agreement, gate, and focused tests. Mark the external dataset path as a local example, not a repository dependency.

- [ ] **Step 2: Update HANDOFF from generated evidence**

Record:

- 282 unique candidates, 15 creators, one platform;
- 36 common pilot annotation IDs, 22 valid three-class pairs, and measured κ;
- Schema migration results and privacy/public counts;
- guide edge-case count;
- every passed/failed/missing M1 check;
- M2.5 code gate status;
- exact commands to resume after new data and human labels exist;
- P3 interface-ready versus formal-stage-not-open distinction.

- [ ] **Step 3: Run focused data tests**

```powershell
cd .\implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests/data -q
```

Expected: all data-tool tests pass.

- [ ] **Step 4: Run dependency and compile checks**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests scripts
```

Expected: no broken requirements and no compile errors.

- [ ] **Step 5: Run complete default regression**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all default tests pass; optional real-network/key/vision paths remain skipped or opt-in.

- [ ] **Step 6: Validate mirror files and working-tree hygiene**

```powershell
cd ..
git diff --check
```

Also compare SHA-256 for every modified mirror pair. Expected: no differences.

- [ ] **Step 7: Final requirement-by-requirement audit**

Read `m1_gate_report.json`, the spec, phase plan, and HANDOFF together. Do not mark the persistent goal complete unless the real gate is fully passed. If the current data still fails M1 after every local task is exhausted, keep the goal incomplete and report the exact external data/human-label requirements.

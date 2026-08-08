# Merged History Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, leakage-safe three-class paper baseline that compares a single-post feature vector with the same vector concatenated to mean, max, or chronological EMA creator-history pooling.

**Architecture:** A root `baseline/` package loads versioned content, formal Gold, audited split artifacts, and an M1 gate before constructing one shared complete cohort. Four independently fitted scikit-learn Logistic Regression pipelines differ only in their input vector; synthetic mode exercises the full pipeline while forcing `research_claims_allowed=false`, and formal mode fails before training until every governance and leakage gate passes.

**Tech Stack:** Python 3.10+, standard library dataclasses/JSON/hashlib, scikit-learn `>=1.5,<2`, pytest `>=8,<9`, jsonschema `>=4.22,<5`.

> **完成审计纠正（2026-08-08）：** 最终 `baseline/requirements.txt` 另含 `jsonschema`，用于权威 formal Schema v1.2 校验；`MethodResult` 仅保留 aggregate-only 字段，named-class 映射由聚合 Brier/AUPRC 测试验证。此说明覆盖早期示例与最终实现的发现性偏差。

## Global Constraints

- Do not modify `implicit-ad-agent` runtime code, LangGraph, Judge, APIs, or existing CreatorShift behavior.
- Do not stage, restore, or edit the four pre-existing deleted paths in the working tree.
- Formal labels are exactly `明广`, `暗广`, and `非广`; automated, system, uncertain, out-of-scope, missing, or duplicate Gold records fail closed.
- Formal mode requires top-level `m1_gate_report.passed == true` plus complete, non-overlapping, leakage-zero split evidence before importing or fitting scikit-learn.
- History must be unique, resolvable, same-creator, non-self, timezone-aware, and strictly earlier than the target; an integrity violation aborts the run.
- A missing target timestamp or fewer than three otherwise valid history posts excludes that target from the shared cohort with an aggregate reason count.
- Feature version is `keyword_weights_v1`; dimension order is `promotion_words`, `price_mentions`, `urgency_expressions`, `brand_mentions`, `action_words`, `natural_expression`.
- EMA uses chronological order and `alpha=0.5`.
- Classifier parameters are `solver="lbfgs"`, `C=1.0`, `max_iter=1000`, `random_state=0`, `class_weight=None`.
- All four methods use the same target IDs in train and evaluation splits; only their feature vectors differ.
- Synthetic reports set `mode="synthetic"`, `dataset_kind="synthetic_fixture"`, and `research_claims_allowed=false`.
- Reports contain hashes, versions, parameters, aggregate counts, metrics, and confusion counts only; never raw text, URLs, media paths, creator/annotator/arbiter IDs, or per-sample predictions.
- Default formal evaluation is dev; test requires `--confirm-test-evaluation` and records that confirmation.
- No true paper metric, CreatorShift gain, M1 passage, M4 passage, statistical significance, or stable improvement may be claimed from the synthetic run.

---

## File Structure

- `baseline/README.md`: setup, formal/synthetic commands, report interpretation, and research-boundary warnings.
- `baseline/requirements.txt`: isolated scikit-learn, pytest, and jsonschema dependencies.
- `baseline/__init__.py`: public constants and exception exports.
- `baseline/contracts.py`: dataclasses, JSON/JSONL/ID loading, Gold/content join, split and gate validation, and input hashes.
- `baseline/features.py`: pinned keyword features, history integrity validation, shared cohort creation, and mean/max/EMA vector construction.
- `baseline/runner.py`: isolated sklearn import, fixed pipelines, train-only fitting, probability reordering, and four-method orchestration.
- `baseline/reporting.py`: metrics, confusion counts, deltas, privacy-safe versioned report assembly, and deterministic JSON serialization.
- `baseline/cli.py`: explicit `synthetic` and `formal` subcommands, test-confirmation guard, error exit codes, and atomic report write.
- `baseline/tests/fixtures/`: versioned content/Gold/split/gate fixtures containing synthetic text and anonymous fixture IDs only.
- `baseline/tests/test_contracts.py`: gate, join, split, label, and privacy-safe error tests.
- `baseline/tests/test_features.py`: keyword parity, history integrity, exact pooling, exclusion, and shared-cohort tests.
- `baseline/tests/test_runner.py`: deterministic model, probability mapping, metric, delta, and report-privacy tests.
- `baseline/tests/test_cli.py`: synthetic end-to-end success, current M1 formal rejection, and test-confirmation tests.
- `docs/隐性广告识别项目_说明书.md`: update `baseline/` from absent to engineering-ready with formal research still gated.
- `docs/隐性广告识别项目_分阶段计划表.md`: record the merged-history baseline engineering status without marking M4 passed.
- `docs/已有功能测试指令库.md`: add copyable PowerShell baseline checks and evidence boundaries.
- `HANDOFF.md`: record files, commands, verified results, and M1/M4 limitations.
- `README.md`: update the current-state baseline row only if needed to avoid contradicting the other current-state documents.

---

### Task 1: Isolated input contracts and formal fail-closed gate

**Files:**
- Create: `baseline/requirements.txt`
- Create: `baseline/__init__.py`
- Create: `baseline/contracts.py`
- Create: `baseline/tests/__init__.py`
- Create: `baseline/tests/test_contracts.py`

**Interfaces:**
- Consumes: content JSONL, Gold JSONL, three UTF-8 ID files, split report JSON, M1 gate JSON, and `mode: Literal["formal", "synthetic"]`.
- Produces: `BaselineInputError`, `ContentPost`, `GoldRecord`, `SplitAssignments`, `InputBundle`, `load_input_bundle(...)`, and `sha256_file(path)`.

- [x] **Step 1: Add isolated dependencies and write failing gate tests**

Create `baseline/requirements.txt` with exactly:

```text
scikit-learn>=1.5,<2
pytest>=8,<9
jsonschema>=4.22,<5
```

Create tests that prove formal gate rejection happens before model import and that synthetic mode can use an explicitly synthetic passed fixture:

```python
import json
from pathlib import Path

import pytest

from baseline.contracts import BaselineInputError, load_input_bundle


def test_formal_mode_rejects_current_failed_m1_gate(tmp_path: Path):
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": False}), encoding="utf-8")
    with pytest.raises(BaselineInputError, match="M1 gate has not passed"):
        load_input_bundle(mode="formal", m1_gate_path=gate)


def test_formal_test_requires_explicit_confirmation(tmp_path: Path):
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": True}), encoding="utf-8")
    with pytest.raises(BaselineInputError, match="test evaluation requires"):
        load_input_bundle(
            mode="formal",
            m1_gate_path=gate,
            evaluation_split="test",
            confirm_test_evaluation=False,
        )
```

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_contracts.py -q
```

Expected: collection fails because `baseline.contracts` does not exist.

- [x] **Step 3: Implement dataclasses, loaders, hashes, and preflight validation**

Use these exact public shapes:

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

Mode = Literal["formal", "synthetic"]
SplitName = Literal["train", "dev", "test"]
LABELS = ("明广", "暗广", "非广")


class BaselineInputError(ValueError):
    """Privacy-safe input or governance failure raised before training."""


@dataclass(frozen=True)
class ContentPost:
    post_id: str
    blogger_id: str
    published_at: datetime | None
    text: str
    history_refs: tuple[str, ...]
    content_group_id: str | None


@dataclass(frozen=True)
class GoldRecord:
    post_id: str
    label: str


@dataclass(frozen=True)
class SplitAssignments:
    train: frozenset[str]
    dev: frozenset[str]
    test: frozenset[str]


@dataclass(frozen=True)
class InputBundle:
    mode: Mode
    posts: dict[str, ContentPost]
    gold: dict[str, GoldRecord]
    splits: SplitAssignments
    evaluation_split: SplitName
    confirm_test_evaluation: bool
    input_hashes: dict[str, str]
```

`load_input_bundle` must validate the M1/test guard first, then require the remaining paths. In formal mode reject `passed != True`; in synthetic mode require fixture metadata `dataset_kind == "synthetic_fixture"`. JSONL loading must reject non-object rows, duplicate `post_id`, invalid labels, duplicate split IDs, split overlap, missing/extra Gold coverage, missing leakage fields, nonzero leakage, and a split without all three labels. Error strings may include field names and aggregate counts but not values of text, URLs, creator IDs, annotators, or post ID lists.

- [x] **Step 4: Add join, split, and label failure tests**

Add parametrized tests covering:

```python
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_content", "duplicate content post_id"),
        ("invalid_gold_label", "invalid formal Gold label"),
        ("missing_gold_content", "Gold/content coverage mismatch"),
        ("overlapping_splits", "split IDs overlap"),
        ("missing_split_id", "split/Gold coverage mismatch"),
        ("nonzero_creator_leakage", "split leakage check failed"),
        ("missing_near_duplicate_evidence", "split leakage evidence is incomplete"),
        ("split_missing_class", "each split must contain all three labels"),
    ],
)
def test_input_contracts_fail_closed(fixture_paths, mutation, message):
    fixture_paths.apply(mutation)
    with pytest.raises(BaselineInputError, match=message):
        load_input_bundle(**fixture_paths.kwargs(mode="formal"))
```

Implement `fixture_paths` as a local test helper that writes only synthetic, anonymous records to `tmp_path`.

- [x] **Step 5: Run contracts tests and verify GREEN**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_contracts.py -q
```

Expected: all contract tests pass without importing sklearn.

- [x] **Step 6: Commit Task 1**

```powershell
git add baseline\requirements.txt baseline\__init__.py baseline\contracts.py baseline\tests\__init__.py baseline\tests\test_contracts.py
git commit -m "feat: add history baseline input gate"
```

---

### Task 2: Leakage-safe shared cohort and exact history pooling

**Files:**
- Create: `baseline/features.py`
- Create: `baseline/tests/test_features.py`
- Modify: `baseline/contracts.py`
- Modify: `baseline/__init__.py`

**Interfaces:**
- Consumes: `InputBundle`, `ContentPost`, fixed `minimum_history=3`, and fixed `ema_alpha=0.5`.
- Produces: `FEATURE_VERSION`, `WEIGHT_DIMENSIONS`, `FeatureRow`, `Cohort`, `compute_keyword_weights(text)`, `pool_history(rows, method, alpha)`, `build_common_cohort(bundle)`, and `method_vector(sample, method)`.

- [x] **Step 1: Write failing exact-value feature and pooling tests**

Use a three-history fixture with vectors `(0.1, 0.2)`, `(0.3, 0.4)`, `(0.5, 0.8)` and assert:

```python
def test_pooling_exact_values():
    rows = _rows((0.1, 0.2), (0.3, 0.4), (0.5, 0.8))
    assert pool_history(rows, method="mean") == pytest.approx((0.3, 0.4666666667))
    assert pool_history(rows, method="max") == pytest.approx((0.5, 0.8))
    assert pool_history(rows, method="ema", alpha=0.5) == pytest.approx((0.35, 0.55))
```

Add keyword parity assertions for the text `"品牌赞助，限时优惠，点击链接购买，今天分享体验"` against `implicit-ad-agent/impad/tools/keywords.py` expected values and fixed dimension order.

- [x] **Step 2: Write failing leakage and shared-cohort tests**

Cover each invariant separately:

```python
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_ref", "history reference is missing"),
        ("cross_creator", "history creator mismatch"),
        ("self_ref", "history self-reference"),
        ("equal_time", "history timestamp is not earlier"),
        ("future_time", "history timestamp is not earlier"),
        ("duplicate_ref", "duplicate history reference"),
        ("naive_time", "timezone-aware timestamp required"),
    ],
)
def test_history_integrity_aborts_entire_run(bundle, mutation, message):
    bundle.apply(mutation)
    with pytest.raises(BaselineInputError, match=message):
        build_common_cohort(bundle.value)
```

Also assert that a missing target timestamp and one/two valid history rows produce `target_timestamp_unavailable` and `history_insufficient` exclusion counts, while every method receives identical train/evaluation target IDs.

- [x] **Step 3: Run focused feature tests and verify RED**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_features.py -q
```

Expected: collection fails because `baseline.features` does not exist.

- [x] **Step 4: Implement pinned keyword features and pooling**

Define:

```python
FEATURE_VERSION = "keyword_weights_v1"
WEIGHT_DIMENSIONS = (
    "promotion_words",
    "price_mentions",
    "urgency_expressions",
    "brand_mentions",
    "action_words",
    "natural_expression",
)


def compute_keyword_weights(text: str) -> tuple[float, ...]:
    hits = {
        name: sum(word in text for word in CATEGORY_WORDS[name])
        for name in WEIGHT_DIMENSIONS
    }
    return tuple(
        round(min(hits[name] / SATURATION[name], 1.0), 2)
        for name in WEIGHT_DIMENSIONS
    )
```

Copy `CATEGORY_WORDS` and `SATURATION` verbatim from `implicit-ad-agent/impad/tools/keywords.py` so the parity test locks the approved version. `pool_history` sorts rows by aware timestamp, validates identical finite vector lengths, computes arithmetic mean or per-feature max, and initializes EMA from the earliest row before applying `alpha * current + (1 - alpha) * previous`.

- [x] **Step 5: Implement integrity validation and shared cohort**

Use these stable shapes:

```python
@dataclass(frozen=True)
class FeatureRow:
    post_id: str
    blogger_id: str
    published_at: datetime
    values: tuple[float, ...]


@dataclass(frozen=True)
class PreparedSample:
    post_id: str
    split: str
    label: str
    target_values: tuple[float, ...]
    history_rows: tuple[FeatureRow, ...]


@dataclass(frozen=True)
class Cohort:
    samples: tuple[PreparedSample, ...]
    gold_count: int
    split_gold_counts: dict[str, int]
    split_cohort_counts: dict[str, int]
    exclusion_counts: dict[str, int]
```

Validate every referenced history item before deciding sufficiency. Any missing/cross-creator/self/duplicate/non-aware/not-earlier ref raises `BaselineInputError`; only a missing target timestamp or fewer than three valid rows increments an exclusion count. Sort `Cohort.samples` by split order then `post_id` for determinism.

After exclusions, verify train, dev, and test cohort subsets each still contain all three formal labels. Raise `BaselineInputError("each cohort split must contain all three labels")` before returning the cohort if any label is absent.

- [x] **Step 6: Run feature tests and verify GREEN**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_features.py -q
```

Expected: exact pooling, leakage rejection, exclusion, parity, and shared-cohort tests pass.

- [x] **Step 7: Commit Task 2**

```powershell
git add baseline\features.py baseline\contracts.py baseline\__init__.py baseline\tests\test_features.py
git commit -m "feat: build leakage-safe history cohort"
```

---

### Task 3: Fixed classifiers, metrics, and privacy-safe reporting

**Files:**
- Create: `baseline/runner.py`
- Create: `baseline/reporting.py`
- Create: `baseline/tests/test_runner.py`
- Modify: `baseline/__init__.py`

**Interfaces:**
- Consumes: `Cohort`, `InputBundle`, `method_vector(sample, method)`, and input hashes.
- Produces: `METHODS`, `ClassifierConfig`, `MethodResult`, `run_baselines(bundle, cohort)`, `evaluate_predictions(...)`, `build_report(...)`, and `serialize_report(report)`.

- [x] **Step 1: Install isolated baseline dependencies**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pip install -r baseline\requirements.txt
```

Expected: scikit-learn and its dependencies install into the existing project venv without changing `implicit-ad-agent/pyproject.toml` or `implicit-ad-agent/requirements.txt`.

- [x] **Step 2: Write failing deterministic training and probability tests**

Create a synthetic `Cohort` with all three labels in train/dev and assert:

```python
def test_four_methods_are_deterministic_and_share_sample_counts(cohort, bundle):
    first = run_baselines(bundle, cohort)
    second = run_baselines(bundle, cohort)
    assert first == second
    assert tuple(first) == ("single_post", "history_mean", "history_max", "history_ema")
    assert {result.train_count for result in first.values()} == {cohort.split_cohort_counts["train"]}
    assert {result.evaluation_count for result in first.values()} == {cohort.split_cohort_counts["dev"]}


def test_dark_ad_probability_uses_named_class_mapping(cohort, bundle):
    results = run_baselines(bundle, cohort)
    for result in results.values():
        assert result.class_order == ("明广", "暗广", "非广")
        assert 0.0 <= result.dark_ad_brier <= 1.0
        assert 0.0 <= result.dark_ad_auprc <= 1.0


def test_method_results_expose_aggregate_metrics_only(cohort, bundle):
    results = run_baselines(bundle, cohort)
    for result in results.values():
        public_fields = vars(result)
        assert "predictions" not in public_fields
        assert not any(field.endswith("_id") for field in public_fields)
        assert set(public_fields) == {
            "method", "class_order", "train_count", "evaluation_count",
            "macro_f1", "dark_ad_precision", "dark_ad_recall", "dark_ad_f1",
            "dark_ad_auprc", "dark_ad_brier", "ece", "confusion_counts",
            "delta_vs_single_post",
        }


# `test_evaluate_predictions_maps_named_probability_column` additionally
# asserts aggregate Brier=0.02 and AUPRC=1.0; no per-sample scores, predictions,
# or IDs are exposed through MethodResult.
```

- [x] **Step 3: Run runner tests and verify RED**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_runner.py -q
```

Expected: collection fails because `baseline.runner` and `baseline.reporting` do not exist.

- [x] **Step 4: Implement fixed sklearn pipelines**

Use lazy imports inside `run_baselines` and convert import failures to a privacy-safe `BaselineInputError`:

```python
METHODS = ("single_post", "history_mean", "history_max", "history_ema")


def _new_pipeline():
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise BaselineInputError(
            "scikit-learn is required; install baseline/requirements.txt"
        ) from exc
    return Pipeline([
        ("scale", StandardScaler()),
        ("classifier", LogisticRegression(
            solver="lbfgs",
            C=1.0,
            max_iter=1000,
            random_state=0,
            class_weight=None,
        )),
    ])
```

For each method, build train/evaluation arrays from the same cohort IDs, fit a fresh pipeline, obtain `predict` and `predict_proba`, and reorder probability columns by the fixed public label tuple instead of relying on sklearn lexical order. Keep predictions only in memory; `MethodResult` exposes aggregate metrics and counts, not IDs or row predictions.

- [x] **Step 5: Implement exact metrics and deltas**

Compute with sklearn:

```python
macro_f1 = f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)
dark_true = [label == "暗广" for label in y_true]
dark_pred = [label == "暗广" for label in y_pred]
dark_precision, dark_recall, dark_f1, _ = precision_recall_fscore_support(
    dark_true, dark_pred, average="binary", zero_division=0
)
dark_auprc = average_precision_score(dark_true, dark_scores)
dark_brier = brier_score_loss(dark_true, dark_scores)
```

Implement ten-bin ECE using `[lower, upper)` intervals and include 1.0 in the last bin. Build a fixed 3x3 confusion mapping in public label order. For each history method subtract the `single_post` point estimate for Macro-F1 and dark-ad F1/AUPRC; do not calculate p-values or intervals.

- [x] **Step 6: Write report privacy and determinism tests**

Assert the serialized JSON contains required versions/hashes/parameters/aggregate metrics, differs only in `generated_at` across runs, and contains none of the fixture raw text, URLs, post IDs, creator IDs, annotator IDs, or in-memory prediction arrays.

- [x] **Step 7: Run runner/report tests and verify GREEN**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_runner.py -q
```

Expected: deterministic model, named-class mapping, metric, delta, privacy, and serialization tests pass.

- [x] **Step 8: Commit Task 3**

```powershell
git add baseline\runner.py baseline\reporting.py baseline\__init__.py baseline\tests\test_runner.py
git commit -m "feat: evaluate merged history baselines"
```

---

### Task 4: Versioned synthetic fixtures and CLI end-to-end gate

**Files:**
- Create: `baseline/cli.py`
- Create: `baseline/tests/fixtures/synthetic_content.jsonl`
- Create: `baseline/tests/fixtures/synthetic_gold.jsonl`
- Create: `baseline/tests/fixtures/train_ids.txt`
- Create: `baseline/tests/fixtures/dev_ids.txt`
- Create: `baseline/tests/fixtures/test_ids.txt`
- Create: `baseline/tests/fixtures/synthetic_split_report.json`
- Create: `baseline/tests/fixtures/synthetic_gate.json`
- Create: `baseline/tests/fixtures/fixture_metadata.json`
- Create: `baseline/tests/test_cli.py`
- Create: `baseline/README.md`

**Interfaces:**
- Consumes: CLI argv and the Task 1-3 public interfaces.
- Produces: `python -m baseline.cli synthetic ...`, `python -m baseline.cli formal ...`, atomic UTF-8 JSON report files, exit code 0 on success, and exit code 2 on expected input/gate failure.

- [x] **Step 1: Create versioned anonymous synthetic fixtures**

Create nine labeled target posts: one `明广`, one `暗广`, and one `非广` in each of train/dev/test. Give every target a unique fixture creator and exactly three earlier same-creator history posts. Use IDs with `fixture_` prefixes, aware UTC timestamps, no URL/media/identity fields, and synthetic texts that exercise promotion, price, urgency, brand, action, and natural dimensions. Gold rows contain only `post_id`, `label`, two distinct human fixture annotators, and `adjudicated` metadata. The split report contains all four leakage counts as integer zero plus `near_duplicate_check_status="passed"`; the gate contains `{"gate":"M1","passed":true,"dataset_kind":"synthetic_fixture"}`; metadata contains `{"fixture_version":"merged-history-synthetic-v1","dataset_kind":"synthetic_fixture"}`.

- [x] **Step 2: Write failing CLI tests**

Add subprocess-level tests:

```python
def test_synthetic_cli_runs_four_methods_and_marks_no_research_claim(tmp_path):
    output = tmp_path / "report.json"
    completed = _run_cli("synthetic", output=output)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "synthetic"
    assert report["research_claims_allowed"] is False
    assert tuple(report["methods"]) == (
        "single_post", "history_mean", "history_max", "history_ema"
    )


def test_formal_cli_rejects_current_repository_gate_before_training(tmp_path):
    completed = _run_formal_with_current_gate(output=tmp_path / "report.json")
    assert completed.returncode == 2
    assert "M1 gate has not passed" in completed.stderr
    assert not (tmp_path / "report.json").exists()
```

Add a formal-test test that fails without `--confirm-test-evaluation` and passes the guard when the flag is present with synthetic copies of otherwise formal-valid fixtures.

- [x] **Step 3: Run CLI tests and verify RED**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests\test_cli.py -q
```

Expected: subprocess import fails because `baseline.cli` does not exist.

- [x] **Step 4: Implement CLI and atomic report write**

Use subcommands with identical input arguments except synthetic metadata and formal gate semantics. Parse paths with `Path`, call `load_input_bundle`, `build_common_cohort`, `run_baselines`, and `build_report`, write to `output.with_suffix(output.suffix + ".tmp")`, then replace the final output only after successful UTF-8 serialization. Catch `BaselineInputError`, print `baseline blocked: <aggregate reason>` to stderr, remove no existing output, and return 2. Unexpected exceptions remain uncaught for a test-visible traceback.

- [x] **Step 5: Write baseline README with exact commands and boundaries**

Document these commands:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pip install -r baseline\requirements.txt
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests -q
.\implicit-ad-agent\.venv\Scripts\python.exe -m baseline.cli synthetic --content baseline\tests\fixtures\synthetic_content.jsonl --gold baseline\tests\fixtures\synthetic_gold.jsonl --train-ids baseline\tests\fixtures\train_ids.txt --dev-ids baseline\tests\fixtures\dev_ids.txt --test-ids baseline\tests\fixtures\test_ids.txt --split-report baseline\tests\fixtures\synthetic_split_report.json --m1-gate baseline\tests\fixtures\synthetic_gate.json --fixture-metadata baseline\tests\fixtures\fixture_metadata.json --output baseline\synthetic_report.json
```

State that the generated file is an engineering artifact, is ignored or manually removed after inspection, and cannot support paper claims. Include a formal command template using named paths only after M1 passes; do not include current private data paths.

- [x] **Step 6: Run the CLI end to end and inspect aggregate-only output**

Run the synthetic command above, parse it with PowerShell `ConvertFrom-Json`, assert four methods and `research_claims_allowed -eq $false`, then check that fixture raw text and `fixture_creator_` do not appear in the report.

- [x] **Step 7: Run all baseline tests and verify GREEN**

Run:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests -q
```

Expected: all contracts, features, runner, reporting, and CLI tests pass.

- [x] **Step 8: Commit Task 4**

```powershell
git add baseline\README.md baseline\cli.py baseline\tests\fixtures baseline\tests\test_cli.py
git commit -m "feat: add history baseline CLI fixture"
```

---

### Task 5: Synchronize current-state documentation

**Files:**
- Modify: `docs/隐性广告识别项目_说明书.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/已有功能测试指令库.md`
- Modify: `HANDOFF.md`
- Modify: `README.md` only if its current-state table still says the root paper baseline is wholly absent.

**Interfaces:**
- Consumes: verified Task 4 commands and exact observed test counts.
- Produces: one consistent statement: merged-history classification baseline engineering is implemented and synthetic-verified; M1, formal training/test metrics, CreatorShift gain, and M4 remain incomplete.

- [x] **Step 1: Record stale statements before editing**

Run:

```powershell
rg -n "论文基线|baseline/|简单历史|历史池化|CreatorShift|M4" README.md HANDOFF.md docs\隐性广告识别项目_说明书.md docs\隐性广告识别项目_分阶段计划表.md docs\已有功能测试指令库.md
```

Save the matching line numbers in the task notes; do not edit historical specs/plans other than checking off this implementation plan as tasks complete.

- [x] **Step 2: Update only current-state sections**

Use wording equivalent to:

```text
独立 baseline/ 已实现单帖与单帖+mean/max/EMA历史池化的固定Logistic Regression工程基线，具备M1/split fail-closed门、共同cohort、版本/哈希和隐私安全聚合报告；当前仅用合成fixture验收工程行为。正式Gold=0且M1未通过，因此尚无真实训练、论文指标、增益或M4验收。
```

In the test runbook add the exact dependency, baseline test, synthetic CLI, report checks, and current formal rejection commands verified in Task 4. Preserve old dated baseline counts inside historical specs/plans.

- [x] **Step 3: Validate documentation consistency**

Run:

```powershell
rg -n "baseline/.*待做|论文基线.*待做|正式Gold=0|research_claims_allowed|M4" README.md HANDOFF.md docs\隐性广告识别项目_说明书.md docs\隐性广告识别项目_分阶段计划表.md docs\已有功能测试指令库.md
git diff --check
```

Expected: no current-state document calls the entire root baseline absent; all formal-research limitations remain explicit; historical plan/spec snapshots remain unchanged.

- [x] **Step 4: Commit Task 5**

```powershell
git add README.md HANDOFF.md docs\隐性广告识别项目_说明书.md docs\隐性广告识别项目_分阶段计划表.md docs\已有功能测试指令库.md
git commit -m "docs: record merged history baseline gate"
```

---

### Task 6: Completion audit and full regression

**Files:**
- Modify: `docs/superpowers/plans/2026-08-08-merged-history-baseline.md` checkboxes and completion-audit corrections after evidence succeeds.

**Interfaces:**
- Consumes: all Task 1-5 artifacts.
- Produces: fresh completion evidence for every design acceptance item without changing user-owned deletions.

- [x] **Step 1: Run baseline package verification**

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe -m pytest baseline\tests -q
.\implicit-ad-agent\.venv\Scripts\python.exe -m compileall -q baseline
```

Expected: all baseline tests pass and compileall exits 0.

- [x] **Step 2: Re-run existing CreatorShift and default regressions**

```powershell
Set-Location implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests\creator_shift -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q impad tests
Set-Location ..
```

Expected: CreatorShift focused and full default suites pass with their freshly observed counts; do not replace observed results with historic counts.

- [x] **Step 3: Verify current M1 formal rejection and synthetic report boundary**

Run formal CLI with `data\reports\m1\m1_gate_report.json` and safe fixture paths for the remaining arguments. Expected: exit 2 with `M1 gate has not passed`, no output file, and no sklearn fitting warning. Run synthetic CLI and verify `research_claims_allowed=false`, four methods, aggregate counts, input hashes, fixed parameters, and absence of raw text/identity values.

- [x] **Step 4: Audit every explicit design acceptance criterion**

Create a temporary checklist mapping design Section 12 items 1-10 to a test name or command output. Treat a missing mapping as incomplete and add the narrowest missing test before proceeding.

- [x] **Step 5: Check diff scope and preserve user changes**

```powershell
git status --short
git diff --check
git diff --stat HEAD~5..HEAD
```

Expected: task files are limited to `baseline/`, approved current-state docs, this plan/spec, and intentional commits. The four pre-existing deleted files remain deleted and unstaged/uncommitted by this task.

- [x] **Step 6: Run an independent Luna completion review**

Ask `luna_worker` to compare the approved design, this plan, current diff, test output, and reports requirement-by-requirement. Fix every verified gap using a failing test first, then rerun the affected focused and full checks.

- [x] **Step 7: Commit the checked plan and final corrections**

```powershell
git add docs\superpowers\plans\2026-08-08-merged-history-baseline.md
git commit -m "docs: close merged history baseline plan"
```

Do not mark M1 or M4 complete. Engineering completion means the isolated baseline package, synthetic verification, and formal fail-closed boundary are all proven by fresh evidence.

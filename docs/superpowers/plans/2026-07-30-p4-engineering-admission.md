# P4 Engineering Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing leakage-safe CreatorShift kernel to the Agent evidence chain and add version-bound synthetic benchmark, bootstrap, and risk-coverage reports without making real-data claims.

**Architecture:** Add a dedicated deterministic CreatorShift graph node rather than changing the seven-tool registry. Reuse the existing keyword feature engine and CreatorShift kernel, add neutral supplemental evidence, and keep the current Judge label logic unchanged. Add two offline P4 report paths: a mean/max/EMA runtime benchmark and an explicit pre-abstention calibration fixture.

**Tech Stack:** Python 3.10+, Pydantic 2, LangGraph, pytest, standard library, PowerShell.

## Global Constraints

- Default tests are zero-key and zero-network.
- CreatorShift only reads same-creator history with `published_at < target_time`.
- Missing or insufficient history is not converted to a zero score.
- CreatorShift evidence is neutral and cannot change Judge label or confidence in this package.
- The seven registered detection tools and their MCP contract remain unchanged.
- Synthetic fixtures prove engineering behavior only; they do not prove real accuracy, calibration, CreatorShift gain, M3, or M4.
- Every production-code change follows an observed RED test before implementation.
- Run verification commands separately so a failed check cannot be hidden by a later command.

---

### Task 1: Runtime CreatorShift assessment contract

**Files:**
- Modify: `implicit-ad-agent/impad/contracts/verdict.py`
- Create: `implicit-ad-agent/impad/creator_shift/runtime.py`
- Modify: `implicit-ad-agent/impad/creator_shift/__init__.py`
- Test: `implicit-ad-agent/tests/creator_shift/test_runtime.py`

**Interfaces:**
- Consumes: `PostRecord`, `compute_keyword_weights(text)`, `CreatorHistoryView`, `pool_history()`, and `calculate_shift()`.
- Produces: `CreatorShiftSummary`, `assess_post_creator_shift(post, method="ema", minimum_history=3, alpha=0.5) -> CreatorShiftSummary`, and `creator_shift_evidence(summary) -> EvidenceItem | None`.

- [ ] **Step 1: Write failing runtime tests**

Add tests that construct normalized `PostRecord` objects and assert:

```python
summary = assess_post_creator_shift(post)
assert summary.status == "sufficient"
assert summary.pooling_method == "ema"
assert summary.history_count == 3
assert summary.shift_score is not None
assert creator_shift_evidence(summary).polarity == "neutral"
```

Also assert that missing target time, empty history, and fewer than three
timestamped history posts return `unavailable` or `insufficient` with
`shift_score is None` and no evidence item. Assert that missing-timestamp
history is excluded and recorded in `limitations`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
cd implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests\creator_shift\test_runtime.py -q
```

Expected: import failure for `CreatorShiftSummary` or
`assess_post_creator_shift`.

- [ ] **Step 3: Implement the structured summary and adapter**

Add this strict report-facing contract to `contracts/verdict.py`:

```python
class CreatorShiftSummary(BaseModel):
    status: Literal["sufficient", "insufficient", "unavailable"]
    history_count: int = Field(ge=0)
    required_history: int = Field(ge=1)
    feature_version: str = "keyword_weights_v1"
    runtime_version: str = "creator_shift_runtime_v1"
    pooling_method: Literal["mean", "max", "ema"] | None = None
    shift_score: float | None = Field(default=None, ge=0, le=1)
    history_post_ids: list[str] = Field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    top_features: list[str] = Field(default_factory=list)
    feature_deltas: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
```

Add `creator_shift: CreatorShiftSummary | None = None` to `VerdictReport`.
Add a model validator so sufficient summaries require a score and pooling
method, while unavailable/insufficient summaries reject numeric scores.

In `creator_shift/runtime.py`, compute target/history keyword features, exclude
history with missing timestamps, build the validated history view, and return
an explicit nonnumeric state before pooling when history is not sufficient.
When sufficient, convert the domain result into `CreatorShiftSummary`.

`creator_shift_evidence()` returns `None` unless the summary is sufficient.
For sufficient summaries return one `EvidenceItem` with:

```python
kind="creator_shift"
source="creator.history"
tool_name="creator_shift_baseline"
tool_version=summary.runtime_version
polarity="neutral"
source_type="history"
producer="agent:creator_shift"
metadata=summary.model_dump(mode="json")
```

Use a SHA-256 digest of the canonical summary JSON in the evidence ID.

- [ ] **Step 4: Verify GREEN**

Run the runtime test and existing CreatorShift tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\creator_shift -q
```

Expected: all CreatorShift tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- implicit-ad-agent/impad/contracts/verdict.py implicit-ad-agent/impad/creator_shift implicit-ad-agent/tests/creator_shift/test_runtime.py
git diff --cached --check
git commit -m "feat: add runtime CreatorShift assessment"
```

---

### Task 2: Dedicated CreatorShift graph node and report integration

**Files:**
- Create: `implicit-ad-agent/impad/agents/creator_shift_agent.py`
- Modify: `implicit-ad-agent/impad/agents/__init__.py`
- Modify: `implicit-ad-agent/impad/agents/supervisor.py`
- Modify: `implicit-ad-agent/impad/graph.py`
- Modify: `implicit-ad-agent/impad/state.py`
- Modify: `implicit-ad-agent/impad/orchestration/evidence_adapters.py`
- Modify: `implicit-ad-agent/impad/orchestration/judgment.py`
- Modify: `implicit-ad-agent/impad/agents/judge.py`
- Modify: `implicit-ad-agent/impad/services/reporting.py`
- Test: `implicit-ad-agent/tests/creator_shift/test_graph_integration.py`

**Interfaces:**
- Consumes: Task 1 `assess_post_creator_shift()` and
  `creator_shift_evidence()`.
- Produces: `creator_shift_agent(state)`, state keys
  `creator_shift_summary` and `supplemental_evidence`, and persisted
  `VerdictReport.creator_shift`.

- [ ] **Step 1: Write failing graph integration tests**

Use one synthetic manual post with three timestamped historical posts. Assert:

```python
out = graph.invoke({"post": payload})
assert out["creator_shift_summary"].status == "sufficient"
items = [
    item for item in out["evidence_bundle"].items
    if item.kind == "creator_shift"
]
assert len(items) == 1
assert items[0].polarity == "neutral"
assert out["verdict_report"].creator_shift == out["creator_shift_summary"]
assert out["verdict_report"].creator_shift_evidence_ids == [
    items[0].evidence_id
]
```

Run the same post without history and assert `unavailable` plus zero
CreatorShift evidence items. Run a paired classification input with and
without valid history and assert identical label, confidence, commercial
intent, and disclosure.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\creator_shift\test_graph_integration.py -q
```

Expected: missing state key or graph node.

- [ ] **Step 3: Add supplemental evidence assembly**

Change the evidence builder signature to:

```python
def build_evidence_bundle(
    post: PostRecord,
    results: list[ToolResult],
    *,
    supplemental_items: list[EvidenceItem] | None = None,
) -> EvidenceBundle:
```

Append supplemental items after tool-derived items, keep deterministic order,
and include their IDs in modality coverage. Existing two-argument callers
must continue to work.

- [ ] **Step 4: Add the dedicated graph node**

`creator_shift_agent()` evaluates the normalized `post_record`, builds zero or
one supplemental evidence item, rebuilds the current bundle, and removes
`creator_shift` from the route plan.

The Supervisor appends `creator_shift` after eligible tool groups for every
run so unavailable status remains explicit. The graph registers the node and
route. `AdCheckState` receives typed keys for the summary and supplemental
items.

- [ ] **Step 5: Persist summary without changing classification**

Extend `build_verdict_report()` with keyword-only
`creator_shift: CreatorShiftSummary | None = None`. Set
`creator_shift_evidence_ids` from bundle items whose kind is
`creator_shift`. Do not reference the shift score in intent, adequacy,
confidence, or label selection.

The Judge passes both supplemental items and the summary, and records
`creator_shift_runtime_v1` in `RunMetadata.model_versions`.

Add a `## CreatorShift` section to readable reports. Render status, observed
history, score/method/top features when sufficient, and limitations otherwise.

- [ ] **Step 6: Verify GREEN and graph regressions**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\creator_shift\test_graph_integration.py tests\test_graph_evidence_flow.py tests\orchestration\test_judgment.py tests\services\test_analysis_service.py -q
```

Expected: all selected tests pass and paired labels remain identical.

- [ ] **Step 7: Commit Task 2**

```powershell
git add -- implicit-ad-agent/impad/agents implicit-ad-agent/impad/graph.py implicit-ad-agent/impad/state.py implicit-ad-agent/impad/orchestration/evidence_adapters.py implicit-ad-agent/impad/orchestration/judgment.py implicit-ad-agent/impad/services/reporting.py implicit-ad-agent/tests/creator_shift/test_graph_integration.py
git diff --cached --check
git commit -m "feat: connect CreatorShift to the evidence graph"
```

---

### Task 3: Version-bound CreatorShift engineering benchmark

**Files:**
- Create: `implicit-ad-agent/impad/creator_shift/benchmark.py`
- Modify: `implicit-ad-agent/impad/creator_shift/__init__.py`
- Create: `implicit-ad-agent/tests/fixtures/creator_shift_eval_v1.json`
- Create: `implicit-ad-agent/tests/creator_shift/test_benchmark.py`
- Create: `implicit-ad-agent/scripts/evaluate_p4.py`
- Create: `implicit-ad-agent/tests/scripts/test_evaluate_p4.py`
- Generate: `data/reports/p4/creator_shift_fixture.json`

**Interfaces:**
- Consumes: Task 1 runtime assessment.
- Produces: `CreatorShiftBenchmarkFixture`,
  `CreatorShiftBenchmarkReport`, `run_creator_shift_benchmark(fixture)`, and
  CLI command `evaluate_p4.py creator-shift`.

- [ ] **Step 1: Write failing benchmark tests**

The fixture model contains:

```python
class CreatorShiftBenchmarkFixture(BaseModel):
    benchmark_version: str
    feature_version: Literal["keyword_weights_v1"]
    posts: list[PostRecord]
```

Require unique target post IDs. Tests assert canonical SHA-256 fixture hash,
mean/max/EMA results for each case, explicit unavailable/insufficient cases,
stable case ordering, and version/config fields.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\creator_shift\test_benchmark.py -q
```

Expected: benchmark imports are missing.

- [ ] **Step 3: Implement the minimal benchmark**

Canonicalize the fixture with sorted-key compact JSON before hashing. Run
`assess_post_creator_shift()` for `("mean", "max", "ema")`. Report:

```python
benchmark_version
feature_version
runtime_version
fixture_sha256
generated_at
minimum_history
ema_alpha
methods
case_count
status_counts
cases
```

Each case records case ID, method, status, score, history count, top features,
and limitations. Do not add labels or accuracy fields.

- [ ] **Step 4: Add the versioned fixture and CLI**

Create four synthetic `PostRecord` cases:

1. sufficient low shift;
2. sufficient high shift;
3. insufficient history;
4. unavailable target time.

Add `creator-shift --fixture --output` to `evaluate_p4.py`. Bootstrap the
project root into `sys.path` exactly as `evaluate_p3.py` does. Write UTF-8
indented JSON and create the output parent directory.

- [ ] **Step 5: Verify CLI through a real subprocess**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\creator_shift\test_benchmark.py tests\scripts\test_evaluate_p4.py -q
```

The subprocess test must invoke the direct script path from a temporary
working directory and validate the produced JSON.

- [ ] **Step 6: Generate the report**

Run from `implicit-ad-agent`:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_p4.py creator-shift --fixture tests\fixtures\creator_shift_eval_v1.json --output ..\data\reports\p4\creator_shift_fixture.json
```

- [ ] **Step 7: Commit Task 3**

```powershell
git add -- implicit-ad-agent/impad/creator_shift implicit-ad-agent/scripts/evaluate_p4.py implicit-ad-agent/tests/creator_shift/test_benchmark.py implicit-ad-agent/tests/scripts/test_evaluate_p4.py implicit-ad-agent/tests/fixtures/creator_shift_eval_v1.json data/reports/p4/creator_shift_fixture.json
git diff --cached --check
git commit -m "feat: add versioned CreatorShift benchmark"
```

---

### Task 4: Bootstrap intervals and risk-coverage report

**Files:**
- Create: `implicit-ad-agent/impad/evaluation/selective.py`
- Create: `implicit-ad-agent/impad/evaluation/calibration_reporting.py`
- Modify: `implicit-ad-agent/impad/evaluation/__init__.py`
- Create: `implicit-ad-agent/tests/fixtures/calibration_eval_v1.json`
- Create: `implicit-ad-agent/tests/evaluation/test_selective.py`
- Create: `implicit-ad-agent/tests/evaluation/test_calibration_reporting.py`
- Modify: `implicit-ad-agent/scripts/evaluate_p4.py`
- Modify: `implicit-ad-agent/tests/scripts/test_evaluate_p4.py`
- Generate: `data/reports/p4/calibration_fixture.json`

**Interfaces:**
- Produces: `CalibrationPrediction`, `CalibrationEvaluationFixture`,
  `MetricInterval`, `RiskCoveragePoint`, `CalibrationEvaluationReport`,
  `bootstrap_classification_intervals()`, `risk_coverage_curve()`, and CLI
  command `evaluate_p4.py calibration`.

- [ ] **Step 1: Write failing selective-evaluation tests**

Use explicit pre-abstention predictions:

```python
CalibrationPrediction(
    sample_id="s1",
    true_label="暗广",
    predicted_label="暗广",
    decision_confidence=0.9,
    dark_ad_score=0.9,
)
```

Assert:

- duplicate IDs are rejected;
- confidence and dark-ad score are constrained to `[0, 1]`;
- risk-coverage points are ordered by increasing coverage;
- the first point retains the highest-confidence sample;
- the final point has coverage `1.0` and risk equal to full-set error rate;
- ties are resolved by sample ID;
- bootstrap output is byte-for-byte deterministic for the same seed;
- every interval has `lower <= upper` and all reported metric values remain
  inside `[0, 1]`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\evaluation\test_selective.py tests\evaluation\test_calibration_reporting.py -q
```

Expected: selective/calibration modules are missing.

- [ ] **Step 3: Implement risk-coverage and bootstrap**

`risk_coverage_curve()` sorts by
`(-decision_confidence, sample_id)` and emits one point for each retained
prefix:

```python
coverage = retained_count / total_count
risk = error_count / retained_count
```

`bootstrap_classification_intervals()` uses `random.Random(seed)` and
resamples with replacement. Report percentile intervals for:

- `macro_f1`;
- `dark_ad_f1`;
- `dark_ad_auprc`;
- `dark_ad_ece`;
- `dark_ad_brier`.

Use a deterministic linear percentile helper. Reject nonpositive resamples and
confidence levels outside `(0, 1)`.

- [ ] **Step 4: Build the versioned report**

Convert `CalibrationPrediction` values to existing
`ClassificationPrediction` values for base metrics. The report records:

```python
benchmark_version
generated_at
sample_count
bootstrap_resamples
bootstrap_seed
confidence_level
metrics
metric_intervals
risk_coverage
```

The fixture contains six synthetic samples with all three labels, at least two
errors, and unique confidence values.

- [ ] **Step 5: Extend and verify the CLI**

Add:

```text
evaluate_p4.py calibration
  --predictions PATH
  --output PATH
  --bootstrap-resamples 500
  --bootstrap-seed 20260730
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\evaluation tests\scripts\test_evaluate_p4.py -q
```

- [ ] **Step 6: Generate the calibration report**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_p4.py calibration --predictions tests\fixtures\calibration_eval_v1.json --output ..\data\reports\p4\calibration_fixture.json --bootstrap-resamples 500 --bootstrap-seed 20260730
```

- [ ] **Step 7: Commit Task 4**

```powershell
git add -- implicit-ad-agent/impad/evaluation implicit-ad-agent/scripts/evaluate_p4.py implicit-ad-agent/tests/evaluation implicit-ad-agent/tests/scripts/test_evaluate_p4.py implicit-ad-agent/tests/fixtures/calibration_eval_v1.json data/reports/p4/calibration_fixture.json
git diff --cached --check
git commit -m "feat: add P4 selective evaluation reports"
```

---

### Task 5: Documentation synchronization and completion gate

**Files:**
- Modify: `HANDOFF.md`
- Modify: `docs/已有功能测试指令库.md`
- Modify: `docs/隐性广告识别项目_分阶段计划表.md`
- Modify: `docs/隐性广告识别项目_说明书.md`
- Modify: `docs/superpowers/specs/2026-07-30-p4-engineering-admission-design.md`
- Modify: `docs/superpowers/plans/2026-07-30-p4-engineering-admission.md`

**Interfaces:**
- Consumes: verified implementation and generated report facts.
- Produces: factual handoff, copyable commands, explicit acceptance criteria,
  and unchanged M1/M4 boundaries.

- [ ] **Step 1: Update factual status**

Record:

- the dedicated CreatorShift node and neutral evidence rule;
- runtime feature/method/version and unavailable behavior;
- the two P4 report paths and fixture-only meaning;
- exact focused/full test counts from fresh output;
- the fact that learned CreatorShift, real calibration, final thresholds,
  real-data gain, and M4 remain incomplete.

- [ ] **Step 2: Add copyable test commands**

Add commands for:

- CreatorShift runtime/graph tests;
- P4 benchmark and calibration CLI;
- report inspection and safety scan;
- full default regression;
- both P1 validators.

For each command document expected artifacts, pass criteria, optional paths,
and unfinished research boundaries.

- [ ] **Step 3: Run the focused gate**

```powershell
cd implicit-ad-agent
.\.venv\Scripts\python.exe -m pytest tests\creator_shift tests\evaluation tests\scripts\test_evaluate_p4.py tests\test_graph_evidence_flow.py tests\services\test_analysis_service.py -q
```

- [ ] **Step 4: Run the full gate as separate commands**

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q impad tests scripts
.\.venv\Scripts\python.exe -m pytest -q
```

From the repository root:

```powershell
.\implicit-ad-agent\.venv\Scripts\python.exe scripts\data\validate_submission_assets.py
.\implicit-ad-agent\.venv\Scripts\python.exe data-tooling\validate_submission_assets.py
git diff --check
```

- [ ] **Step 5: Audit generated reports**

Parse both P4 reports and assert:

- expected benchmark versions;
- fixture hash length is 64;
- mean/max/EMA are present;
- insufficient/unavailable cases have no score;
- bootstrap configuration equals the CLI arguments;
- coverage is strictly increasing and ends at `1.0`;
- no source URL, creator ID, raw post text, annotator ID, secret, or API key
  fields are present.

- [ ] **Step 6: Review the complete diff**

Compare the implementation to every acceptance criterion in the design.
Inspect production code, tests, reports, HANDOFF, test library, and phase/spec
status. Fix every Critical or Important issue and rerun the affected gate.

- [ ] **Step 7: Commit documentation and final corrections**

```powershell
git add -- HANDOFF.md docs/已有功能测试指令库.md docs/隐性广告识别项目_分阶段计划表.md docs/隐性广告识别项目_说明书.md docs/superpowers/specs/2026-07-30-p4-engineering-admission-design.md docs/superpowers/plans/2026-07-30-p4-engineering-admission.md
git diff --cached --check
git commit -m "docs: record P4 engineering admission"
```

- [ ] **Step 8: Final repository audit**

```powershell
git status --short --branch
git log -10 --oneline
git diff --check
```

The work is complete only if the worktree is clean, all design requirements
have direct evidence, both required documents are synchronized, and formal
M1/M4 limitations remain explicit.

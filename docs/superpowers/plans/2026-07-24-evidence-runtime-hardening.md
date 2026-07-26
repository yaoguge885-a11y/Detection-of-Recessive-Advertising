# Evidence and Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the P1-independent evidence, execution-policy, duplicate-call, and run-tracing contracts.

**Architecture:** Extend current Pydantic contracts without breaking existing constructors. Keep tracing local and dependency-free. Let RestrictedFunctionCaller optionally consume a CapabilityPlan so planning limits are enforced at execution time.

**Tech Stack:** Python 3.10+, Pydantic 2, LangChain tools, pytest.

## Global Constraints

- Do not import P1 Schema, PostRecord, CaptureStatus, LangGraph, MCP, or RAG.
- Existing ToolResult and EvidenceItem construction must remain valid.
- Missing or skipped evidence must not become a negative EvidenceItem.
- Every production behavior requires a failing test first.

---

### Task 1: Rich evidence contracts

**Files:**
- Modify: `implicit-ad-agent/impad/contracts/evidence.py`
- Modify: `implicit-ad-agent/impad/contracts/__init__.py`
- Modify: `implicit-ad-agent/tests/contracts/test_evidence.py`

**Interfaces:**
- Produces: `EvidenceModalityCoverage`, `EvidenceConflict`, richer `EvidenceItem` and `EvidenceBundle`.

- [x] **Step 1: Add failing tests**

Add tests that:

```python
item = EvidenceItem(
    evidence_id="ev_1",
    kind="commercial_intent",
    source="post.text",
    tool_name="analyze_text_intent",
    tool_version="1.0",
    polarity="supports",
    strength=0.8,
    source_type="text",
    source_ref="post.text",
    producer="tool:analyze_text_intent",
    status="observed",
)
assert item.polarity == "supports"
```

Also verify:

- a conflict must reference at least two different existing evidence IDs;
- modality coverage may reference only existing evidence IDs;
- missing requirements serialize to JSON;
- the old `_item()` helper remains valid.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_evidence.py -q
```

Expected: failure because the new models/fields and reference validators do not exist.

- [x] **Step 3: Implement the contracts**

Add literal types:

```python
EvidencePolarity = Literal["supports", "contradicts", "neutral"]
EvidenceStatus = Literal["observed", "degraded", "conflicted"]
EvidenceSourceType = Literal["text", "image", "comment", "history", "metadata"]
CoverageStatus = Literal["covered", "partial", "missing", "not_applicable"]
```

Add:

```python
class EvidenceModalityCoverage(BaseModel):
    modality: EvidenceSourceType
    status: CoverageStatus
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[ToolLimitation] = Field(default_factory=list)


class EvidenceConflict(BaseModel):
    conflict_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)
```

Extend `EvidenceItem` with optional/defaulted fields and extend `EvidenceBundle` with `coverage`, `conflicts`, and `missing_requirements`. In the bundle validator, reject duplicate IDs and unknown references.

- [x] **Step 4: Verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts/test_evidence.py -q
```

Expected: all evidence tests pass.

---

### Task 2: Run events and trace aggregation

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/tracing.py`
- Modify: `implicit-ad-agent/impad/contracts/run.py`
- Modify: `implicit-ad-agent/impad/contracts/__init__.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_tracing.py`
- Modify: `implicit-ad-agent/tests/contracts/test_run.py`

**Interfaces:**
- Produces: `RunEvent`, `RunTrace`, `InMemoryTraceRecorder`.
- Consumes: `RunMetadata.trace_ids`.

- [x] **Step 1: Add failing tests**

Test that:

```python
recorder = InMemoryTraceRecorder("run_1")
event = recorder.record(
    event_type="tool_started",
    stage="function_calling",
    call_id="call_1",
    tool_name="analyze_text_intent",
)
assert recorder.trace.events == [event]
assert event.run_id == "run_1"
```

Also verify monotonically ordered timestamps, JSON serialization, and that `RunMetadata` accepts `runtime_mode`, `planner_version`, token/cost fields, and trace IDs.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_tracing.py tests/contracts/test_run.py -q
```

Expected: import or field failures.

- [x] **Step 3: Implement minimal tracing**

Implement:

```python
class RunEvent(BaseModel):
    event_id: str
    run_id: str
    event_type: Literal[
        "function_call_proposed", "function_call_rejected",
        "tool_started", "tool_completed", "tool_failed", "run_stopped"
    ]
    stage: str
    timestamp: datetime
    call_id: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RunTrace(BaseModel):
    run_id: str
    events: list[RunEvent] = Field(default_factory=list)
```

`InMemoryTraceRecorder.record()` appends immutable event snapshots. Extend RunMetadata only with optional fields so existing code remains compatible.

- [x] **Step 4: Verify GREEN**

Run the same command and expect all tests to pass.

---

### Task 3: Duplicate-call guard and plan enforcement

**Files:**
- Modify: `implicit-ad-agent/impad/orchestration/tool_gateway.py`
- Modify: `implicit-ad-agent/impad/orchestration/function_calling.py`
- Modify: `implicit-ad-agent/tests/orchestration/test_function_calling.py`

**Interfaces:**
- Produces: public `input_fingerprint(arguments: dict) -> str`.
- Consumes: optional `CapabilityPlan` and `InMemoryTraceRecorder`.

- [x] **Step 1: Add failing tests**

Add real-tool tests proving:

1. identical normalized calls are rejected with `duplicate_call`;
2. the second duplicate is not added to `tool_results`;
3. `CapabilityPlan.call_budget` overrides the default policy limit;
4. `CapabilityPlan.tool_timeouts[name]` is copied into RunContext;
5. proposed/rejected/completed/error events are recorded;
6. `max_total_seconds` limits the active call and stops later proposals;
7. proposed, executed and rejected counts are reported separately;
8. trace event IDs can be attached to matching `RunMetadata`.

- [x] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_function_calling.py -q
```

Expected: failures for duplicate execution and missing plan/trace arguments.

- [x] **Step 3: Implement minimal behavior**

- Rename `_input_fingerprint` to public `input_fingerprint`.
- Validate allowed tool arguments before calling the gateway.
- Track `(tool_name, fingerprint)` keys for successfully validated proposals.
- Reject repeats with `duplicate_call`.
- If a plan is supplied, restrict allowed names to `plan.available_tools`, use `plan.call_budget`, and apply `plan.tool_timeouts`.
- Apply the remaining total-time budget as an upper bound on the active tool timeout.
- Record separate proposed/executed/rejected counters.
- Preserve existing FunctionCallingResult fields and add backward-compatible counters.
- Add `attach_trace()` to copy ordered event IDs into matching RunMetadata.

- [x] **Step 4: Verify GREEN and regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration -q
.\.venv\Scripts\python.exe -m pytest tests/contracts -q
```

Expected: all orchestration and contract tests pass.

---

### Task 4: Module gate

- [x] **Step 1: Run full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 2: Compile and diff checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad tests
git diff --check -- implicit-ad-agent/impad implicit-ad-agent/tests
```

- [x] **Step 3: Mark every preceding checkbox complete only after its command passes**


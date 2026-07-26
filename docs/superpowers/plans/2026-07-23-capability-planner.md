# Deterministic Capability Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, auditable Capability Planner that converts `CapabilityContext` into an allowed-tool plan without reading P1 Schema or making an LLM call.

**Architecture:** Extract one shared eligibility function used by both `LocalToolGateway.list_tools()` and the planner so allowlist behavior cannot drift. The planner records available tools, explicit skip reasons, Function Calling definitions, call budget, per-tool timeouts, and parallel/serial execution eligibility. A future PostRecord adapter will only populate `CapabilityContext`; it will not change planner logic.

**Tech Stack:** Python 3.10+, Pydantic 2, pytest.

## Global Constraints

- Do not import P1 Schema, `PostRecord`, LangGraph State, or an LLM client.
- Missing modality and insufficient samples are skip reasons, never zero-valued evidence.
- Preserve registry order for deterministic plans and tests.
- Derive Function Calling definitions and timeout defaults from `ToolSpec`.
- `LocalToolGateway.list_tools()` and `CapabilityPlanner.plan()` must agree on available tool names.

---

### Task 1: Specify planner output and eligibility behavior

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/capability_planner.py`
- Modify: `implicit-ad-agent/impad/orchestration/tool_gateway.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_capability_planner.py`

- [x] **Step 1: Write failing tests**

```python
from impad.orchestration.capability_planner import (
    CapabilityPlanner,
    CapabilityPlanningPolicy,
)
from impad.orchestration.tool_gateway import CapabilityContext, LocalToolGateway


def test_text_only_plan_exposes_only_text_tools_with_explicit_skips():
    context = CapabilityContext(
        modalities=frozenset({"text"}),
        sample_counts={"text": 1},
    )
    plan = CapabilityPlanner().plan(context)
    assert plan.available_tools == [
        "analyze_text_intent",
        "sentiment_curve",
    ]
    skipped = {item.tool_name: item.reasons for item in plan.skipped_tools}
    assert "missing_modality:image" in skipped["ocr_extract"]
    assert "missing_modality:history" in skipped["topic_drift"]
    assert plan.call_budget == 8
    assert len(plan.function_definitions) == 2


def test_present_but_insufficient_comments_are_skipped_not_available():
    context = CapabilityContext(
        modalities=frozenset({"comments"}),
        sample_counts={"comments": 4},
    )
    plan = CapabilityPlanner().plan(context)
    skipped = {item.tool_name: item.reasons for item in plan.skipped_tools}
    assert "comment_anomaly" not in plan.available_tools
    assert "insufficient_samples:comments:4<5" in skipped["comment_anomaly"]


def test_full_context_exposes_all_seven_tools():
    context = CapabilityContext(
        modalities=frozenset({"text", "image", "comments", "history"}),
        sample_counts={"text": 1, "image": 1, "comments": 5, "history": 3},
    )
    plan = CapabilityPlanner().plan(context)
    assert len(plan.available_tools) == 7
    assert plan.skipped_tools == []


def test_empty_context_has_zero_call_budget():
    plan = CapabilityPlanner().plan(CapabilityContext())
    assert plan.available_tools == []
    assert plan.function_definitions == []
    assert plan.call_budget == 0


def test_policy_caps_calls_and_tool_timeouts():
    context = CapabilityContext(
        modalities=frozenset({"text", "image", "comments", "history"}),
        sample_counts={"text": 1, "image": 1, "comments": 5, "history": 3},
    )
    plan = CapabilityPlanner().plan(
        context,
        CapabilityPlanningPolicy(
            max_calls=3,
            max_tool_timeout_seconds=5,
        ),
    )
    assert plan.call_budget == 3
    assert all(value <= 5 for value in plan.tool_timeouts.values())


def test_gateway_and_planner_use_the_same_eligibility_rule():
    context = CapabilityContext(
        modalities=frozenset({"text", "comments"}),
        sample_counts={"text": 1, "comments": 5},
    )
    planned = CapabilityPlanner().plan(context).available_tools
    listed = [spec.name for spec in LocalToolGateway().list_tools(context)]
    assert planned == listed
```

- [x] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_capability_planner.py -q
```

Expected: import fails because `capability_planner.py` does not exist.

- [x] **Step 3: Implement shared eligibility reasons**

Add to `tool_gateway.py`:

```python
def tool_eligibility_issues(
    spec: ToolSpec,
    context: CapabilityContext,
) -> list[str]:
    issues = []
    if not spec.ready:
        issues.append("tool_not_ready")
    missing = sorted(spec.required_modalities - context.modalities)
    issues.extend(f"missing_modality:{item}" for item in missing)
    for kind, minimum in spec.minimum_samples.items():
        if kind not in context.modalities:
            continue
        observed = context.sample_counts.get(kind, 0)
        if observed < minimum:
            issues.append(
                f"insufficient_samples:{kind}:{observed}<{minimum}"
            )
    return issues
```

Refactor `LocalToolGateway.list_tools()` to include a spec only when this function returns an empty list.

- [x] **Step 4: Implement planner models and deterministic plan**

Create:

```python
class CapabilityPlanningPolicy(BaseModel):
    max_calls: int = Field(default=8, ge=1, le=64)
    max_tool_timeout_seconds: float | None = Field(default=None, gt=0)


class SkippedTool(BaseModel):
    tool_name: str
    reasons: list[str]


class CapabilityPlan(BaseModel):
    available_tools: list[str]
    skipped_tools: list[SkippedTool]
    function_definitions: list[dict]
    call_budget: int = Field(ge=0)
    tool_timeouts: dict[str, float]
    parallel_tools: list[str]
    serial_tools: list[str]
```

`CapabilityPlanner.plan()` iterates over `TOOL_SPECS_V1` in order, records reasons for ineligible tools, deep-copies eligible Function Calling definitions, caps each timeout with `max_tool_timeout_seconds` when present, and sets `call_budget` to `policy.max_calls` when at least one tool is available (otherwise `0`). This permits repeated per-image calls while retaining a hard run-level cap.

- [x] **Step 5: Run planner and existing gateway tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_capability_planner.py tests/orchestration/test_tool_gateway.py -q
```

Expected: all planner and gateway tests pass.

---

### Task 2: Regression gate

- [x] **Step 1: Run all orchestration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration -q
```

- [x] **Step 2: Run the full default suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Run compile and diff checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad
git diff --check
```

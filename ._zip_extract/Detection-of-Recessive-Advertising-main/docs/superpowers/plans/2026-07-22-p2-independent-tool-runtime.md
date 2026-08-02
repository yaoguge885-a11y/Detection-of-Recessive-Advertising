# P2 Independent Tool Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the P2.5 runtime metadata, seven-tool registry metadata, and local tool gateway without depending on or modifying any P1 Schema asset.

**Architecture:** Keep the seven existing LangChain tools and their scoring behavior unchanged. Extend their shared result envelope compatibly, derive a metadata-rich `ToolSpec` catalog around the existing tools, and put invocation concerns in a new `LocalToolGateway` boundary. Invalid arguments remain validation errors; execution failures and timeouts become structured `ToolResult(status="error")` values.

**Tech Stack:** Python 3.10+, Pydantic 2, LangChain structured tools, pytest.

## Global Constraints

- Do not merge or read runtime fields from P1 Schema.
- Preserve `TOOLS_V1` and `TOOL_READINESS` as backward-compatible derived exports.
- Preserve all seven tool implementations and their current score logic.
- Default tests must remain zero-key and zero-network.
- `vision_integration` remains opt-in.
- Every production behavior is implemented only after its failing test is observed.

---

### Task 1: Extend the shared ToolResult runtime envelope

**Files:**
- Modify: `implicit-ad-agent/impad/tools/contracts.py`
- Modify: `implicit-ad-agent/tests/test_tool_contracts.py`

**Interfaces:**
- Consumes: Existing `ToolResult` dictionaries returned by all seven tools.
- Produces: `ToolLimitation` and backward-compatible optional fields on `ToolResult`: `call_id`, `run_id`, `latency_ms`, `error_code`, `retryable`, `input_fingerprint`, and `limitations`.

- [x] **Step 1: Write failing contract tests**

```python
from pydantic import ValidationError
from impad.tools.contracts import ToolLimitation, ToolResult


def test_common_result_accepts_optional_runtime_metadata():
    result = ToolResult(
        tool_name="sample",
        status="error",
        call_id="call_1",
        run_id="run_1",
        latency_ms=12,
        error_code="tool_timeout",
        retryable=True,
        input_fingerprint="sha256:abc",
        limitations=[ToolLimitation(
            kind="evidence",
            code="tool_timeout",
            message="No evidence was produced before the deadline.",
        )],
    )
    assert result.limitations[0].kind == "evidence"


def test_common_result_rejects_negative_latency():
    with pytest.raises(ValidationError):
        ToolResult(tool_name="sample", status="error", latency_ms=-1)
```

- [x] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_contracts.py -q
```

Expected: collection fails because `ToolLimitation` does not exist.

- [x] **Step 3: Implement the minimal compatible fields**

```python
ToolLimitationKind = Literal["capture", "evidence"]


class ToolLimitation(BaseModel):
    kind: ToolLimitationKind
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    tool_version: str = "1.0"
    status: ToolStatus
    score: float | None = Field(default=None, ge=0, le=1)
    evidence: list[ToolEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    model_info: str | None = None
    call_id: str | None = None
    run_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    retryable: bool | None = None
    input_fingerprint: str | None = None
    limitations: list[ToolLimitation] = Field(default_factory=list)
```

- [x] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_contracts.py -q
```

Expected: all contract tests pass and old minimal `ToolResult` construction still works.

---

### Task 2: Replace the bare registry with metadata-rich ToolSpec entries

**Files:**
- Modify: `implicit-ad-agent/impad/tools/registry.py`
- Modify: `implicit-ad-agent/impad/tools/__init__.py`
- Modify: `implicit-ad-agent/tests/test_tool_registry.py`

**Interfaces:**
- Consumes: The same seven `StructuredTool` objects and their Pydantic argument schemas.
- Produces: `ToolSpec`, `TOOL_SPECS_V1`, `TOOL_SPEC_BY_NAME`, plus compatible `TOOLS_V1` and `TOOL_READINESS`.

- [x] **Step 1: Write failing registry metadata tests**

```python
from impad.tools.registry import TOOL_SPEC_BY_NAME, TOOL_SPECS_V1


def test_registry_exposes_complete_runtime_metadata():
    assert len(TOOL_SPECS_V1) == 7
    assert set(TOOL_SPEC_BY_NAME) == {spec.name for spec in TOOL_SPECS_V1}
    for spec in TOOL_SPECS_V1:
        assert spec.input_schema["type"] == "object"
        assert spec.default_timeout_seconds > 0
        assert spec.mcp_name.startswith("detection.")
        assert spec.function_calling["function"]["parameters"] == spec.input_schema
        assert spec.function_calling["function"]["name"] == spec.name


def test_registry_declares_real_minimum_samples():
    assert TOOL_SPEC_BY_NAME["topic_drift"].minimum_samples["history"] == 3
    assert TOOL_SPEC_BY_NAME["comment_anomaly"].minimum_samples["comments"] == 5
```

- [x] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py -q
```

Expected: import fails because `TOOL_SPECS_V1` does not exist.

- [x] **Step 3: Implement ToolSpec and derive compatibility exports**

Implement a Pydantic `ToolSpec` holding:

```python
name: str
description: str
tool: BaseTool
input_schema: dict[str, Any]
required_modalities: frozenset[Literal["text", "image", "comments", "history"]]
minimum_samples: dict[str, int]
default_timeout_seconds: float
allow_parallel: bool
function_calling: dict[str, Any]
mcp_name: str
ready: bool
version: str
```

Create one spec for each existing tool. Use the tools' actual Pydantic JSON schemas for both `input_schema` and Function Calling parameters. Derive:

```python
TOOLS_V1 = [spec.tool for spec in TOOL_SPECS_V1]
TOOL_SPEC_BY_NAME = {spec.name: spec for spec in TOOL_SPECS_V1}
TOOL_READINESS = {spec.name: spec.ready for spec in TOOL_SPECS_V1}
```

Declare meaningful minimums:

```python
topic_drift: {"text": 1, "history": 3}
comment_anomaly: {"comments": 5}
```

- [x] **Step 4: Run registry tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py tests/test_tool_contracts.py -q
```

Expected: registry metadata and all existing registry invocation tests pass.

---

### Task 3: Implement LocalToolGateway

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/impad/orchestration/tool_gateway.py`
- Create: `implicit-ad-agent/tests/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_tool_gateway.py`

**Interfaces:**
- Consumes: `ToolSpec`, `ToolResult`, tool call arguments, a `CapabilityContext`, and a `RunContext`.
- Produces: a `ToolGateway` protocol with
  `list_tools(self, context: CapabilityContext) -> list[ToolSpec]` and
  `call(self, name: str, arguments: dict, run: RunContext) -> ToolResult`.

- [x] **Step 1: Write failing gateway tests**

Cover these real behaviors:

```python
import time

import pytest
from langchain_core.tools import tool
from pydantic import BaseModel, Field, ValidationError

from impad.orchestration.tool_gateway import (
    CapabilityContext,
    LocalToolGateway,
    RunContext,
    UnknownToolError,
)
from impad.tools.contracts import ToolResult
from impad.tools.registry import ToolSpec


def _test_spec(registered_tool, *, timeout_seconds=1.0):
    schema = registered_tool.args_schema.model_json_schema()
    return ToolSpec(
        name=registered_tool.name,
        description=registered_tool.description,
        tool=registered_tool,
        input_schema=schema,
        required_modalities=frozenset(),
        minimum_samples={},
        default_timeout_seconds=timeout_seconds,
        allow_parallel=True,
        function_calling={
            "type": "function",
            "function": {
                "name": registered_tool.name,
                "description": registered_tool.description,
                "parameters": schema,
            },
        },
        mcp_name=f"detection.{registered_tool.name}",
        ready=True,
        version="1.0",
    )


def test_list_tools_filters_modalities_and_sample_minimums():
    gateway = LocalToolGateway()
    text_only = gateway.list_tools(CapabilityContext(
        modalities=frozenset({"text"}),
        sample_counts={"text": 1},
    ))
    names = {spec.name for spec in text_only}
    assert {"analyze_text_intent", "sentiment_curve"} <= names
    assert "topic_drift" not in names
    assert "comment_anomaly" not in names

    with_history = gateway.list_tools(CapabilityContext(
        modalities=frozenset({"text", "history"}),
        sample_counts={"text": 1, "history": 3},
    ))
    assert "topic_drift" in {spec.name for spec in with_history}


def test_call_enriches_real_tool_result_with_runtime_metadata():
    gateway = LocalToolGateway()
    run = RunContext(run_id="run_1", call_id="call_1")
    result = gateway.call(
        "analyze_text_intent",
        {"text": "限时抢购，立即下单"},
        run,
    )
    assert result.status == "degraded"
    assert result.run_id == "run_1"
    assert result.call_id == "call_1"
    assert result.latency_ms is not None and result.latency_ms >= 0
    assert result.input_fingerprint.startswith("sha256:")

    repeated = gateway.call(
        "analyze_text_intent",
        {"text": "限时抢购，立即下单"},
        RunContext(run_id="run_1", call_id="call_2"),
    )
    assert repeated.input_fingerprint == result.input_fingerprint


def test_call_rejects_invalid_arguments_before_execution():
    with pytest.raises(ValidationError):
        LocalToolGateway().call(
            "analyze_text_intent",
            {"text": ""},
            RunContext(run_id="run_invalid"),
        )


def test_call_rejects_unknown_tool_name():
    with pytest.raises(UnknownToolError):
        LocalToolGateway().call(
            "not_registered",
            {},
            RunContext(run_id="run_unknown"),
        )


class FailureInput(BaseModel):
    value: str = "x"


@tool(args_schema=FailureInput)
def failing_test_tool(value: str = "x") -> dict:
    """Raise a controlled execution failure."""
    raise RuntimeError("private failure detail")


def test_call_normalizes_tool_exception_to_error_result():
    gateway = LocalToolGateway(specs=[_test_spec(failing_test_tool)])
    result = gateway.call(
        "failing_test_tool",
        {},
        RunContext(run_id="run_failure"),
    )
    assert result.status == "error"
    assert result.error_code == "tool_execution_error"
    assert result.retryable is False
    assert "private failure detail" not in " ".join(result.warnings)


class SlowInput(BaseModel):
    delay: float = Field(gt=0)


@tool(args_schema=SlowInput)
def slow_test_tool(delay: float) -> dict:
    """Return after a controlled delay."""
    time.sleep(delay)
    return ToolResult(
        tool_name="slow_test_tool",
        status="ok",
    ).model_dump(mode="json")


def test_call_normalizes_timeout_to_retryable_error_result():
    gateway = LocalToolGateway(specs=[
        _test_spec(slow_test_tool, timeout_seconds=0.005),
    ])
    result = gateway.call(
        "slow_test_tool",
        {"delay": 0.05},
        RunContext(run_id="run_timeout"),
    )
    assert result.status == "error"
    assert result.error_code == "tool_timeout"
    assert result.retryable is True
    assert result.limitations[0].code == "tool_timeout"
```

The successful call must use the real `analyze_text_intent` tool. Exception and timeout tests may use small local `@tool` functions injected through explicit `ToolSpec` instances; assertions target gateway results, not mocks.

- [x] **Step 2: Run gateway tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_tool_gateway.py -q
```

Expected: import fails because `impad.orchestration.tool_gateway` does not exist.

- [x] **Step 3: Implement contexts and capability filtering**

```python
class CapabilityContext(BaseModel):
    modalities: frozenset[ToolModality] = frozenset()
    sample_counts: dict[str, int] = Field(default_factory=dict)


class RunContext(BaseModel):
    run_id: str = Field(min_length=1)
    call_id: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)
```

`list_tools()` must return only ready specs whose required modalities are present and whose declared minimum sample counts are satisfied.

- [x] **Step 4: Implement validation, local invocation, and metadata**

`call()` must:

1. Reject unknown or unavailable tools.
2. Validate arguments through the registered tool's real `args_schema`.
3. Hash canonical validated JSON into `sha256:<hex>`.
4. Invoke within the selected timeout.
5. Validate the tool output as `ToolResult`.
6. Set `run_id`, `call_id`, `latency_ms`, and `input_fingerprint`.
7. Convert execution exceptions to non-retryable error results.
8. Convert timeouts to retryable error results.

Use a daemon thread plus bounded `join()` so returning a timeout does not block while waiting for the timed-out function to finish.

- [x] **Step 5: Run gateway tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_tool_gateway.py -q
```

Expected: all gateway tests pass.

---

### Task 4: Regression and quality gate

**Files:**
- Verify only; do not alter tool scoring to force tests green.

- [x] **Step 1: Run all P1-independent targeted tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_contracts.py tests/test_tool_registry.py tests/orchestration/test_tool_gateway.py -q
```

- [x] **Step 2: Run the default full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all default tests pass and `vision_integration` remains skipped.

- [x] **Step 3: Check diff quality and scope**

```powershell
git diff --check
git status --short
```

Confirm that existing user-modified documentation is untouched and all production changes trace to this plan.

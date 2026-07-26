# Restricted Function Calling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a zero-key, provider-neutral Function Calling boundary that exposes only capability-allowed P2 tools, validates tool arguments, enforces call/retry budgets, records traces, and executes through `LocalToolGateway`.

**Architecture:** Normalize LangChain-style tool calls into `FunctionCallRequest`, obtain the allowlist from `ToolGateway.list_tools()`, and execute accepted calls through the gateway. The caller never selects labels and never invokes a tool outside the active `CapabilityContext`. Invalid requests become traceable rejections; structured tool errors remain results so later calls can continue.

**Tech Stack:** Python 3.10+, Pydantic 2, LangChain tool-call dictionaries, pytest.

## Global Constraints

- Do not depend on P1 Schema or `PostRecord`.
- Do not call any external LLM or network service in default tests.
- Do not bypass `ToolGateway` or invoke registry tools directly.
- Do not expose tools that fail the current modality and minimum-sample checks.
- Count every proposed call against `max_calls`.
- Permit at most `max_validation_retries` argument/allowlist corrections after the first rejection.
- A `ToolResult(status="error")` must not prevent later valid calls from running.

---

### Task 1: Define and test the restricted Function Calling boundary

**Files:**
- Create: `implicit-ad-agent/impad/orchestration/function_calling.py`
- Modify: `implicit-ad-agent/impad/orchestration/__init__.py`
- Create: `implicit-ad-agent/tests/orchestration/test_function_calling.py`

**Interfaces:**
- Consumes: LangChain-style calls shaped as `{"id": str, "name": str, "args": dict}`, `CapabilityContext`, `RunContext`, and `ToolGateway`.
- Produces: `FunctionCallingPolicy`, `FunctionCallTrace`, `FunctionCallingResult`, and `RestrictedFunctionCaller`.

- [x] **Step 1: Write failing tests for allowed tool exposure and real execution**

```python
from impad.orchestration.function_calling import (
    FunctionCallingPolicy,
    RestrictedFunctionCaller,
)
from impad.orchestration.tool_gateway import CapabilityContext, RunContext


def _text_context():
    return CapabilityContext(
        modalities=frozenset({"text"}),
        sample_counts={"text": 1},
    )


def test_available_functions_only_expose_capability_allowed_tools():
    definitions = RestrictedFunctionCaller().available_functions(_text_context())
    names = {item["function"]["name"] for item in definitions}
    assert {"analyze_text_intent", "sentiment_curve"} <= names
    assert "ocr_extract" not in names
    assert "topic_drift" not in names


def test_execute_runs_real_allowed_tool_and_records_trace():
    result = RestrictedFunctionCaller().execute(
        calls=[{
            "id": "call_1",
            "name": "analyze_text_intent",
            "args": {"text": "限时抢购，立即下单"},
        }],
        context=_text_context(),
        run=RunContext(run_id="run_fc"),
    )
    assert len(result.tool_results) == 1
    assert result.tool_results[0].call_id == "call_1"
    assert result.traces[0].status == "completed"
    assert result.stopped_reason is None
```

- [x] **Step 2: Write failing tests for rejection and bounded correction**

```python
def test_disallowed_tool_is_rejected_without_execution():
    result = RestrictedFunctionCaller().execute(
        calls=[{
            "id": "call_ocr",
            "name": "ocr_extract",
            "args": {"image_path": "not-used.jpg"},
        }],
        context=_text_context(),
        run=RunContext(run_id="run_disallowed"),
    )
    assert result.tool_results == []
    assert result.traces[0].status == "rejected"
    assert result.traces[0].error_code == "tool_not_allowed"


def test_one_invalid_argument_call_can_be_followed_by_a_correction():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_bad",
                "name": "analyze_text_intent",
                "args": {"text": ""},
            },
            {
                "id": "call_fixed",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作推广"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_retry"),
        policy=FunctionCallingPolicy(
            max_calls=3,
            max_validation_retries=1,
        ),
    )
    assert [trace.status for trace in result.traces] == [
        "rejected",
        "completed",
    ]
    assert result.tool_results[0].call_id == "call_fixed"


def test_validation_retry_budget_stops_before_third_call():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_bad_1",
                "name": "analyze_text_intent",
                "args": {"text": ""},
            },
            {
                "id": "call_bad_2",
                "name": "analyze_text_intent",
                "args": {"text": ""},
            },
            {
                "id": "call_not_run",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作推广"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_retry_limit"),
        policy=FunctionCallingPolicy(
            max_calls=3,
            max_validation_retries=1,
        ),
    )
    assert result.tool_results == []
    assert result.stopped_reason == "validation_retry_budget_exceeded"
    assert len(result.traces) == 2
```

- [x] **Step 3: Write failing tests for call budget and error continuation**

Use two small real LangChain test tools injected through `LocalToolGateway`: one raises, one returns `ToolResult(status="ok")`.

```python
from langchain_core.tools import tool
from pydantic import BaseModel

from impad.orchestration.tool_gateway import LocalToolGateway
from impad.tools.contracts import ToolResult
from impad.tools.registry import ToolSpec


class NoArgs(BaseModel):
    pass


@tool(args_schema=NoArgs)
def failing_fc_tool() -> dict:
    """Raise a controlled failure for caller continuation tests."""
    raise RuntimeError("controlled failure")


@tool(args_schema=NoArgs)
def successful_fc_tool() -> dict:
    """Return a successful shared result."""
    return ToolResult(
        tool_name="successful_fc_tool",
        status="ok",
    ).model_dump(mode="json")


def _fc_test_spec(registered_tool):
    schema = registered_tool.args_schema.model_json_schema()
    return ToolSpec(
        name=registered_tool.name,
        description=registered_tool.description,
        tool=registered_tool,
        input_schema=schema,
        required_modalities=frozenset(),
        minimum_samples={},
        default_timeout_seconds=1,
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


def _gateway_with_failing_and_success_tools():
    return LocalToolGateway(specs=[
        _fc_test_spec(failing_fc_tool),
        _fc_test_spec(successful_fc_tool),
    ])


def test_max_calls_limits_the_number_of_proposals_processed():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_1",
                "name": "analyze_text_intent",
                "args": {"text": "限时抢购"},
            },
            {
                "id": "call_2",
                "name": "sentiment_curve",
                "args": {"text": "限时抢购"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_budget"),
        policy=FunctionCallingPolicy(max_calls=1),
    )
    assert len(result.tool_results) == 1
    assert len(result.traces) == 1
    assert result.stopped_reason == "max_calls_reached"


def test_tool_error_does_not_prevent_later_calls():
    caller = RestrictedFunctionCaller(
        gateway=_gateway_with_failing_and_success_tools(),
    )
    result = caller.execute(
        calls=[
            {"id": "call_fail", "name": "failing_fc_tool", "args": {}},
            {"id": "call_ok", "name": "successful_fc_tool", "args": {}},
        ],
        context=CapabilityContext(),
        run=RunContext(run_id="run_continue"),
    )
    assert [item.status for item in result.tool_results] == ["error", "ok"]
    assert [trace.status for trace in result.traces] == ["error", "completed"]
```

- [x] **Step 4: Run tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_function_calling.py -q
```

Expected: collection fails because `impad.orchestration.function_calling` does not exist.

- [x] **Step 5: Implement normalized requests, policies, traces, and execution**

Implement these concrete fields:

```python
class FunctionCallRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)


class FunctionCallingPolicy(BaseModel):
    max_calls: int = Field(default=8, ge=1, le=64)
    max_validation_retries: int = Field(default=1, ge=0, le=8)


class FunctionCallTrace(BaseModel):
    call_id: str
    tool_name: str
    status: Literal["completed", "rejected", "error"]
    error_code: str | None = None
    result_status: ToolStatus | None = None


class FunctionCallingResult(BaseModel):
    tool_results: list[ToolResult] = Field(default_factory=list)
    traces: list[FunctionCallTrace] = Field(default_factory=list)
    stopped_reason: str | None = None
```

`RestrictedFunctionCaller.available_functions()` returns the `function_calling` definitions from `gateway.list_tools(context)`.

`execute()` must:

1. Normalize each input with `FunctionCallRequest.model_validate`.
2. Process no more than `policy.max_calls`.
3. Reject names outside the capability-derived allowlist.
4. Call the gateway with a per-request `call_id`.
5. Catch Pydantic argument validation errors as `invalid_arguments`.
6. Stop when validation rejections exceed `max_validation_retries`.
7. Keep structured tool errors and continue processing.
8. Set `max_calls_reached` only when proposals remain after the allowed count.

- [x] **Step 6: Run Function Calling tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration/test_function_calling.py -q
```

Expected: all Function Calling tests pass without keys or network.

---

### Task 2: Regression gate

- [x] **Step 1: Run orchestration tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/orchestration -q
```

- [x] **Step 2: Run the complete default suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

- [x] **Step 3: Run compile and scoped diff checks**

```powershell
.\.venv\Scripts\python.exe -m compileall -q impad
git diff --check
```

Confirm the change does not modify P1 data, existing seven-tool scoring logic, or unrelated user documentation.

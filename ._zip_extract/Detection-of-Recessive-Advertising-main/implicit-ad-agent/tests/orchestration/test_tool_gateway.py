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
    result = gateway.call(
        "analyze_text_intent",
        {"text": "限时抢购，立即下单"},
        RunContext(run_id="run_1", call_id="call_1"),
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

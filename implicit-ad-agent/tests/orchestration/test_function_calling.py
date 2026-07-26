import time

from langchain_core.tools import tool
from pydantic import BaseModel

from impad.orchestration.capability_planner import CapabilityPlan
from impad.orchestration.function_calling import (
    FunctionCallingPolicy,
    RestrictedFunctionCaller,
)
from impad.orchestration.tracing import InMemoryTraceRecorder
from impad.orchestration.tool_gateway import (
    CapabilityContext,
    LocalToolGateway,
    RunContext,
)
from impad.tools.contracts import ToolResult
from impad.tools.registry import ToolSpec


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
    assert all(
        item["function"]["parameters"]["additionalProperties"] is False
        for item in definitions
    )


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


def test_unknown_argument_is_rejected_instead_of_silently_dropped():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_bad",
                "name": "analyze_text_intent",
                "args": {
                    "text": "品牌合作推广",
                    "unexpected": "must be rejected",
                },
            }
        ],
        context=_text_context(),
        run=RunContext(run_id="run_unknown_arg"),
    )

    assert result.tool_results == []
    assert result.traces[0].status == "rejected"
    assert result.traces[0].error_code == "invalid_arguments"


def test_unknown_nested_argument_is_rejected():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_bad_nested",
                "name": "comment_anomaly",
                "args": {
                    "comments": [
                        {
                            "comment_id": f"comment_{index}",
                            "text": "普通评论",
                            "unexpected": "must be rejected",
                        }
                        for index in range(5)
                    ]
                },
            }
        ],
        context=CapabilityContext(
            modalities=frozenset({"comments"}),
            sample_counts={"comments": 5},
        ),
        run=RunContext(run_id="run_unknown_nested_arg"),
    )

    assert result.tool_results == []
    assert result.traces[0].error_code == "invalid_arguments"


def test_malformed_call_envelope_is_traced_and_does_not_abort_batch():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "name": "analyze_text_intent",
                "args": {"text": "缺少调用 ID"},
            },
            {
                "id": "call_fixed",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作推广"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_bad_envelope"),
        policy=FunctionCallingPolicy(max_validation_retries=1),
    )

    assert [trace.status for trace in result.traces] == [
        "rejected",
        "completed",
    ]
    assert result.traces[0].error_code == "invalid_call_request"
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


def test_duplicate_normalized_call_is_rejected_without_second_execution():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_1",
                "name": "analyze_text_intent",
                "args": {"text": "限时抢购"},
            },
            {
                "id": "call_2",
                "name": "analyze_text_intent",
                "args": {
                    "text": "限时抢购",
                    "comments": [],
                    "language": "zh",
                },
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_duplicate"),
    )

    assert len(result.tool_results) == 1
    assert [trace.status for trace in result.traces] == [
        "completed",
        "rejected",
    ]
    assert result.traces[1].error_code == "duplicate_call"


def _plan_for(*tool_names, call_budget=8, timeout=1.0):
    return CapabilityPlan(
        available_tools=list(tool_names),
        skipped_tools=[],
        function_definitions=[],
        call_budget=call_budget,
        tool_timeouts={name: timeout for name in tool_names},
        parallel_tools=list(tool_names),
        serial_tools=[],
    )


def test_capability_plan_call_budget_is_enforced():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_1",
                "name": "analyze_text_intent",
                "args": {"text": "限时抢购"},
            },
            {
                "id": "call_2",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_plan_budget"),
        plan=_plan_for("analyze_text_intent", call_budget=1),
    )

    assert len(result.tool_results) == 1
    assert result.stopped_reason == "max_calls_reached"


@tool(args_schema=NoArgs)
def slow_fc_tool() -> dict:
    """Sleep long enough for a plan timeout to interrupt the call."""
    time.sleep(0.05)
    return ToolResult(
        tool_name="slow_fc_tool",
        status="ok",
    ).model_dump(mode="json")


def test_capability_plan_tool_timeout_is_applied_to_run_context():
    caller = RestrictedFunctionCaller(
        gateway=LocalToolGateway(specs=[_fc_test_spec(slow_fc_tool)]),
    )
    result = caller.execute(
        calls=[{"id": "call_slow", "name": "slow_fc_tool", "args": {}}],
        context=CapabilityContext(),
        run=RunContext(run_id="run_plan_timeout"),
        plan=_plan_for("slow_fc_tool", timeout=0.005),
    )

    assert result.tool_results[0].status == "error"
    assert result.tool_results[0].error_code == "tool_timeout"


def test_function_calling_records_proposed_started_and_terminal_events():
    recorder = InMemoryTraceRecorder("run_trace")
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_ok",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作"},
            },
            {
                "id": "call_rejected",
                "name": "ocr_extract",
                "args": {"image_path": "not-used.jpg"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_trace"),
        recorder=recorder,
    )

    assert [event.event_type for event in recorder.trace.events] == [
        "function_call_proposed",
        "tool_started",
        "tool_completed",
        "function_call_proposed",
        "function_call_rejected",
    ]
    assert result.traces[1].error_code == "tool_not_allowed"


def test_result_counts_proposed_executed_and_rejected_calls_separately():
    result = RestrictedFunctionCaller().execute(
        calls=[
            {
                "id": "call_rejected",
                "name": "ocr_extract",
                "args": {"image_path": "not-used.jpg"},
            },
            {
                "id": "call_executed",
                "name": "analyze_text_intent",
                "args": {"text": "品牌合作"},
            },
        ],
        context=_text_context(),
        run=RunContext(run_id="run_counts"),
    )

    assert result.proposed_count == 2
    assert result.executed_count == 1
    assert result.rejected_count == 1


def test_total_time_budget_limits_current_timeout_and_stops_later_calls():
    caller = RestrictedFunctionCaller(
        gateway=LocalToolGateway(specs=[
            _fc_test_spec(slow_fc_tool),
            _fc_test_spec(successful_fc_tool),
        ]),
    )
    result = caller.execute(
        calls=[
            {"id": "call_slow", "name": "slow_fc_tool", "args": {}},
            {"id": "call_not_run", "name": "successful_fc_tool", "args": {}},
        ],
        context=CapabilityContext(),
        run=RunContext(run_id="run_total_budget"),
        policy=FunctionCallingPolicy(
            max_calls=2,
            max_total_seconds=0.005,
        ),
    )

    assert len(result.tool_results) == 1
    assert result.tool_results[0].error_code == "tool_timeout"
    assert result.stopped_reason == "total_time_budget_exceeded"
    assert result.proposed_count == 1
    assert result.executed_count == 1

"""Shared expert-node execution through restricted Function Calling."""
from __future__ import annotations

from collections.abc import Collection

from ..orchestration import (
    FunctionCallingResult,
    InMemoryTraceRecorder,
    RunContext,
    attach_trace,
    build_evidence_bundle,
    execute_post_tools,
)
from ..state import AdCheckState


def execute_agent_group(
    state: AdCheckState,
    *,
    agent_name: str,
    tool_names: Collection[str],
) -> AdCheckState:
    post = state["post_record"]
    plan = state["capability_plan"]
    metadata = state["run_metadata"]
    recorder = InMemoryTraceRecorder(metadata.run_id)
    consumed_calls = len(state.get("function_traces", []))
    remaining_calls = max(0, plan.call_budget - consumed_calls)
    if remaining_calls == 0:
        result = FunctionCallingResult(
            stopped_reason="max_calls_reached",
        )
    else:
        remaining_plan = plan.model_copy(
            update={"call_budget": remaining_calls}
        )
        result = execute_post_tools(
            post,
            remaining_plan,
            RunContext(run_id=metadata.run_id),
            tool_names=tool_names,
            recorder=recorder,
        )
    tool_results = [*state.get("tool_results", []), *result.tool_results]
    trace = recorder.snapshot()
    metadata = attach_trace(metadata, trace)
    bundle = build_evidence_bundle(post, tool_results)
    outputs = {
        **state.get("agent_outputs", {}),
        agent_name: {
            "tools": [item.tool_name for item in result.tool_results],
            "statuses": {
                item.tool_name: item.status
                for item in result.tool_results
            },
            "stopped_reason": result.stopped_reason,
        },
    }
    evidence = [
        *state.get("evidence", []),
        *(
            f"[{agent_name}] {item.tool_name}: {item.status}"
            for item in result.tool_results
        ),
    ]
    update: AdCheckState = {
        "tool_results": tool_results,
        "function_traces": [
            *state.get("function_traces", []),
            *result.traces,
        ],
        "run_events": [*state.get("run_events", []), *trace.events],
        "run_metadata": metadata,
        "evidence_bundle": bundle,
        "agent_outputs": outputs,
        "agent_votes": outputs,
        "evidence": evidence,
        "plan": [
            item
            for item in state.get("plan", [])
            if item != agent_name
        ],
    }
    text_result = next(
        (
            item
            for item in tool_results
            if item.tool_name == "analyze_text_intent"
        ),
        None,
    )
    if text_result is not None:
        weights = text_result.payload.get("keyword_weights")
        if isinstance(weights, dict):
            update["keyword_weights"] = weights
    return update

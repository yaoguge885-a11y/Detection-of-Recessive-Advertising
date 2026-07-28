"""Adapt PostRecord capabilities and fields to the seven stable tool schemas."""
from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Collection
from urllib.parse import urlparse

from ..contracts.post import HistoryPost, PostRecord
from ..tools.registry import TOOL_SPECS_V1
from .capability_planner import CapabilityPlan
from .function_calling import (
    FunctionCallingPolicy,
    FunctionCallingResult,
    RestrictedFunctionCaller,
)
from .tool_gateway import (
    CapabilityContext,
    RunContext,
    ToolGateway,
    validate_tool_arguments,
)
from .tracing import InMemoryTraceRecorder


def _is_local_file(ref: str | None) -> bool:
    if not ref:
        return False
    if urlparse(ref).scheme.lower() in {"http", "https"}:
        return False
    return Path(ref).is_file()


def _local_image(post: PostRecord) -> str | None:
    for item in post.media:
        if item.type == "image" and _is_local_file(item.ref):
            return item.ref
    return None


def _time_safe_history(post: PostRecord) -> list[HistoryPost]:
    if post.published_at is None:
        return []
    return [
        item
        for item in post.history
        if item.published_at is not None
        and item.published_at < post.published_at
    ]


def capability_context_from_post(post: PostRecord) -> CapabilityContext:
    """Derive executable modalities without treating logical refs as files."""

    modalities = set()
    sample_counts: dict[str, int] = {}
    if post.text.strip():
        modalities.add("text")
        sample_counts["text"] = 1
    local_images = [
        item
        for item in post.media
        if item.type == "image" and _is_local_file(item.ref)
    ]
    if local_images:
        modalities.add("image")
        sample_counts["image"] = len(local_images)
    if post.comments:
        modalities.add("comments")
        sample_counts["comments"] = len(post.comments)
    safe_history = _time_safe_history(post)
    if safe_history:
        modalities.add("history")
        sample_counts["history"] = len(safe_history)
    return CapabilityContext(
        modalities=frozenset(modalities),
        sample_counts=sample_counts,
    )


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _history_payload(history: list[HistoryPost]) -> list[dict]:
    return [
        {
            "post_id": item.post_id,
            "text": item.text,
            "published_at": _iso(item.published_at),
        }
        for item in history
    ]


def _arguments_for(post: PostRecord, tool_name: str) -> dict:
    image_path = _local_image(post)
    history = _history_payload(_time_safe_history(post))
    comments = [
        item.model_dump(mode="json", exclude_none=True)
        for item in post.comments
    ]
    if tool_name == "analyze_text_intent":
        return {
            "text": post.text,
            "comments": [item.text for item in post.comments],
        }
    if tool_name == "sentiment_curve":
        return {"text": post.text, "history": history}
    if tool_name == "ocr_extract":
        return {"image_path": image_path}
    if tool_name == "image_text_consistency":
        return {"text": post.text, "image_path": image_path}
    if tool_name == "detect_logo_product":
        return {"image_path": image_path}
    if tool_name == "topic_drift":
        return {
            "post_id": post.post_id,
            "text": post.text,
            "published_at": _iso(post.published_at),
            "history": history,
        }
    if tool_name == "comment_anomaly":
        return {"comments": comments}
    raise ValueError(f"No PostRecord argument adapter for tool: {tool_name}")


def function_calls_from_post(
    post: PostRecord,
    plan: CapabilityPlan,
    tool_names: Collection[str] | None = None,
) -> list[dict]:
    """Create validated provider-neutral calls in registry order."""

    allowed = set(plan.available_tools)
    if tool_names is not None:
        allowed &= set(tool_names)
    calls = []
    for spec in TOOL_SPECS_V1:
        if spec.name not in allowed:
            continue
        arguments = _arguments_for(post, spec.name)
        validated = validate_tool_arguments(
            spec.tool.args_schema,
            arguments,
        )
        calls.append({
            "id": f"call_{spec.name}",
            "name": spec.name,
            "args": validated.model_dump(mode="json"),
        })
    return calls


def execute_post_tools(
    post: PostRecord,
    plan: CapabilityPlan,
    run: RunContext,
    *,
    tool_names: Collection[str] | None = None,
    gateway: ToolGateway | None = None,
    recorder: InMemoryTraceRecorder | None = None,
    policy: FunctionCallingPolicy | None = None,
) -> FunctionCallingResult:
    """Execute adapted calls only through the restricted Function Caller."""

    context = capability_context_from_post(post)
    calls = function_calls_from_post(post, plan, tool_names=tool_names)
    return RestrictedFunctionCaller(gateway=gateway).execute(
        calls=calls,
        context=context,
        run=run,
        policy=policy,
        plan=plan,
        recorder=recorder,
    )


def execute_post_tools_parallel(
    post: PostRecord,
    plan: CapabilityPlan,
    run: RunContext,
    *,
    tool_names: Collection[str] | None = None,
    gateway: ToolGateway | None = None,
    recorder: InMemoryTraceRecorder | None = None,
    policy: FunctionCallingPolicy | None = None,
) -> FunctionCallingResult:
    """Execute independent planned calls concurrently, then merge in plan order."""

    calls = function_calls_from_post(post, plan, tool_names=tool_names)
    active_policy = policy or FunctionCallingPolicy()
    budget = min(plan.call_budget, active_policy.max_calls)
    selected = calls[:budget]
    if not selected:
        return FunctionCallingResult(
            stopped_reason=(
                "max_calls_reached" if calls and budget == 0 else None
            )
        )
    context = capability_context_from_post(post)
    active_gateway = gateway

    def invoke(call: dict):
        local_recorder = InMemoryTraceRecorder(run.run_id)
        single_plan = plan.model_copy(update={
            "available_tools": [call["name"]],
            "call_budget": 1,
        })
        single_policy = active_policy.model_copy(update={"max_calls": 1})
        outcome = RestrictedFunctionCaller(
            gateway=active_gateway
        ).execute(
            calls=[call],
            context=context,
            run=run,
            policy=single_policy,
            plan=single_plan,
            recorder=local_recorder,
        )
        return outcome, local_recorder.snapshot()

    with ThreadPoolExecutor(max_workers=len(selected)) as executor:
        outcomes = list(executor.map(invoke, selected))

    merged = FunctionCallingResult(
        stopped_reason=(
            "max_calls_reached" if len(calls) > len(selected) else None
        )
    )
    for outcome, trace in outcomes:
        merged.tool_results.extend(outcome.tool_results)
        merged.traces.extend(outcome.traces)
        merged.proposed_count += outcome.proposed_count
        merged.executed_count += outcome.executed_count
        merged.rejected_count += outcome.rejected_count
        if recorder is not None:
            recorder.trace.events.extend(trace.events)
    return merged

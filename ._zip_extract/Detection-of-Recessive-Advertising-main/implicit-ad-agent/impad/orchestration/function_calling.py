"""Capability-restricted execution for normalized LLM tool calls."""
from __future__ import annotations

from copy import deepcopy
import time
from typing import Literal, Sequence

from pydantic import BaseModel, Field, ValidationError

from ..tools.contracts import ToolResult, ToolStatus
from .capability_planner import CapabilityPlan
from .tool_gateway import (
    CapabilityContext,
    LocalToolGateway,
    RunContext,
    ToolGateway,
    UnexpectedToolArgumentsError,
    UnavailableToolError,
    UnknownToolError,
    input_fingerprint,
    validate_tool_arguments,
)
from .tracing import InMemoryTraceRecorder


class FunctionCallRequest(BaseModel):
    """Provider-neutral form of one LangChain-style tool call."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    args: dict = Field(default_factory=dict)


class FunctionCallingPolicy(BaseModel):
    """Hard bounds applied before any tool is executed."""

    max_calls: int = Field(default=8, ge=1, le=64)
    max_validation_retries: int = Field(default=1, ge=0, le=8)
    max_total_seconds: float | None = Field(default=None, gt=0)


class FunctionCallTrace(BaseModel):
    """Auditable outcome of one proposed tool call."""

    call_id: str
    tool_name: str
    status: Literal["completed", "rejected", "error"]
    error_code: str | None = None
    result_status: ToolStatus | None = None


class FunctionCallingResult(BaseModel):
    """Tool results and decision trace for one Function Calling batch."""

    tool_results: list[ToolResult] = Field(default_factory=list)
    traces: list[FunctionCallTrace] = Field(default_factory=list)
    stopped_reason: str | None = None
    proposed_count: int = Field(default=0, ge=0)
    executed_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)


class RestrictedFunctionCaller:
    """Expose and execute only tools allowed by the active capabilities."""

    def __init__(self, gateway: ToolGateway | None = None):
        self._gateway = gateway or LocalToolGateway()

    def available_functions(self, context: CapabilityContext) -> list[dict]:
        definitions = []
        for spec in self._gateway.list_tools(context):
            definition = deepcopy(spec.function_calling)
            definition["function"]["parameters"][
                "additionalProperties"
            ] = False
            definitions.append(definition)
        return definitions

    def execute(
        self,
        *,
        calls: Sequence[FunctionCallRequest | dict],
        context: CapabilityContext,
        run: RunContext,
        policy: FunctionCallingPolicy | None = None,
        plan: CapabilityPlan | None = None,
        recorder: InMemoryTraceRecorder | None = None,
    ) -> FunctionCallingResult:
        if recorder is not None and recorder.trace.run_id != run.run_id:
            raise ValueError("trace recorder run_id must match RunContext")
        active_policy = policy or FunctionCallingPolicy()
        listed = {
            spec.name: spec
            for spec in self._gateway.list_tools(context)
        }
        if plan is None:
            allowed = listed
            call_budget = active_policy.max_calls
        else:
            planned_names = set(plan.available_tools)
            allowed = {
                name: spec
                for name, spec in listed.items()
                if name in planned_names
            }
            call_budget = min(active_policy.max_calls, plan.call_budget)
        result = FunctionCallingResult()
        validation_rejections = 0
        seen_calls: set[tuple[str, str]] = set()
        batch_started = time.perf_counter()

        for index, raw_call in enumerate(calls):
            if index >= call_budget:
                result.stopped_reason = "max_calls_reached"
                self._record(
                    recorder,
                    event_type="run_stopped",
                    stage="function_calling",
                    data={"reason": result.stopped_reason},
                )
                break
            remaining_seconds = None
            if active_policy.max_total_seconds is not None:
                remaining_seconds = (
                    active_policy.max_total_seconds
                    - (time.perf_counter() - batch_started)
                )
                if remaining_seconds <= 0:
                    result.stopped_reason = "total_time_budget_exceeded"
                    self._record_stop(recorder, result.stopped_reason)
                    break

            try:
                call = (
                    raw_call
                    if isinstance(raw_call, FunctionCallRequest)
                    else FunctionCallRequest.model_validate(raw_call)
                )
            except ValidationError:
                raw_mapping = (
                    raw_call if isinstance(raw_call, dict) else {}
                )
                raw_id = raw_mapping.get("id")
                raw_name = raw_mapping.get("name")
                call = FunctionCallRequest(
                    id=raw_id
                    if isinstance(raw_id, str) and raw_id
                    else f"invalid_call_{index}",
                    name=raw_name
                    if isinstance(raw_name, str) and raw_name
                    else "<invalid>",
                )
                result.proposed_count += 1
                result.traces.append(FunctionCallTrace(
                    call_id=call.id,
                    tool_name=call.name,
                    status="rejected",
                    error_code="invalid_call_request",
                ))
                result.rejected_count += 1
                self._record(
                    recorder,
                    event_type="function_call_proposed",
                    stage="function_calling",
                    call_id=call.id,
                    tool_name=call.name,
                )
                self._record_rejection(
                    recorder,
                    call,
                    "invalid_call_request",
                )
                validation_rejections += 1
                if (
                    validation_rejections
                    > active_policy.max_validation_retries
                ):
                    result.stopped_reason = (
                        "validation_retry_budget_exceeded"
                    )
                    self._record_stop(recorder, result.stopped_reason)
                    break
                continue

            result.proposed_count += 1
            self._record(
                recorder,
                event_type="function_call_proposed",
                stage="function_calling",
                call_id=call.id,
                tool_name=call.name,
            )
            if call.name not in allowed:
                result.traces.append(FunctionCallTrace(
                    call_id=call.id,
                    tool_name=call.name,
                    status="rejected",
                    error_code="tool_not_allowed",
                ))
                result.rejected_count += 1
                self._record_rejection(
                    recorder,
                    call,
                    "tool_not_allowed",
                )
                validation_rejections += 1
                if validation_rejections > active_policy.max_validation_retries:
                    result.stopped_reason = "validation_retry_budget_exceeded"
                    self._record_stop(recorder, result.stopped_reason)
                    break
                continue

            try:
                validated = validate_tool_arguments(
                    allowed[call.name].tool.args_schema,
                    call.args,
                )
                validated_args = validated.model_dump(mode="json")
                fingerprint = input_fingerprint(validated_args)
                duplicate_key = (call.name, fingerprint)
                if duplicate_key in seen_calls:
                    result.traces.append(FunctionCallTrace(
                        call_id=call.id,
                        tool_name=call.name,
                        status="rejected",
                        error_code="duplicate_call",
                    ))
                    result.rejected_count += 1
                    self._record_rejection(
                        recorder,
                        call,
                        "duplicate_call",
                    )
                    validation_rejections += 1
                    if (
                        validation_rejections
                        > active_policy.max_validation_retries
                    ):
                        result.stopped_reason = (
                            "validation_retry_budget_exceeded"
                        )
                        self._record_stop(recorder, result.stopped_reason)
                        break
                    continue
                seen_calls.add(duplicate_key)

                run_update = {"call_id": call.id}
                timeout_candidates = []
                if run.timeout_seconds is not None:
                    timeout_candidates.append(run.timeout_seconds)
                if plan is not None and call.name in plan.tool_timeouts:
                    timeout_candidates.append(plan.tool_timeouts[call.name])
                if remaining_seconds is not None:
                    timeout_candidates.append(remaining_seconds)
                if timeout_candidates:
                    run_update["timeout_seconds"] = min(timeout_candidates)
                call_run = run.model_copy(update=run_update)
                self._record(
                    recorder,
                    event_type="tool_started",
                    stage="function_calling",
                    call_id=call.id,
                    tool_name=call.name,
                    data={"timeout_seconds": call_run.timeout_seconds},
                )
                result.executed_count += 1
                tool_result = self._gateway.call(
                    call.name,
                    validated_args,
                    call_run,
                )
            except (ValidationError, UnexpectedToolArgumentsError):
                result.traces.append(FunctionCallTrace(
                    call_id=call.id,
                    tool_name=call.name,
                    status="rejected",
                    error_code="invalid_arguments",
                ))
                result.rejected_count += 1
                self._record_rejection(
                    recorder,
                    call,
                    "invalid_arguments",
                )
                validation_rejections += 1
                if validation_rejections > active_policy.max_validation_retries:
                    result.stopped_reason = "validation_retry_budget_exceeded"
                    self._record_stop(recorder, result.stopped_reason)
                    break
                continue
            except (UnknownToolError, UnavailableToolError):
                result.traces.append(FunctionCallTrace(
                    call_id=call.id,
                    tool_name=call.name,
                    status="rejected",
                    error_code="tool_unavailable",
                ))
                result.rejected_count += 1
                self._record_rejection(
                    recorder,
                    call,
                    "tool_unavailable",
                )
                validation_rejections += 1
                if validation_rejections > active_policy.max_validation_retries:
                    result.stopped_reason = "validation_retry_budget_exceeded"
                    self._record_stop(recorder, result.stopped_reason)
                    break
                continue

            result.tool_results.append(tool_result)
            trace_status = "error" if tool_result.status == "error" else "completed"
            result.traces.append(FunctionCallTrace(
                call_id=call.id,
                tool_name=call.name,
                status=trace_status,
                error_code=tool_result.error_code,
                result_status=tool_result.status,
            ))
            self._record(
                recorder,
                event_type=(
                    "tool_failed"
                    if tool_result.status == "error"
                    else "tool_completed"
                ),
                stage="function_calling",
                call_id=call.id,
                tool_name=call.name,
                data={
                    "result_status": tool_result.status,
                    "error_code": tool_result.error_code,
                },
            )

        return result

    @staticmethod
    def _record(
        recorder: InMemoryTraceRecorder | None,
        *,
        event_type: str,
        stage: str,
        call_id: str | None = None,
        tool_name: str | None = None,
        data: dict | None = None,
    ) -> None:
        if recorder is not None:
            recorder.record(
                event_type=event_type,
                stage=stage,
                call_id=call_id,
                tool_name=tool_name,
                data=data,
            )

    @classmethod
    def _record_rejection(
        cls,
        recorder: InMemoryTraceRecorder | None,
        call: FunctionCallRequest,
        error_code: str,
    ) -> None:
        cls._record(
            recorder,
            event_type="function_call_rejected",
            stage="function_calling",
            call_id=call.id,
            tool_name=call.name,
            data={"error_code": error_code},
        )

    @classmethod
    def _record_stop(
        cls,
        recorder: InMemoryTraceRecorder | None,
        reason: str,
    ) -> None:
        cls._record(
            recorder,
            event_type="run_stopped",
            stage="function_calling",
            data={"reason": reason},
        )

"""Dependency-free run event recording for orchestration boundaries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts.run import RunMetadata


RunEventType = Literal[
    "analysis_started",
    "function_call_proposed",
    "function_call_rejected",
    "tool_started",
    "tool_completed",
    "tool_failed",
    "run_stopped",
    "judgment_completed",
    "rag_completed",
    "report_completed",
    "run_persisted",
]


class RunEvent(BaseModel):
    """One immutable, JSON-serializable orchestration event."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    event_type: RunEventType
    stage: str = Field(min_length=1)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    call_id: str | None = None
    tool_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class RunTrace(BaseModel):
    """Ordered events belonging to one analysis run."""

    run_id: str = Field(min_length=1)
    events: list[RunEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def event_run_ids_match(self):
        if any(event.run_id != self.run_id for event in self.events):
            raise ValueError("all trace events must have the same run_id")
        return self


class InMemoryTraceRecorder:
    """Append run events locally and provide safe snapshots."""

    def __init__(self, run_id: str):
        self.trace = RunTrace(run_id=run_id)

    def record(
        self,
        *,
        event_type: RunEventType,
        stage: str,
        call_id: str | None = None,
        tool_name: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> RunEvent:
        event = RunEvent(
            event_id=f"event_{uuid4().hex}",
            run_id=self.trace.run_id,
            event_type=event_type,
            stage=stage,
            call_id=call_id,
            tool_name=tool_name,
            data={} if data is None else dict(data),
        )
        self.trace.events.append(event)
        return event

    def snapshot(self) -> RunTrace:
        return self.trace.model_copy(deep=True)


def attach_trace(metadata: RunMetadata, trace: RunTrace) -> RunMetadata:
    """Return metadata with ordered, de-duplicated event identifiers."""

    if metadata.run_id != trace.run_id:
        raise ValueError("RunMetadata and RunTrace run_id values must match")
    trace_ids = list(dict.fromkeys([
        *metadata.trace_ids,
        *(event.event_id for event in trace.events),
    ]))
    return metadata.model_copy(update={"trace_ids": trace_ids})

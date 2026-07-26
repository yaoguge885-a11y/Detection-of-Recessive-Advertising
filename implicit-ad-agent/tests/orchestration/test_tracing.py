import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.run import RunMetadata
from impad.orchestration.tracing import (
    InMemoryTraceRecorder,
    RunEvent,
    RunTrace,
    attach_trace,
)


def test_recorder_appends_ordered_json_serializable_events():
    recorder = InMemoryTraceRecorder("run_1")

    started = recorder.record(
        event_type="tool_started",
        stage="function_calling",
        call_id="call_1",
        tool_name="analyze_text_intent",
        data={"timeout_seconds": 10},
    )
    completed = recorder.record(
        event_type="tool_completed",
        stage="function_calling",
        call_id="call_1",
        tool_name="analyze_text_intent",
        data={"result_status": "ok"},
    )

    assert recorder.trace.events == [started, completed]
    assert started.run_id == "run_1"
    assert started.timestamp <= completed.timestamp
    assert started.event_id != completed.event_id
    json.dumps(recorder.trace.model_dump(mode="json"), ensure_ascii=False)


def test_trace_rejects_event_from_another_run():
    event = RunEvent(
        event_id="event_1",
        run_id="run_other",
        event_type="run_stopped",
        stage="function_calling",
    )

    with pytest.raises(ValidationError, match="same run_id"):
        RunTrace(run_id="run_1", events=[event])


def test_recorder_returns_a_snapshot_not_its_mutable_internal_trace():
    recorder = InMemoryTraceRecorder("run_1")
    recorder.record(
        event_type="function_call_proposed",
        stage="function_calling",
        call_id="call_1",
        tool_name="analyze_text_intent",
    )

    snapshot = recorder.snapshot()
    snapshot.events.clear()

    assert len(recorder.trace.events) == 1


def test_trace_event_ids_are_attached_to_matching_run_metadata():
    recorder = InMemoryTraceRecorder("run_1")
    first = recorder.record(
        event_type="function_call_proposed",
        stage="function_calling",
    )
    second = recorder.record(
        event_type="run_stopped",
        stage="function_calling",
    )
    metadata = RunMetadata(
        run_id="run_1",
        status="completed",
        started_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        trace_ids=["event_existing"],
    )

    attached = attach_trace(metadata, recorder.snapshot())

    assert attached.trace_ids == [
        "event_existing",
        first.event_id,
        second.event_id,
    ]
    assert metadata.trace_ids == ["event_existing"]


def test_trace_cannot_be_attached_to_different_run_metadata():
    metadata = RunMetadata(
        run_id="run_1",
        status="failed",
        started_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    trace = RunTrace(run_id="run_other")

    with pytest.raises(ValueError, match="run_id"):
        attach_trace(metadata, trace)

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.run import RunIssue, RunMetadata


def test_run_metadata_serializes_versions_and_degradation():
    metadata = RunMetadata(
        run_id="run_1",
        status="degraded",
        started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        duration_ms=15,
        tool_versions={"analyze_text_intent": "1.0"},
        model_versions={"intent": "rule_v1"},
        issues=[RunIssue(
            kind="degradation",
            code="history_unavailable",
            message="Creator history was not available.",
            stage="capability_plan",
            retryable=False,
        )],
        trace_ids=["trace_1"],
    )

    assert metadata.issues[0].kind == "degradation"
    json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False)


def test_run_metadata_rejects_negative_duration():
    with pytest.raises(ValidationError):
        RunMetadata(
            run_id="run_1",
            status="failed",
            started_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            duration_ms=-1,
        )


def test_run_metadata_serializes_runtime_cost_and_trace_summary():
    metadata = RunMetadata(
        run_id="run_observed",
        status="completed",
        started_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        runtime_mode="mcp",
        planner_version="capability-planner-v1",
        prompt_versions={"supervisor": "prompt-v2"},
        token_usage={"input": 120, "output": 30},
        cost_usd=0.002,
        retry_count=1,
        fallback_count=0,
        trace_ids=["event_1", "event_2"],
    )

    assert metadata.runtime_mode == "mcp"
    assert metadata.token_usage["input"] == 120
    assert metadata.cost_usd == 0.002
    json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False)


def test_run_metadata_rejects_negative_usage_or_cost():
    with pytest.raises(ValidationError):
        RunMetadata(
            run_id="run_bad_cost",
            status="failed",
            started_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            cost_usd=-0.1,
        )

    with pytest.raises(ValidationError):
        RunMetadata(
            run_id="run_bad_tokens",
            status="failed",
            started_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
            token_usage={"input": -1},
        )

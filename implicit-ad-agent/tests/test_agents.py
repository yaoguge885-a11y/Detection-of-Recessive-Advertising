"""P2.5 agent routing and structured judgment tests."""
from __future__ import annotations

from impad.agents import judge, route_next, supervisor
from impad.contracts import (
    EvidenceBundle,
    PostRecord,
    VerdictReport,
)
from impad.orchestration import CapabilityPlan
from impad.tools.contracts import ToolEvidence, ToolResult


def test_supervisor_routes_by_capability_plan():
    text_only = supervisor({"post": {"text": "hi"}})
    assert text_only["plan"] == ["nlp"]

    with_history_and_comments = supervisor({
        "post": {
            "text": "hi",
            "published_at": "2026-07-20T00:00:00Z",
            "comments": [f"评论{index}" for index in range(5)],
            "history": [
                {
                    "post_id": f"post_history_{index}",
                    "text": f"历史{index}",
                    "published_at": f"2026-07-{17 + index}T00:00:00Z",
                }
                for index in range(3)
            ],
        }
    })
    assert with_history_and_comments["plan"] == ["nlp", "behavior"]
    assert isinstance(
        with_history_and_comments["post_record"],
        PostRecord,
    )
    assert isinstance(
        with_history_and_comments["capability_plan"],
        CapabilityPlan,
    )


def test_route_next_falls_back_to_judge():
    assert route_next({"plan": ["vision", "behavior"]}) == "vision"
    assert route_next({"plan": []}) == "judge"


def test_judge_builds_structured_report_from_tool_results():
    state = supervisor({
        "post": {
            "text": "本内容由品牌赞助",
            "capture_complete": True,
        }
    })
    state["tool_results"] = [
        ToolResult(
            tool_name="analyze_text_intent",
            status="degraded",
            score=0.8,
            evidence=[
                ToolEvidence(
                    kind="explicit_ad_marker",
                    source="post.text",
                    quote="赞助",
                    score=0.8,
                )
            ],
        )
    ]

    out = judge(state)

    assert isinstance(out["evidence_bundle"], EvidenceBundle)
    assert isinstance(out["verdict_report"], VerdictReport)
    assert out["verdict"] == "明广"
    assert out["report"]

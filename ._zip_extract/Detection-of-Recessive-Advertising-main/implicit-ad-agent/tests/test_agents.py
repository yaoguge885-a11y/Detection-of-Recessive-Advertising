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
    assert text_only["plan"] == ["nlp", "creator_shift"]

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
    assert with_history_and_comments["plan"] == [
        "nlp",
        "behavior",
        "creator_shift",
    ]
    assert isinstance(
        with_history_and_comments["post_record"],
        PostRecord,
    )
    assert isinstance(
        with_history_and_comments["capability_plan"],
        CapabilityPlan,
    )


def test_supervisor_accepts_schema_v12_content_record():
    state = supervisor(
        {
            "post": {
                "schema_version": "1.2",
                "post_id": "post_v12_supervisor_001",
                "platform": "bilibili",
                "source_type": "manual_public_collection",
                "blogger_id": "blogger_v12_supervisor_001",
                "published_at": "2026-07-28T12:00:00+08:00",
                "title": "测试视频",
                "content_group_id": None,
                "text": "本期视频介绍测试产品",
                "media": [],
                "comments": [],
                "blogger_history_refs": [],
                "provenance": {
                    "source_ref_hash": "source-v12-supervisor-001",
                    "collected_at": "2026-07-28T12:01:00+08:00",
                    "collector": "A",
                    "terms_checked_at": "2026-07-28",
                },
                "privacy": {
                    "anonymized": True,
                    "contains_sensitive_data": False,
                },
            }
        }
    )

    assert state["post_record"].schema_version == "1.2"
    assert state["post_record"].platform == "bilibili"
    assert state["post_record"].creator_id == "blogger_v12_supervisor_001"


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

"""End-to-end P2.5 evidence flow over the existing local graph."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from impad.contracts import (
    CaptureStatus,
    EvidenceBundle,
    PostRecord,
    RunMetadata,
    VerdictReport,
)
from impad.agents import behavior_agent, nlp_agent, supervisor, vision_agent
from impad.graph import graph
from impad.orchestration import CapabilityPlan
from impad.tools.contracts import ToolEvidence, ToolResult
from impad.orchestration import LocalToolGateway


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_graph_executes_all_eligible_non_vision_tools_with_one_run():
    out = graph.invoke({
        "post": {
            "text": "限时推荐，欢迎了解",
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

    names = {result.tool_name for result in out["tool_results"]}
    assert names == {
        "analyze_text_intent",
        "sentiment_curve",
        "topic_drift",
        "comment_anomaly",
    }
    run_id = out["run_metadata"].run_id
    assert {result.run_id for result in out["tool_results"]} == {run_id}
    assert {
        event.event_type for event in out["run_events"]
    } >= {"function_call_proposed", "tool_completed"}


def test_graph_state_contains_structured_p2_5_boundary():
    out = graph.invoke({"post": {"text": "普通生活记录"}})

    assert isinstance(out["post_record"], PostRecord)
    assert isinstance(out["capture_status"], CaptureStatus)
    assert isinstance(out["capability_plan"], CapabilityPlan)
    assert isinstance(out["evidence_bundle"], EvidenceBundle)
    assert isinstance(out["run_metadata"], RunMetadata)
    assert isinstance(out["verdict_report"], VerdictReport)
    assert len(out["tool_results"]) == 2


def test_soft_ad_with_unknown_disclosure_requires_review():
    out = graph.invoke({
        "post": {
            "text": "这款面霜无限回购，链接在评论区",
        }
    })

    assert out["verdict_report"].commercial_intent.status == "present"
    assert out["verdict_report"].disclosure.status == "unknown"
    assert out["verdict"] == "需复核"


def test_explicit_synthetic_p1_record_returns_structured_explicit_ad():
    payload = json.loads(
        (
            REPO_ROOT / "data/synthetic/simulated_posts_v1.json"
        ).read_text(encoding="utf-8")
    )

    out = graph.invoke({"post": payload["content_records"][0]})

    assert out["post_record"].post_id == "post_explicit_sponsor"
    assert out["verdict"] == "明广"
    assert out["verdict_report"].review_required is False


@pytest.mark.parametrize("missing_field", ["privacy", "schema_version"])
def test_p1_shaped_input_missing_required_field_is_not_treated_as_manual(
    missing_field,
):
    payload = json.loads(
        (
            REPO_ROOT / "data/synthetic/simulated_posts_v1.json"
        ).read_text(encoding="utf-8")
    )
    malformed = dict(payload["content_records"][0])
    malformed.pop(missing_field)

    with pytest.raises(
        ValueError,
        match=r"P1 content_record validation failed:.*required",
    ):
        graph.invoke({"post": malformed})


def test_severely_malformed_p1_shape_is_not_treated_as_manual():
    payload = json.loads(
        (
            REPO_ROOT / "data/synthetic/simulated_posts_v1.json"
        ).read_text(encoding="utf-8")
    )
    malformed = dict(payload["content_records"][0])
    for field in ("schema_version", "provenance", "privacy"):
        malformed.pop(field)

    with pytest.raises(
        ValueError,
        match=r"P1 content_record validation failed:.*required",
    ):
        graph.invoke({"post": malformed})


def test_legacy_manual_input_remains_accepted():
    out = graph.invoke({
        "post": {
            "text": "今天去图书馆读书",
            "blogger": "小美",
            "comments": ["真不错"],
            "history": ["昨天散步"],
        }
    })

    assert out["post_record"].creator_id.startswith("blogger_manual_")
    assert out["verdict"] in {"非广", "需复核"}
    assert out["report"]


def test_run_level_call_budget_is_shared_across_expert_groups(tmp_path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fixture")
    state = supervisor({
        "post": {
            "text": "限时推荐",
            "published_at": "2026-07-20T00:00:00Z",
            "image_path": str(image),
            "comments": [f"评论{index}" for index in range(5)],
            "history": [
                {
                    "post_id": f"history_{index}",
                    "text": f"历史{index}",
                    "published_at": f"2026-07-{17 + index}T00:00:00Z",
                }
                for index in range(3)
            ],
        }
    })
    state["capability_plan"] = state["capability_plan"].model_copy(
        update={"call_budget": 3}
    )

    state.update(nlp_agent(state))
    state.update(vision_agent(state))
    state.update(behavior_agent(state))

    assert len(state["function_traces"]) == 3
    assert len(state["tool_results"]) == 3
    assert state["agent_outputs"]["vision"]["stopped_reason"] == (
        "max_calls_reached"
    )
    assert state["agent_outputs"]["behavior"]["stopped_reason"] == (
        "max_calls_reached"
    )


class MultiImageOcrGateway(LocalToolGateway):
    def call(self, name, arguments, run):
        if name == "ocr_extract":
            image_name = Path(arguments["image_path"]).name
            sponsored = image_name == "second.jpg"
            quote = "本内容由品牌方赞助" if sponsored else "日常记录"
            evidence = ToolEvidence(
                kind="ocr_text" if sponsored else "absence",
                source="image.ocr",
                quote=quote,
                score=0.99 if sponsored else 0.1,
            )
            return ToolResult(
                tool_name=name,
                tool_version="test-ocr-v1",
                status="ok",
                score=evidence.score,
                evidence=[evidence],
                payload={
                    "vision_context": {
                        "image_name": image_name,
                        "capabilities": {"ocr": True},
                    },
                },
                call_id=run.call_id,
                run_id=run.run_id,
            )
        if name in {"image_text_consistency", "detect_logo_product"}:
            return ToolResult(
                tool_name=name,
                tool_version="test-vision-v1",
                status="ok",
                payload={},
                call_id=run.call_id,
                run_id=run.run_id,
            )
        return super().call(name, arguments, run)


def test_graph_tracks_per_image_ocr_disclosure_and_call_provenance(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    out = graph.invoke({
        "post": {
            "text": "今天记录一下生活。",
            "capture_complete": True,
            "media": [
                {"media_id": "media_first", "type": "image",
                 "ref": str(first)},
                {"media_id": "media_second", "type": "image",
                 "ref": str(second)},
            ],
        },
        "tool_gateway": MultiImageOcrGateway(),
    })

    assert out["verdict"] == "明广"
    ocr_results = [
        result for result in out["tool_results"]
        if result.tool_name == "ocr_extract"
    ]
    assert {
        result.payload["media_id"] for result in ocr_results
    } == {"media_first", "media_second"}
    marker = next(
        item for item in out["evidence_bundle"].items
        if item.kind == "explicit_ad_marker"
    )
    assert marker.call_id == "call_ocr_extract_media_1_media_second"
    assert marker.call_id in {
        trace.call_id for trace in out["function_traces"]
    }

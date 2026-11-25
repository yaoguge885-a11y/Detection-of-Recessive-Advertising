"""Captured platform sponsorship badges must reach the final verdict."""
from __future__ import annotations

import pytest

from impad.adapters.manual import post_record_from_manual
from impad.contracts.post import DisclosureRecord, MediaRecord
from impad.orchestration.evidence_adapters import build_evidence_bundle
from impad.orchestration.judgment import build_verdict_report
from impad.tools.contracts import ToolResult


def _post_with_badge(text, *, kind="platform_badge", source="platform_metadata"):
    post = post_record_from_manual({"text": "今天分享使用体验"})
    return post.model_copy(update={
        "disclosures": [DisclosureRecord(kind=kind, text=text, source=source)],
        "media": [MediaRecord(media_id="video_0", type="video")],
    })


@pytest.mark.parametrize("badge", ["广告", "品牌合作", "赞助", "Paid partnership", " Sponsored "])
def test_captured_badge_establishes_overt_ad_even_without_video_frames(badge):
    post = _post_with_badge(badge)
    bundle = build_evidence_bundle(post, [ToolResult(
        tool_name="analyze_text_intent", status="degraded", score=0,
    )])
    verdict = build_verdict_report(post, bundle)

    assert verdict.label == "明广"
    assert verdict.disclosure.status == "disclosed"
    marker = next(item for item in bundle.items if item.kind == "explicit_ad_marker")
    assert marker.quote == badge
    assert marker.source == "post.disclosures[0]"
    assert marker.source_type == "disclosure"
    assert marker.evidence_id in verdict.disclosure.evidence_ids


@pytest.mark.parametrize(("badge", "kind", "source"), [
    ("原创", "platform_badge", "platform_metadata"),
    ("非广告", "platform_badge", "platform_metadata"),
    ("广告", "text_statement", "post_text"),
    ("#ad", "hashtag", "post_text"),
])
def test_unverified_text_markers_and_unrelated_badges_do_not_prove_disclosure(badge, kind, source):
    post = _post_with_badge(badge, kind=kind, source=source)
    bundle = build_evidence_bundle(post, [ToolResult(
        tool_name="analyze_text_intent", status="degraded", score=0,
    )])
    verdict = build_verdict_report(post, bundle)
    assert not any(item.kind == "explicit_ad_marker" for item in bundle.items)
    assert verdict.label == "需复核"


def test_platform_badge_survives_the_complete_agent_graph(monkeypatch):
    from impad.config import settings
    from impad.graph import graph

    monkeypatch.setattr(settings, "text_intent_model_path", "")
    state = graph.invoke({"post": _post_with_badge("品牌合作")})

    assert state["verdict_report"].label == "明广"
    assert state["verdict_report"].disclosure.evidence_ids
    assert any(
        item.source == "post.disclosures[0]"
        for item in state["evidence_bundle"].items
    )

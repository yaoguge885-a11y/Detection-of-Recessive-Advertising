"""Evidence-adequacy gate behavior."""
from __future__ import annotations

from impad.adapters.manual import post_record_from_manual
from impad.contracts.evidence import (
    EvidenceBundle,
    EvidenceConflict,
    EvidenceItem,
)
from impad.orchestration.adequacy import assess_evidence_adequacy
from impad.orchestration.evidence_adapters import build_evidence_bundle
from impad.tools.contracts import ToolEvidence, ToolResult


def _text_result(score: float = 0.2) -> ToolResult:
    return ToolResult(
        tool_name="analyze_text_intent",
        status="degraded",
        score=score,
        evidence=[
            ToolEvidence(
                kind="current_text_assessment",
                source="post.text",
                quote="已分析正文",
                score=score,
            )
        ],
    )


def test_missing_text_intent_blocks_forced_verdict():
    post = post_record_from_manual({"text": "正文存在"})
    bundle = build_evidence_bundle(post, [])

    result = assess_evidence_adequacy(post, bundle)

    assert result.intent_evaluable is False
    assert result.review_required is True
    assert "text_intent_missing" in result.reason_codes


def test_optional_image_and_history_do_not_block_text_only_verdict():
    post = post_record_from_manual({"text": "普通生活记录"})
    bundle = build_evidence_bundle(
        post,
        [
            _text_result(),
            ToolResult(tool_name="topic_drift", status="skipped"),
        ],
    )

    result = assess_evidence_adequacy(post, bundle)

    assert result.intent_evaluable is True
    assert result.review_required is False
    assert "topic_drift_skipped" not in result.reason_codes


def test_provided_but_unavailable_image_requires_review():
    post = post_record_from_manual({
        "text": "含图片的帖子",
        "image_url": "https://example.com/image.jpg",
    })
    bundle = build_evidence_bundle(post, [_text_result(0.8)])

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "image_capture_incomplete" in result.reason_codes


def test_image_execution_error_requires_review_when_image_was_provided(
    tmp_path,
):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fixture")
    post = post_record_from_manual({
        "text": "含本地图像",
        "image_path": str(image),
    })
    bundle = build_evidence_bundle(
        post,
        [
            _text_result(0.8),
            ToolResult(
                tool_name="ocr_extract",
                status="error",
                error_code="tool_execution_error",
            ),
        ],
    )

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "image_tool_error" in result.reason_codes


def test_image_tool_skip_requires_review_when_image_was_provided(tmp_path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fixture")
    post = post_record_from_manual({
        "text": "含本地图像",
        "image_path": str(image),
    })
    bundle = build_evidence_bundle(
        post,
        [
            _text_result(0.8),
            ToolResult(
                tool_name="ocr_extract",
                status="skipped",
            ),
        ],
    )

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "image_tool_unavailable" in result.reason_codes


def test_missing_image_tool_results_require_review_without_explicit_marker(
    tmp_path,
):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fixture")
    post = post_record_from_manual({
        "text": "含本地图像",
        "image_path": str(image),
    })
    bundle = build_evidence_bundle(post, [_text_result(0.8)])

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "image_evidence_missing" in result.reason_codes


def test_evidence_conflict_always_requires_review():
    post = post_record_from_manual({"text": "有冲突"})
    items = [
        EvidenceItem(
            evidence_id="ev_support",
            kind="soft_ad_signal",
            source="post.text",
            tool_name="analyze_text_intent",
            tool_version="1.0",
        ),
        EvidenceItem(
            evidence_id="ev_contradict",
            kind="counter_signal",
            source="post.text",
            tool_name="analyze_text_intent",
            tool_version="1.0",
        ),
    ]
    bundle = EvidenceBundle(
        post_id=post.post_id,
        items=items,
        tool_results=[_text_result(0.6)],
        conflicts=[
            EvidenceConflict(
                conflict_id="conflict_1",
                evidence_ids=["ev_support", "ev_contradict"],
                reason="相反证据",
            )
        ],
    )

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "evidence_conflict" in result.reason_codes


def test_tool_reported_image_text_conflict_requires_review():
    post = post_record_from_manual({"text": "正文存在"})
    bundle = build_evidence_bundle(
        post,
        [
            _text_result(0.2),
            ToolResult(
                tool_name="image_text_consistency",
                status="degraded",
                score=0.1,
                evidence=[
                    ToolEvidence(
                        kind="ocr_semantic_overlap",
                        source="post.text<->image.ocr",
                        quote="完全不同的图片文案",
                        score=0.1,
                    )
                ],
                payload={"relation": "conflicting"},
            ),
        ],
    )

    result = assess_evidence_adequacy(post, bundle)

    assert result.review_required is True
    assert "evidence_conflict" in result.reason_codes

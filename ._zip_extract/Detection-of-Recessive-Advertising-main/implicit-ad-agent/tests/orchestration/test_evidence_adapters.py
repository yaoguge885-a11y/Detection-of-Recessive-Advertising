"""Seven-tool result to evidence-bundle adaptation."""
from __future__ import annotations

import pytest

from impad.adapters.manual import post_record_from_manual
from impad.orchestration.evidence_adapters import (
    build_evidence_bundle,
    evidence_items_from_tool_result,
)
from impad.tools.contracts import ToolEvidence, ToolLimitation, ToolResult


@pytest.mark.parametrize(
    ("tool_name", "kind", "source"),
    [
        ("analyze_text_intent", "soft_ad_signal", "post.text"),
        ("sentiment_curve", "emotion_signal", "post.text"),
        ("ocr_extract", "ocr_text", "image.ocr"),
        (
            "image_text_consistency",
            "object_text_alignment",
            "post.text<->image.yolo",
        ),
        ("detect_logo_product", "commercial_object", "image.yolo"),
        ("topic_drift", "nearest_history", "blogger.history"),
        ("comment_anomaly", "comment_anomaly", "post.comments"),
    ],
)
def test_each_registered_tool_converts_usable_observation(
    tool_name,
    kind,
    source,
):
    result = ToolResult(
        tool_name=tool_name,
        status="degraded",
        score=0.7,
        evidence=[
            ToolEvidence(
                kind=kind,
                source=source,
                quote="可定位证据",
            )
        ],
    )

    items = evidence_items_from_tool_result(result)

    assert len(items) == 1
    assert items[0].tool_name == tool_name
    assert items[0].kind == kind
    assert items[0].source_ref == source
    assert items[0].strength == 0.7
    assert items[0].status == "degraded"


def test_adapter_preserves_all_source_pointers():
    result = ToolResult(
        tool_name="comment_anomaly",
        tool_version="1.2",
        call_id="call_comments",
        status="ok",
        evidence=[
            ToolEvidence(
                kind="comment_anomaly",
                source="post.comments",
                quote="模板化评论",
                span=(1, 4),
                bbox=[1, 2, 3, 4],
                related_post_id="post_history_1",
                comment_ids=["comment_1", "comment_2"],
                score=0.8,
            )
        ],
    )

    item = evidence_items_from_tool_result(result)[0]

    assert item.call_id == "call_comments"
    assert item.span == (1, 4)
    assert item.bbox == [1, 2, 3, 4]
    assert item.related_post_id == "post_history_1"
    assert item.comment_ids == ["comment_1", "comment_2"]
    assert item.producer_version == "1.2"


def test_skipped_error_absence_and_insufficient_create_no_evidence_items():
    results = [
        ToolResult(
            tool_name="topic_drift",
            status="skipped",
            evidence=[
                ToolEvidence(
                    kind="nearest_history",
                    source="blogger.history",
                )
            ],
        ),
        ToolResult(
            tool_name="ocr_extract",
            status="error",
            evidence=[
                ToolEvidence(kind="ocr_text", source="image.ocr")
            ],
        ),
        ToolResult(
            tool_name="analyze_text_intent",
            status="degraded",
            score=0,
            evidence=[
                ToolEvidence(kind="absence", source="post.text", score=0)
            ],
        ),
        ToolResult(
            tool_name="image_text_consistency",
            status="degraded",
            evidence=[
                ToolEvidence(
                    kind="insufficient",
                    source="image.visual",
                )
            ],
        ),
    ]

    assert [
        evidence_items_from_tool_result(result)
        for result in results
    ] == [[], [], [], []]


def test_bundle_preserves_outcomes_limitations_coverage_and_missing_state():
    post = post_record_from_manual({
        "text": "带远程图片",
        "image_url": "https://example.com/image.jpg",
    })
    results = [
        ToolResult(
            tool_name="analyze_text_intent",
            status="degraded",
            score=0.6,
            evidence=[
                ToolEvidence(
                    kind="soft_ad_signal",
                    source="post.text",
                    quote="推荐",
                )
            ],
        ),
        ToolResult(
            tool_name="ocr_extract",
            status="skipped",
            limitations=[
                ToolLimitation(
                    kind="capture",
                    code="local_image_missing",
                    message="No local image.",
                    source="media.ref",
                )
            ],
        ),
    ]

    bundle = build_evidence_bundle(post, results)

    assert bundle.tool_results == results
    assert bundle.limitations == results[1].limitations
    assert "capture:image:partial:local_media.ref" in (
        bundle.missing_requirements
    )
    assert "tool:ocr_extract:skipped" in bundle.missing_requirements
    image_coverage = next(
        item for item in bundle.coverage if item.modality == "image"
    )
    assert image_coverage.status == "partial"


def test_evidence_ids_are_deterministic_and_unique():
    result = ToolResult(
        tool_name="analyze_text_intent",
        call_id="call_1",
        status="degraded",
        score=0.8,
        evidence=[
            ToolEvidence(
                kind="soft_ad_signal",
                source="post.text",
                quote="推荐",
            ),
            ToolEvidence(
                kind="soft_ad_signal",
                source="post.text",
                quote="推荐",
            ),
        ],
    )

    first = evidence_items_from_tool_result(result)
    second = evidence_items_from_tool_result(result)

    assert [item.evidence_id for item in first] == [
        item.evidence_id for item in second
    ]
    assert len({item.evidence_id for item in first}) == 2


def test_ocr_disclosure_marker_becomes_explicit_disclosure_evidence():
    result = ToolResult(
        tool_name="ocr_extract",
        status="ok",
        score=0.9,
        evidence=[
            ToolEvidence(
                kind="ocr_text",
                source="image.ocr",
                quote="本内容由品牌方赞助",
                bbox=[10, 20, 100, 50],
                score=0.9,
            )
        ],
    )

    items = evidence_items_from_tool_result(result)
    disclosure = [
        item for item in items if item.kind == "explicit_ad_marker"
    ]

    assert len(disclosure) == 1
    assert disclosure[0].quote == "赞助"
    assert disclosure[0].bbox == [10, 20, 100, 50]
    assert disclosure[0].source_type == "image"
    assert disclosure[0].polarity == "supports"

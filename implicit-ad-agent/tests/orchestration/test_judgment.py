"""Deterministic P2.5 judgment baseline."""
from __future__ import annotations

import pytest

from impad.adapters.manual import post_record_from_manual
from impad.orchestration.evidence_adapters import build_evidence_bundle
from impad.orchestration.judgment import (
    assess_commercial_intent,
    assess_disclosure,
    build_verdict_report,
)
from impad.tools.contracts import ToolEvidence, ToolResult


def _post(*, disclosure_complete: bool, image_url: str | None = None):
    raw = {
        "text": "待分析正文",
        "capture_complete": disclosure_complete,
    }
    if image_url is not None:
        raw["image_url"] = image_url
    return post_record_from_manual(raw)


def _bundle(post, *, score: float, kind: str):
    return build_evidence_bundle(
        post,
        [
            ToolResult(
                tool_name="analyze_text_intent",
                status="degraded",
                score=score,
                evidence=[
                    ToolEvidence(
                        kind=kind,
                        source="post.text",
                        quote="可定位正文证据",
                        score=score,
                    )
                ],
            )
        ],
    )


@pytest.mark.parametrize(
    (
        "score",
        "kind",
        "disclosure_complete",
        "expected_intent",
        "expected_disclosure",
        "expected_label",
    ),
    [
        (
            0.1,
            "current_text_assessment",
            False,
            "absent",
            "unknown",
            "非广",
        ),
        (
            0.8,
            "explicit_ad_marker",
            False,
            "present",
            "disclosed",
            "明广",
        ),
        (
            0.8,
            "soft_ad_signal",
            True,
            "present",
            "not_disclosed",
            "暗广",
        ),
        (
            0.8,
            "soft_ad_signal",
            False,
            "present",
            "unknown",
            "需复核",
        ),
        (
            0.4,
            "soft_ad_signal",
            True,
            "uncertain",
            "not_disclosed",
            "需复核",
        ),
    ],
)
def test_judgment_label_table(
    score,
    kind,
    disclosure_complete,
    expected_intent,
    expected_disclosure,
    expected_label,
):
    post = _post(disclosure_complete=disclosure_complete)
    bundle = _bundle(post, score=score, kind=kind)

    intent = assess_commercial_intent(bundle)
    disclosure = assess_disclosure(post, bundle)
    report = build_verdict_report(post, bundle)

    assert intent.status == expected_intent
    assert disclosure.status == expected_disclosure
    assert report.label == expected_label
    assert report.review_required is (expected_label == "需复核")
    assert report.judgment_method == "deterministic_baseline_v1"


def test_adequacy_failure_overrides_otherwise_present_intent():
    post = _post(
        disclosure_complete=True,
        image_url="https://example.com/missing.jpg",
    )
    bundle = _bundle(post, score=0.8, kind="soft_ad_signal")

    report = build_verdict_report(post, bundle)

    assert report.label == "需复核"
    assert "image_capture_incomplete" in report.reasons


def test_report_only_references_real_bundle_evidence_and_invents_no_law():
    post = _post(disclosure_complete=False)
    bundle = _bundle(post, score=0.8, kind="explicit_ad_marker")

    report = build_verdict_report(post, bundle)
    known_ids = {item.evidence_id for item in bundle.items}

    assert set(report.evidence_ids) <= known_ids
    assert set(report.commercial_intent.evidence_ids) <= known_ids
    assert set(report.disclosure.evidence_ids) <= known_ids
    assert report.law_evidence == []


def _ocr_result(*, ocr_available: bool, status: str = "ok"):
    return ToolResult(
        tool_name="ocr_extract",
        status=status,
        score=0,
        evidence=[
            ToolEvidence(
                kind="absence",
                source="image.ocr",
                quote="No text above the confidence threshold.",
                score=0,
            )
        ],
        payload={
            "vision_context": {
                "capabilities": {"ocr": ocr_available},
            }
        },
    )


def test_multiple_images_keep_non_disclosure_unknown_until_all_are_analyzed(
    tmp_path,
):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    post = post_record_from_manual({
        "text": "限时推荐",
        "capture_complete": True,
        "media": [
            {"media_id": "media_1", "type": "image", "ref": str(first)},
            {"media_id": "media_2", "type": "image", "ref": str(second)},
        ],
    })
    bundle = build_evidence_bundle(
        post,
        [
            *_bundle(
                post,
                score=0.8,
                kind="soft_ad_signal",
            ).tool_results,
            _ocr_result(ocr_available=True),
        ],
    )

    report = build_verdict_report(post, bundle)

    assert report.disclosure.status == "unknown"
    assert report.label == "需复核"
    assert "image_coverage_incomplete" in report.reasons


def test_degraded_ocr_without_ocr_capability_cannot_prove_non_disclosure(
    tmp_path,
):
    image = tmp_path / "single.jpg"
    image.write_bytes(b"image")
    post = post_record_from_manual({
        "text": "限时推荐",
        "capture_complete": True,
        "image_path": str(image),
    })
    bundle = build_evidence_bundle(
        post,
        [
            *_bundle(
                post,
                score=0.8,
                kind="soft_ad_signal",
            ).tool_results,
            _ocr_result(ocr_available=False, status="degraded"),
        ],
    )

    report = build_verdict_report(post, bundle)

    assert report.disclosure.status == "unknown"
    assert report.label == "需复核"
    assert "image_ocr_unavailable" in report.reasons


def test_unsupported_media_cannot_prove_non_disclosure():
    post = post_record_from_manual({
        "text": "限时推荐",
        "capture_complete": True,
        "media": [
            {
                "media_id": "media_video_1",
                "type": "video",
                "ref": "video.mp4",
            }
        ],
    })
    bundle = _bundle(
        post,
        score=0.8,
        kind="soft_ad_signal",
    )

    report = build_verdict_report(post, bundle)

    assert report.disclosure.status == "unknown"
    assert report.label == "需复核"
    assert "unsupported_media_for_disclosure" in report.reasons

"""Evidence-adequacy gate for the deterministic P2.5 judgment baseline."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts.evidence import EvidenceBundle
from ..contracts.post import PostRecord


_IMAGE_TOOLS = {
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
}


def non_disclosure_assessment_reasons(
    post: PostRecord,
    bundle: EvidenceBundle,
) -> list[str]:
    """Explain why absence of disclosure cannot be established safely."""

    if any(item.type != "image" for item in post.media):
        return ["unsupported_media_for_disclosure"]
    if not post.capture_status.can_assess_disclosure:
        return ["capture_not_sufficient_for_non_disclosure"]
    image_media = [item for item in post.media if item.type == "image"]
    if not image_media:
        return []
    if len(image_media) != 1:
        return ["image_coverage_incomplete"]
    ocr_results = [
        result
        for result in bundle.tool_results
        if result.tool_name == "ocr_extract"
    ]
    if len(ocr_results) != 1:
        return ["image_ocr_missing"]
    ocr_result = ocr_results[0]
    capabilities = (
        ocr_result.payload.get("vision_context") or {}
    ).get("capabilities") or {}
    if ocr_result.status != "ok" or capabilities.get("ocr") is not True:
        return ["image_ocr_unavailable"]
    return []


class EvidenceAdequacyResult(BaseModel):
    """Whether available evidence can support a forced classification."""

    intent_evaluable: bool
    review_required: bool
    reason_codes: list[str] = Field(default_factory=list)


def assess_evidence_adequacy(
    post: PostRecord,
    bundle: EvidenceBundle,
) -> EvidenceAdequacyResult:
    """Require critical evidence while keeping optional missing data unknown."""

    reasons = []
    text_capture = post.capture_status.modalities.get("text")
    if text_capture is None or text_capture.status in {"partial", "missing"}:
        reasons.append("text_capture_incomplete")

    text_results = [
        result
        for result in bundle.tool_results
        if result.tool_name == "analyze_text_intent"
    ]
    intent_evaluable = any(
        result.status in {"ok", "degraded"}
        for result in text_results
    )
    if not text_results:
        reasons.append("text_intent_missing")
    elif not intent_evaluable:
        reasons.append("text_intent_unavailable")

    image_capture = post.capture_status.modalities.get("image")
    image_was_provided = (
        image_capture is not None
        and image_capture.status != "not_applicable"
    )
    explicit_disclosure_found = any(
        item.kind == "explicit_ad_marker" for item in bundle.items
    )
    unsupported_media_present = any(
        item.type != "image" for item in post.media
    )
    if unsupported_media_present and not explicit_disclosure_found:
        reasons.append("unsupported_media_for_disclosure")
    image_results = [
        result
        for result in bundle.tool_results
        if result.tool_name in _IMAGE_TOOLS
    ]
    image_is_critical = image_was_provided and not explicit_disclosure_found
    if image_is_critical and image_capture.status in {"partial", "missing"}:
        reasons.append("image_capture_incomplete")
    if image_is_critical and not image_results:
        reasons.append("image_evidence_missing")
    if image_is_critical and any(
        result.status == "error" for result in image_results
    ):
        reasons.append("image_tool_error")
    if image_is_critical and any(
        result.status == "skipped" for result in image_results
    ):
        reasons.append("image_tool_unavailable")
    if image_is_critical:
        reasons.extend(non_disclosure_assessment_reasons(post, bundle))

    tool_reported_conflict = any(
        result.tool_name == "image_text_consistency"
        and result.payload.get("relation") == "conflicting"
        for result in bundle.tool_results
    )
    if bundle.conflicts or tool_reported_conflict:
        reasons.append("evidence_conflict")

    reason_codes = list(dict.fromkeys(reasons))
    return EvidenceAdequacyResult(
        intent_evaluable=intent_evaluable,
        review_required=bool(reason_codes),
        reason_codes=reason_codes,
    )

"""Evidence-adequacy gate for the deterministic P2.5 judgment baseline."""
from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from ..contracts.evidence import EvidenceBundle
from ..contracts.post import PostRecord
from ..tools.contracts import ToolResult
from .post_tools import _image_call_id, _is_local_file


_IMAGE_TOOLS = {
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
}


def _local_image_media(post: PostRecord):
    return [
        item
        for item in post.media
        if item.type == "image" and _is_local_file(item.ref)
    ]


def _ocr_capability_is_available(result: ToolResult) -> bool:
    vision_context = result.payload.get("vision_context") or {}
    capabilities = vision_context.get("capabilities") or {}
    return capabilities.get("ocr") is True


def _result_media_candidates(
    result: ToolResult,
    post: PostRecord,
) -> list[int]:
    """Resolve one OCR result to its source media without guessing."""

    images = _local_image_media(post)
    payload = result.payload or {}
    media_id = payload.get("media_id")
    media_ref = payload.get("media_ref")
    declared_identity = media_id is not None or media_ref is not None
    candidates = list(range(len(images)))
    if media_id is not None:
        candidates = [
            index
            for index in candidates
            if images[index].media_id == str(media_id)
        ]
    if media_ref is not None:
        candidates = [
            index
            for index in candidates
            if images[index].ref == str(media_ref)
        ]
    if declared_identity:
        return candidates

    call_id = result.call_id
    if not call_id:
        return []
    resolved = []
    for image_index, image in enumerate(images):
        expected = _image_call_id(
            "ocr_extract",
            image,
            image_index,
            len(images),
        )
        if call_id == expected:
            resolved.append(image_index)
    return resolved


def _ocr_coverage_reasons(
    post: PostRecord,
    ocr_results: list[ToolResult],
) -> list[str]:
    """Require one successful, OCR-capable result for every local image."""

    images = _local_image_media(post)
    if not images:
        return []

    reasons: list[str] = []
    matched: dict[int, ToolResult] = {}
    duplicate = False
    unresolved = False
    for result in ocr_results:
        candidates = _result_media_candidates(result, post)
        if len(candidates) != 1:
            unresolved = True
            continue
        image_index = candidates[0]
        if image_index in matched:
            duplicate = True
            continue
        matched[image_index] = result

    if len(images) == 1 and len(ocr_results) == 1:
        # Existing callers and stored bundles may predate per-result media
        # identity. Keep that one-image contract while validating the result.
        payload = ocr_results[0].payload or {}
        has_identity = any(
            key in payload for key in ("media_id", "media_ref")
        )
        if not matched and not has_identity:
            matched[0] = ocr_results[0]
            unresolved = False

    all_image_refs = [
        item.ref for item in post.media if item.type == "image"
    ]
    covered_refs = [images[index].ref for index in matched]
    if (
        unresolved
        or duplicate
        or Counter(covered_refs) != Counter(all_image_refs)
    ):
        reasons.append("image_coverage_incomplete")

    for result in matched.values():
        if result.status == "error":
            reasons.append("image_tool_error")
        elif result.status == "skipped":
            reasons.append("image_tool_unavailable")
        elif result.status != "ok" or not _ocr_capability_is_available(result):
            reasons.append("image_ocr_unavailable")
    return reasons


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
    ocr_results: list[ToolResult] = [
        result
        for result in bundle.tool_results
        if result.tool_name == "ocr_extract"
    ]
    local_images = _local_image_media(post)
    reasons = []
    if len(local_images) != len(image_media):
        reasons.append("image_coverage_incomplete")
    if not ocr_results:
        reasons.append("image_ocr_missing")
    reasons.extend(_ocr_coverage_reasons(post, ocr_results))
    return list(dict.fromkeys(reasons))


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
    if text_capture is None or text_capture.status in {
        "partial",
        "missing",
        "unsupported",
    }:
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
        and image_capture.status not in {"not_applicable", "unsupported"}
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
    if image_is_critical and any(
        not _is_local_file(item.ref)
        for item in post.media
        if item.type == "image"
    ):
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

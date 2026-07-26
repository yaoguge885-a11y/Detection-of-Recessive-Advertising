"""Normalize seven-tool results into traceable evidence without inventing facts."""
from __future__ import annotations

import hashlib
import json

from ..contracts.evidence import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceModalityCoverage,
)
from ..contracts.post import PostRecord
from ..tools.contracts import ToolEvidence, ToolResult
from ..tools.keywords import EXPLICIT_AD_MARKERS


_SUPPORTING_KINDS = {
    "explicit_ad_marker",
    "soft_ad_signal",
    "commercial_object",
    "brand_candidate",
    "comment_anomaly",
}
_SUPPORTING_KEYWORDS = {
    "promotion_words",
    "price_mentions",
    "urgency_expressions",
    "brand_mentions",
    "action_words",
}
_NON_EVIDENCE_KINDS = {"absence", "insufficient"}
_CAPTURE_TO_COVERAGE = {
    "complete": "covered",
    "partial": "partial",
    "missing": "missing",
    "not_applicable": "not_applicable",
}
_MODALITY_MAP = {
    "text": "text",
    "image": "image",
    "comment": "comment",
    "history": "history",
    "metadata": "metadata",
}


def _source_type(source: str) -> str:
    lowered = source.lower()
    if "comment" in lowered:
        return "comment"
    if "history" in lowered or "related_post" in lowered:
        return "history"
    if any(part in lowered for part in ("image", "media", "ocr", "yolo")):
        return "image"
    if "text" in lowered:
        return "text"
    return "metadata"


def _polarity(kind: str) -> str:
    if kind in _SUPPORTING_KINDS:
        return "supports"
    if kind.startswith("keyword:"):
        dimension = kind.split(":", 1)[1]
        if dimension in _SUPPORTING_KEYWORDS:
            return "supports"
    return "neutral"


def _evidence_id(
    result: ToolResult,
    evidence: ToolEvidence,
    index: int,
) -> str:
    payload = {
        "tool_name": result.tool_name,
        "call_id": result.call_id,
        "index": index,
        "evidence": evidence.model_dump(mode="json"),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"ev_{result.tool_name}_{hashlib.sha256(canonical).hexdigest()[:16]}"


def evidence_items_from_tool_result(
    result: ToolResult,
) -> list[EvidenceItem]:
    """Convert usable observations; missing/error/absence stays non-evidence."""

    if result.status in {"skipped", "error"}:
        return []
    limitations = [
        *result.warnings,
        *(item.message for item in result.limitations),
    ]
    items = []
    for index, evidence in enumerate(result.evidence):
        if evidence.kind in _NON_EVIDENCE_KINDS:
            continue
        items.append(_item_from_observation(
            result,
            evidence,
            index,
            limitations,
        ))
        marker = None
        if (
            result.tool_name == "ocr_extract"
            and evidence.kind == "ocr_text"
            and evidence.quote
        ):
            marker = next(
                (
                    value
                    for value in EXPLICIT_AD_MARKERS
                    if value in evidence.quote
                ),
                None,
            )
        if marker is not None:
            derived = evidence.model_copy(update={
                "kind": "explicit_ad_marker",
                "quote": marker,
            })
            items.append(_item_from_observation(
                result,
                derived,
                10_000 + index,
                limitations,
            ))
    return items


def _item_from_observation(
    result: ToolResult,
    evidence: ToolEvidence,
    index: int,
    limitations: list[str],
) -> EvidenceItem:
    strength = (
        evidence.score
        if evidence.score is not None
        else result.score
    )
    return EvidenceItem(
        evidence_id=_evidence_id(result, evidence, index),
        kind=evidence.kind,
        source=evidence.source,
        tool_name=result.tool_name,
        tool_version=result.tool_version,
        call_id=result.call_id,
        quote=evidence.quote,
        score=strength,
        span=evidence.span,
        bbox=evidence.bbox,
        related_post_id=evidence.related_post_id,
        comment_ids=evidence.comment_ids,
        polarity=_polarity(evidence.kind),
        strength=strength,
        source_type=_source_type(evidence.source),
        source_ref=evidence.source,
        producer=f"tool:{result.tool_name}",
        producer_version=result.tool_version,
        status="degraded"
        if result.status == "degraded"
        else "observed",
        limitations=limitations,
        metadata={"result_status": result.status},
    )


def _missing_requirements(
    post: PostRecord,
    results: list[ToolResult],
) -> list[str]:
    missing = []
    for modality, capture in post.capture_status.modalities.items():
        if capture.status not in {"partial", "missing"}:
            continue
        if capture.missing_fields:
            missing.extend(
                f"capture:{modality}:{capture.status}:{field}"
                for field in capture.missing_fields
            )
        else:
            missing.append(f"capture:{modality}:{capture.status}")
    missing.extend(
        f"tool:{result.tool_name}:{result.status}"
        for result in results
        if result.status in {"skipped", "error"}
    )
    return list(dict.fromkeys(missing))


def build_evidence_bundle(
    post: PostRecord,
    results: list[ToolResult],
) -> EvidenceBundle:
    """Build evidence, raw outcomes, coverage, and explicit missing state."""

    items = [
        item
        for result in results
        for item in evidence_items_from_tool_result(result)
    ]
    ids_by_modality: dict[str, list[str]] = {}
    for item in items:
        ids_by_modality.setdefault(item.source_type, []).append(
            item.evidence_id
        )
    coverage = [
        EvidenceModalityCoverage(
            modality=_MODALITY_MAP[modality],
            status=_CAPTURE_TO_COVERAGE[capture.status],
            evidence_ids=ids_by_modality.get(
                _MODALITY_MAP[modality],
                [],
            ),
        )
        for modality, capture in post.capture_status.modalities.items()
    ]
    limitations = [
        limitation
        for result in results
        for limitation in result.limitations
    ]
    return EvidenceBundle(
        post_id=post.post_id,
        items=items,
        tool_results=results,
        limitations=limitations,
        coverage=coverage,
        missing_requirements=_missing_requirements(post, results),
    )

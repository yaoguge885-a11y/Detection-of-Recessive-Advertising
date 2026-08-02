"""Conservative deterministic judgment over normalized evidence."""
from __future__ import annotations

from ..contracts.evidence import EvidenceBundle
from ..contracts.post import PostRecord
from ..contracts.verdict import (
    CommercialIntent,
    CreatorShiftSummary,
    DisclosureEvidence,
    VerdictReport,
)
from .adequacy import (
    assess_evidence_adequacy,
    non_disclosure_assessment_reasons,
)


_METHOD = "deterministic_baseline_v1"


def _usable_text_result(bundle: EvidenceBundle):
    return next(
        (
            result
            for result in bundle.tool_results
            if result.tool_name == "analyze_text_intent"
            and result.status in {"ok", "degraded"}
        ),
        None,
    )


def assess_commercial_intent(
    bundle: EvidenceBundle,
) -> CommercialIntent:
    """Use the stable text-intent score as the P2.5 primary baseline."""

    text_result = _usable_text_result(bundle)
    supporting_ids = [
        item.evidence_id
        for item in bundle.items
        if item.polarity == "supports"
    ]
    explicit_ids = [
        item.evidence_id
        for item in bundle.items
        if item.kind == "explicit_ad_marker"
    ]
    if text_result is None:
        return CommercialIntent(
            status="uncertain",
            score=None,
            evidence_ids=supporting_ids,
        )
    score = text_result.score
    if explicit_ids:
        return CommercialIntent(
            status="present",
            score=max(score or 0.0, 0.75),
            evidence_ids=supporting_ids,
        )
    if score is None:
        status = "uncertain"
    elif score >= 0.50:
        status = "present"
    elif score < 0.35:
        status = "absent"
    else:
        status = "uncertain"
    return CommercialIntent(
        status=status,
        score=score,
        evidence_ids=supporting_ids,
    )


def assess_disclosure(
    post: PostRecord,
    bundle: EvidenceBundle,
) -> DisclosureEvidence:
    """Never infer no disclosure when capture was not sufficient."""

    explicit = [
        item
        for item in bundle.items
        if item.kind == "explicit_ad_marker"
    ]
    if explicit:
        strengths = [
            item.strength
            for item in explicit
            if item.strength is not None
        ]
        return DisclosureEvidence(
            status="disclosed",
            confidence=max(strengths, default=0.8),
            evidence_ids=[item.evidence_id for item in explicit],
        )
    limitations = non_disclosure_assessment_reasons(post, bundle)
    if not limitations:
        return DisclosureEvidence(
            status="not_disclosed",
            confidence=0.8,
            evidence_ids=[],
        )
    return DisclosureEvidence(
        status="unknown",
        confidence=None,
        evidence_ids=[],
        limitations=limitations,
    )


def _confidence(
    label: str,
    intent: CommercialIntent,
    disclosure: DisclosureEvidence,
) -> float:
    intent_score = intent.score if intent.score is not None else 0.5
    if label == "需复核":
        return round(min(intent_score, 0.5), 3)
    if label == "非广":
        return round(max(0.0, 1.0 - intent_score), 3)
    if label == "明广":
        return round(
            min(intent_score, disclosure.confidence or intent_score),
            3,
        )
    return round(
        min(intent_score, disclosure.confidence or intent_score),
        3,
    )


def build_verdict_report(
    post: PostRecord,
    bundle: EvidenceBundle,
    *,
    creator_shift: CreatorShiftSummary | None = None,
) -> VerdictReport:
    """Apply the documented label table after the adequacy gate."""

    adequacy = assess_evidence_adequacy(post, bundle)
    intent = assess_commercial_intent(bundle)
    disclosure = assess_disclosure(post, bundle)
    if adequacy.review_required:
        label = "需复核"
    elif intent.status == "absent":
        label = "非广"
    elif intent.status == "present" and disclosure.status == "disclosed":
        label = "明广"
    elif (
        intent.status == "present"
        and disclosure.status == "not_disclosed"
    ):
        label = "暗广"
    else:
        label = "需复核"

    reasons = [
        *adequacy.reason_codes,
        f"commercial_intent:{intent.status}",
        f"disclosure:{disclosure.status}",
    ]
    creator_shift_ids = [
        item.evidence_id
        for item in bundle.items
        if item.kind == "creator_shift"
    ]
    return VerdictReport(
        post_id=post.post_id,
        label=label,
        confidence=_confidence(label, intent, disclosure),
        review_required=label == "需复核",
        commercial_intent=intent,
        disclosure=disclosure,
        creator_shift=creator_shift,
        creator_shift_evidence_ids=creator_shift_ids,
        evidence_ids=[item.evidence_id for item in bundle.items],
        reasons=reasons,
        law_evidence=[],
        judgment_method=_METHOD,
    )

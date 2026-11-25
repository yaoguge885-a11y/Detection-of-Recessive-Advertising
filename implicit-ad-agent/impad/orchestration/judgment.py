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
    unresolved = any(item.kind == "disclosure_candidate" for item in bundle.items)
    rejected = any(
        result.tool_name == "verify_disclosure"
        and result.status == "ok"
        and result.payload.get("decision") == "rejected"
        for result in bundle.tool_results
    )
    if unresolved and not rejected:
        limitations = [*limitations, "ambiguous_disclosure"]
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


def _recurring_weak_cues(
    post: PostRecord, bundle: EvidenceBundle, history: CreatorShiftSummary | None,
) -> bool:
    """Check whether only familiar soft-ad wording supports commercial intent."""
    if history is None or history.status != "sufficient":
        return False
    cues = {item.quote for item in bundle.items if item.kind == "soft_ad_signal" and item.quote}
    if not cues or any(
        item.polarity == "supports" and (
            item.source_type != "text" or item.quote not in cues
            or item.kind not in {"soft_ad_signal", "keyword:promotion_words"}
        )
        for item in bundle.items
    ):
        return False
    valid_ids = set(history.history_post_ids)
    prior = [item for item in post.history if item.post_id in valid_ids]
    recent = prior[-history.required_history:]
    return len(recent) == history.required_history and all(
        all(cue in item.text for cue in cues) for item in recent
    )


def build_verdict_report(
    post: PostRecord,
    bundle: EvidenceBundle,
    *,
    creator_shift: CreatorShiftSummary | None = None,
    use_history_for_review: bool = False,
) -> VerdictReport:
    """Apply the documented label table after the adequacy gate."""

    adequacy = assess_evidence_adequacy(post, bundle)
    intent = assess_commercial_intent(bundle)
    disclosure = assess_disclosure(post, bundle)
    recurring = (
        use_history_for_review and intent.status == "present"
        and disclosure.status == "not_disclosed"
        and _recurring_weak_cues(post, bundle, creator_shift)
    )
    if recurring:
        intent = CommercialIntent(
            status="uncertain",
            evidence_ids=[*intent.evidence_ids,
                          *(item.evidence_id for item in bundle.items if item.kind == "creator_shift")],
        )
    if adequacy.review_required or "ambiguous_disclosure" in disclosure.limitations:
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
        *(["commercial_wording_recurs_in_history"] if recurring else []),
        *[reason for reason in disclosure.limitations if reason == "ambiguous_disclosure"],
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
        judgment_method="adaptive_evidence_v2" if use_history_for_review else _METHOD,
    )

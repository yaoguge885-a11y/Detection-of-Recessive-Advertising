"""Normalize input and build a deterministic capability plan."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..adapters import (
    post_record_from_content_record,
    post_record_from_manual,
)
from ..contracts import PostRecord, RunMetadata
from ..orchestration import (
    CapabilityPlanner,
    capability_context_from_post,
)
from ..state import AdCheckState


_NLP_TOOLS = {
    "analyze_text_intent",
    "sentiment_curve",
    "comment_anomaly",
}
_VISION_TOOLS = {
    "ocr_extract",
    "image_text_consistency",
    "detect_logo_product",
}
_BEHAVIOR_TOOLS = {"topic_drift"}
_P1_SOURCE_TYPES = {
    "public_dataset",
    "manual_public_collection",
    "authorized_export",
    "synthetic",
}
_P1_SCHEMA_VERSIONS = {"1.0", "1.1", "1.2"}
_EVIDENCE_STRATEGIES = {"adaptive", "fixed"}


def _evidence_strategy(state: AdCheckState) -> str:
    strategy = state.get("evidence_strategy", "adaptive")
    return strategy if strategy in _EVIDENCE_STRATEGIES else "adaptive"


def _has_confirmed_disclosure(state: AdCheckState) -> bool:
    bundle = state.get("evidence_bundle")
    return bundle is not None and any(
        item.kind == "explicit_ad_marker" for item in bundle.items
    )


def _needs_followup_evidence(state: AdCheckState) -> bool:
    result = next((item for item in state.get("tool_results", [])
                   if item.tool_name == "analyze_text_intent"), None)
    if result is None or result.status not in {"ok", "degraded"}:
        return True
    return bool(result.score and result.score >= 0.35) or any(
        item.kind in {"disclosure_candidate", "soft_ad_signal",
                      "keyword:urgency_expressions", "keyword:action_words"}
        for item in result.evidence
    )


def normalize_post_record(raw: dict | PostRecord) -> PostRecord:
    if isinstance(raw, PostRecord):
        return raw
    is_p1 = raw.get("schema_version") in _P1_SCHEMA_VERSIONS or (
        "blogger_id" in raw
        and ("provenance" in raw or "privacy" in raw)
    ) or (
        raw.get("source_type") in _P1_SOURCE_TYPES
        and "blogger_id" in raw
        and all(
            field in raw
            for field in ("post_id", "platform", "media")
        )
    )
    if is_p1:
        return post_record_from_content_record(raw)
    return post_record_from_manual(raw)


def supervisor(state: AdCheckState) -> AdCheckState:
    post = normalize_post_record(state.get("post", {}))
    context = capability_context_from_post(post)
    capability_plan = CapabilityPlanner().plan(context)
    evidence_strategy = _evidence_strategy(state)
    available = set(capability_plan.available_tools)
    plan = []
    if available & _NLP_TOOLS:
        plan.append("nlp")
    if available & _VISION_TOOLS:
        plan.append("vision")
    if available & _BEHAVIOR_TOOLS:
        plan.append("behavior")
    plan.append("creator_shift")
    run_id = f"run_{uuid4().hex}"
    return {
        "post_record": post,
        "capture_status": post.capture_status,
        "capability_plan": capability_plan,
        "evidence_strategy": evidence_strategy,
        "plan": plan,
        "tool_results": [],
        "function_traces": [],
        "run_events": [],
        "run_metadata": RunMetadata(
            run_id=run_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            runtime_mode=state.get("runtime_mode", "local"),
            planner_version=f"capability_planner_v2_{evidence_strategy}",
        ),
        "agent_outputs": {},
        "agent_votes": {},
        "evidence": [
            "[Supervisor] capability plan: "
            + ", ".join(capability_plan.available_tools)
        ],
    }


def route_next(state: AdCheckState) -> str:
    """Route expert groups, optionally prioritizing evidence by signal."""

    plan = state.get("plan") or []
    if not plan:
        return "judge"
    if _evidence_strategy(state) == "fixed":
        return plan[0]

    # Text is the first-pass gate whenever it is available.  If it is not
    # available, preserve the original deterministic order for the remaining
    # groups rather than silently dropping a modality.
    if "nlp" in plan:
        return "nlp"

    # Images can carry a disclosure marker that is absent from the text. Keep
    # the eligible vision group in the route even when text intent is weak.
    if "vision" in plan:
        return "vision"

    if "behavior" in plan and not _has_confirmed_disclosure(state) and _needs_followup_evidence(state):
        return "behavior"
    if "creator_shift" in plan:
        return "creator_shift"
    return "judge"

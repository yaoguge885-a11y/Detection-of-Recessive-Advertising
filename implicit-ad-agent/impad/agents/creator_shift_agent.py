"""Dedicated deterministic CreatorShift evidence node."""
from __future__ import annotations

from ..creator_shift import (
    assess_post_creator_shift,
    creator_shift_evidence,
)
from ..orchestration import build_evidence_bundle
from ..state import AdCheckState


def creator_shift_agent(state: AdCheckState) -> AdCheckState:
    """Record history sufficiency and neutral shift evidence."""

    post = state["post_record"]
    summary = assess_post_creator_shift(post)
    item = creator_shift_evidence(summary)
    supplemental = [item] if item is not None else []
    bundle = build_evidence_bundle(
        post,
        list(state.get("tool_results", [])),
        supplemental_items=supplemental,
    )
    outputs = {
        **state.get("agent_outputs", {}),
        "creator_shift": {
            "status": summary.status,
            "history_count": summary.history_count,
            "required_history": summary.required_history,
            "evidence_count": len(supplemental),
        },
    }
    return {
        "creator_shift_summary": summary,
        "supplemental_evidence": supplemental,
        "evidence_bundle": bundle,
        "agent_outputs": outputs,
        "agent_votes": outputs,
        "plan": [
            item
            for item in state.get("plan", [])
            if item != "creator_shift"
        ],
    }

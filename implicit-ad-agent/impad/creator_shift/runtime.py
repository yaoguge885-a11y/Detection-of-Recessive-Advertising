"""Runtime adapter from normalized posts to CreatorShift evidence."""
from __future__ import annotations

import hashlib
import json

from ..contracts.evidence import EvidenceItem
from ..contracts.post import PostRecord
from ..contracts.verdict import CreatorShiftSummary
from ..tools.keywords import compute_keyword_weights
from .baselines import PoolingMethod, pool_history
from .contracts import CreatorHistoryView, HistoryFeature
from .shift import calculate_shift


FEATURE_VERSION = "keyword_weights_v1"
RUNTIME_VERSION = "creator_shift_runtime_v1"


def _summary(
    *,
    status: str,
    history_count: int,
    required_history: int,
    limitations: list[str],
) -> CreatorShiftSummary:
    return CreatorShiftSummary(
        status=status,
        history_count=history_count,
        required_history=required_history,
        limitations=limitations,
    )


def assess_post_creator_shift(
    post: PostRecord,
    *,
    method: PoolingMethod = "ema",
    minimum_history: int = 3,
    alpha: float = 0.5,
) -> CreatorShiftSummary:
    """Build deterministic shift evidence without changing classification."""

    timestamped = [
        item for item in post.history if item.published_at is not None
    ]
    excluded = len(post.history) - len(timestamped)
    limitations = []
    if excluded:
        limitations.append(
            f"excluded_history_without_timestamp:{excluded}"
        )
    if post.published_at is None:
        return _summary(
            status="unavailable",
            history_count=len(timestamped),
            required_history=minimum_history,
            limitations=[
                *limitations,
                "target_timestamp_unavailable",
            ],
        )

    view = CreatorHistoryView(
        target_post_id=post.post_id,
        target_creator_id=post.creator_id,
        target_time=post.published_at,
        minimum_history=minimum_history,
        history=[
            HistoryFeature(
                post_id=item.post_id,
                creator_id=item.creator_id,
                published_at=item.published_at,
                features=compute_keyword_weights(item.text),
            )
            for item in timestamped
        ],
    )
    sufficiency = view.sufficiency
    if sufficiency.status != "sufficient":
        return _summary(
            status=sufficiency.status,
            history_count=sufficiency.observed_count,
            required_history=sufficiency.required_count,
            limitations=[*limitations, sufficiency.reason],
        )

    pooled = pool_history(view, method=method, alpha=alpha)
    result = calculate_shift(
        compute_keyword_weights(post.text),
        pooled,
    )
    return CreatorShiftSummary(
        status="sufficient",
        history_count=result.history_count,
        required_history=minimum_history,
        pooling_method=result.pooling_method,
        shift_score=result.shift_score,
        history_post_ids=result.history_post_ids,
        window_start=result.window_start,
        window_end=result.window_end,
        top_features=result.top_features,
        feature_deltas=result.feature_deltas,
        limitations=[*limitations, *result.limitations],
    )


def creator_shift_evidence(
    summary: CreatorShiftSummary,
) -> EvidenceItem | None:
    """Convert only sufficient numeric shift into neutral history evidence."""

    if summary.status != "sufficient":
        return None
    metadata = summary.model_dump(mode="json")
    canonical = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    evidence_id = (
        "ev_creator_shift_"
        + hashlib.sha256(canonical).hexdigest()[:16]
    )
    return EvidenceItem(
        evidence_id=evidence_id,
        kind="creator_shift",
        source="creator.history",
        tool_name="creator_shift_baseline",
        tool_version=summary.runtime_version,
        score=summary.shift_score,
        metadata=metadata,
        polarity="neutral",
        strength=summary.shift_score,
        source_type="history",
        source_ref="creator.history",
        producer="agent:creator_shift",
        producer_version=summary.runtime_version,
        limitations=summary.limitations,
    )

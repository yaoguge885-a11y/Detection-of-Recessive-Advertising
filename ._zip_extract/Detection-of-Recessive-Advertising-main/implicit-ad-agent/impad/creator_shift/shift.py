"""Interpretable shift evidence over a pooled creator history."""
from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, Field

from .baselines import PooledHistory, PoolingMethod


class CreatorShiftResult(BaseModel):
    """Numeric historical deviation; never a final advertisement label."""

    shift_score: float = Field(ge=0)
    feature_deltas: dict[str, float] = Field(min_length=1)
    top_features: list[str] = Field(min_length=1)
    pooling_method: PoolingMethod
    history_count: int = Field(ge=1)
    history_post_ids: list[str] = Field(min_length=1)
    window_start: datetime
    window_end: datetime
    limitations: list[str] = Field(min_length=1)


def calculate_shift(
    target_features: dict[str, float],
    pooled: PooledHistory,
) -> CreatorShiftResult:
    """Compare a target feature vector with one validated history baseline."""

    if set(target_features) != set(pooled.values):
        raise ValueError("target and pooled feature keys must match")
    if any(not math.isfinite(value) for value in target_features.values()):
        raise ValueError("target features must be finite")
    names = sorted(target_features)
    deltas = {
        name: target_features[name] - pooled.values[name]
        for name in names
    }
    score = sum(abs(delta) for delta in deltas.values()) / len(deltas)
    top_features = sorted(
        names,
        key=lambda name: (-abs(deltas[name]), name),
    )
    return CreatorShiftResult(
        shift_score=score,
        feature_deltas=deltas,
        top_features=top_features,
        pooling_method=pooled.method,
        history_count=pooled.history_count,
        history_post_ids=pooled.history_post_ids,
        window_start=pooled.window_start,
        window_end=pooled.window_end,
        limitations=[
            "Simple history pooling baseline; shift is not a calibrated "
            "advertising probability."
        ],
    )

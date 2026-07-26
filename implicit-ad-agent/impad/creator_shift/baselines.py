"""Simple, reproducible history pooling baselines for CreatorShift."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import CreatorHistoryView


PoolingMethod = Literal["mean", "max", "ema"]


class HistoryPoolingError(ValueError):
    """Raised when a validated view still cannot support pooling."""


class PooledHistory(BaseModel):
    """One deterministic baseline vector with its temporal provenance."""

    method: PoolingMethod
    values: dict[str, float] = Field(min_length=1)
    history_post_ids: list[str] = Field(min_length=1)
    history_count: int = Field(ge=1)
    window_start: datetime
    window_end: datetime
    alpha: float | None = Field(default=None, gt=0, le=1)


def pool_history(
    view: CreatorHistoryView,
    *,
    method: PoolingMethod,
    alpha: float = 0.5,
) -> PooledHistory:
    """Pool a sufficient chronological history without classifying a post."""

    sufficiency = view.sufficiency
    if sufficiency.status != "sufficient":
        raise HistoryPoolingError(
            f"history is {sufficiency.status}; pooling is not allowed"
        )
    if method not in {"mean", "max", "ema"}:
        raise ValueError(f"unsupported pooling method: {method}")
    if method == "ema" and not 0 < alpha <= 1:
        raise ValueError("alpha must be greater than 0 and at most 1")

    expected_keys = set(view.history[0].features)
    if any(set(item.features) != expected_keys for item in view.history):
        raise HistoryPoolingError(
            "all history feature keys must match before pooling"
        )
    names = sorted(expected_keys)

    if method == "mean":
        values = {
            name: sum(item.features[name] for item in view.history)
            / len(view.history)
            for name in names
        }
    elif method == "max":
        values = {
            name: max(item.features[name] for item in view.history)
            for name in names
        }
    else:
        values = dict(view.history[0].features)
        for item in view.history[1:]:
            values = {
                name: (
                    alpha * item.features[name]
                    + (1 - alpha) * values[name]
                )
                for name in names
            }

    return PooledHistory(
        method=method,
        values={name: values[name] for name in names},
        history_post_ids=[item.post_id for item in view.history],
        history_count=len(view.history),
        window_start=view.history[0].published_at,
        window_end=view.history[-1].published_at,
        alpha=alpha if method == "ema" else None,
    )

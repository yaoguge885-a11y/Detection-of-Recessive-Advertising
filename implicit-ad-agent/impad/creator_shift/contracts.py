"""P1-independent temporal contracts for CreatorShift experiments."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class HistoryFeature(BaseModel):
    """Numeric features from one historical post."""

    post_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    published_at: datetime
    features: dict[str, float] = Field(min_length=1)

    @field_validator("published_at")
    @classmethod
    def published_at_has_timezone(cls, value: datetime):
        return _timezone_aware(value)

    @field_validator("features")
    @classmethod
    def features_are_finite(cls, value: dict[str, float]):
        if any(not math.isfinite(number) for number in value.values()):
            raise ValueError("history features must be finite")
        return value


class HistorySufficiency(BaseModel):
    """Whether a valid history window supports shift calculation."""

    status: Literal["sufficient", "insufficient", "unavailable"]
    observed_count: int = Field(ge=0)
    required_count: int = Field(ge=1)
    reason: str = Field(min_length=1)


class CreatorHistoryView(BaseModel):
    """Validated same-creator history strictly before one target post."""

    target_post_id: str = Field(min_length=1)
    target_creator_id: str = Field(min_length=1)
    target_time: datetime
    minimum_history: int = Field(default=3, ge=1)
    history: list[HistoryFeature] = Field(default_factory=list)

    @field_validator("target_time")
    @classmethod
    def target_time_has_timezone(cls, value: datetime):
        return _timezone_aware(value)

    @model_validator(mode="after")
    def validate_window(self):
        ids = [item.post_id for item in self.history]
        if len(ids) != len(set(ids)):
            raise ValueError("history post_id values must be unique")
        if self.target_post_id in ids:
            raise ValueError("history cannot contain the target post")
        if any(
            item.creator_id != self.target_creator_id
            for item in self.history
        ):
            raise ValueError("all history records must use the same creator")
        if any(
            item.published_at >= self.target_time
            for item in self.history
        ):
            raise ValueError(
                "history timestamps must be strictly earlier than target_time"
            )
        self.history = sorted(
            self.history,
            key=lambda item: (item.published_at, item.post_id),
        )
        return self

    @property
    def sufficiency(self) -> HistorySufficiency:
        observed = len(self.history)
        if observed == 0:
            return HistorySufficiency(
                status="unavailable",
                observed_count=0,
                required_count=self.minimum_history,
                reason="No valid creator history is available.",
            )
        if observed < self.minimum_history:
            return HistorySufficiency(
                status="insufficient",
                observed_count=observed,
                required_count=self.minimum_history,
                reason="Valid history is below the configured minimum.",
            )
        return HistorySufficiency(
            status="sufficient",
            observed_count=observed,
            required_count=self.minimum_history,
            reason="Valid same-creator history meets the minimum.",
        )

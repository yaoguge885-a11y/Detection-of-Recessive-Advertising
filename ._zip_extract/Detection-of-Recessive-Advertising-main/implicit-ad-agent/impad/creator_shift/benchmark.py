"""Version-bound synthetic benchmark for CreatorShift engineering behavior."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts.post import PostRecord
from .baselines import PoolingMethod
from .runtime import (
    FEATURE_VERSION,
    RUNTIME_VERSION,
    assess_post_creator_shift,
)


METHODS: tuple[PoolingMethod, ...] = ("mean", "max", "ema")


class CreatorShiftBenchmarkFixture(BaseModel):
    """Versioned normalized posts for zero-network engineering evaluation."""

    model_config = ConfigDict(extra="forbid")

    benchmark_version: str = Field(min_length=1)
    feature_version: Literal["keyword_weights_v1"]
    posts: list[PostRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def target_post_ids_are_unique(self):
        ids = [post.post_id for post in self.posts]
        if len(ids) != len(set(ids)):
            raise ValueError("post_id values must be unique")
        return self


class CreatorShiftBenchmarkCase(BaseModel):
    """One post/method outcome without a classification claim."""

    case_id: str = Field(min_length=1)
    method: PoolingMethod
    status: Literal["sufficient", "insufficient", "unavailable"]
    history_count: int = Field(ge=0)
    shift_score: float | None = Field(default=None, ge=0, le=1)
    top_features: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CreatorShiftBenchmarkReport(BaseModel):
    """Reproducible P4 engineering benchmark report."""

    benchmark_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    fixture_sha256: str = Field(min_length=64, max_length=64)
    generated_at: datetime
    minimum_history: int = Field(ge=1)
    ema_alpha: float = Field(gt=0, le=1)
    methods: list[PoolingMethod]
    case_count: int = Field(ge=1)
    status_counts: dict[str, int]
    cases: list[CreatorShiftBenchmarkCase]


def _fixture_hash(fixture: CreatorShiftBenchmarkFixture) -> str:
    canonical = json.dumps(
        fixture.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_creator_shift_benchmark(
    fixture: CreatorShiftBenchmarkFixture,
    *,
    minimum_history: int = 3,
    ema_alpha: float = 0.5,
) -> CreatorShiftBenchmarkReport:
    """Run all simple baselines over explicit normalized fixture posts."""

    cases = []
    status_counts = {
        "sufficient": 0,
        "insufficient": 0,
        "unavailable": 0,
    }
    for post in fixture.posts:
        for method in METHODS:
            summary = assess_post_creator_shift(
                post,
                method=method,
                minimum_history=minimum_history,
                alpha=ema_alpha,
            )
            status_counts[summary.status] += 1
            cases.append(CreatorShiftBenchmarkCase(
                case_id=post.post_id,
                method=method,
                status=summary.status,
                history_count=summary.history_count,
                shift_score=summary.shift_score,
                top_features=summary.top_features,
                limitations=summary.limitations,
            ))

    return CreatorShiftBenchmarkReport(
        benchmark_version=fixture.benchmark_version,
        feature_version=fixture.feature_version,
        runtime_version=RUNTIME_VERSION,
        fixture_sha256=_fixture_hash(fixture),
        generated_at=datetime.now(timezone.utc),
        minimum_history=minimum_history,
        ema_alpha=ema_alpha,
        methods=list(METHODS),
        case_count=len(fixture.posts),
        status_counts=status_counts,
        cases=cases,
    )

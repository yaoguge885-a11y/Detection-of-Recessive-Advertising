"""Explicit pre-abstention predictions and risk-coverage evaluation."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .classification import GoldLabel


class CalibrationPrediction(BaseModel):
    """One explicit prediction before any review threshold is applied."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    true_label: GoldLabel
    predicted_label: GoldLabel
    decision_confidence: float = Field(ge=0, le=1)
    dark_ad_score: float = Field(ge=0, le=1)


class RiskCoveragePoint(BaseModel):
    """Observed error risk for one retained-confidence prefix."""

    retained_count: int = Field(ge=1)
    retained_sample_ids: list[str] = Field(min_length=1)
    coverage: float = Field(gt=0, le=1)
    risk: float = Field(ge=0, le=1)
    error_count: int = Field(ge=0)
    confidence_threshold: float = Field(ge=0, le=1)


def risk_coverage_curve(
    predictions: list[CalibrationPrediction],
) -> list[RiskCoveragePoint]:
    """Retain predictions from highest to lowest explicit confidence."""

    if not predictions:
        raise ValueError("at least one prediction is required")
    ordered = sorted(
        predictions,
        key=lambda item: (-item.decision_confidence, item.sample_id),
    )
    total = len(ordered)
    retained_ids = []
    errors = 0
    curve = []
    for index, item in enumerate(ordered, start=1):
        retained_ids.append(item.sample_id)
        if item.predicted_label != item.true_label:
            errors += 1
        curve.append(RiskCoveragePoint(
            retained_count=index,
            retained_sample_ids=list(retained_ids),
            coverage=index / total,
            risk=errors / index,
            error_count=errors,
            confidence_threshold=item.decision_confidence,
        ))
    return curve

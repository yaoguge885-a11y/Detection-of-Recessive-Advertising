"""Seeded bootstrap and selective-evaluation reports for P4 engineering."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import random

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .classification import (
    ClassificationMetrics,
    ClassificationPrediction,
    evaluate_classification,
)
from .selective import (
    CalibrationPrediction,
    RiskCoveragePoint,
    risk_coverage_curve,
)


METRIC_NAMES = (
    "macro_f1",
    "dark_ad_f1",
    "dark_ad_auprc",
    "dark_ad_ece",
    "dark_ad_brier",
)


class CalibrationEvaluationFixture(BaseModel):
    """Versioned pre-abstention predictions for engineering evaluation."""

    model_config = ConfigDict(extra="forbid")

    benchmark_version: str = Field(min_length=1)
    predictions: list[CalibrationPrediction] = Field(min_length=1)

    @model_validator(mode="after")
    def sample_ids_are_unique(self):
        ids = [item.sample_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("sample_id values must be unique")
        return self


class MetricInterval(BaseModel):
    """Point estimate and deterministic percentile bootstrap bounds."""

    estimate: float = Field(ge=0, le=1)
    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)


class CalibrationEvaluationReport(BaseModel):
    """Metrics plus uncertainty and risk-coverage engineering evidence."""

    benchmark_version: str = Field(min_length=1)
    generated_at: datetime
    sample_count: int = Field(ge=1)
    bootstrap_resamples: int = Field(ge=1)
    bootstrap_seed: int
    confidence_level: float = Field(gt=0, lt=1)
    metrics: ClassificationMetrics
    metric_intervals: dict[str, MetricInterval]
    risk_coverage: list[RiskCoveragePoint] = Field(min_length=1)


def _classification_predictions(
    predictions: list[CalibrationPrediction],
) -> list[ClassificationPrediction]:
    return [
        ClassificationPrediction(
            sample_id=item.sample_id,
            true_label=item.true_label,
            predicted_label=item.predicted_label,
            dark_ad_score=item.dark_ad_score,
        )
        for item in predictions
    ]


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return (
        ordered[lower_index] * (1 - fraction)
        + ordered[upper_index] * fraction
    )


def bootstrap_classification_intervals(
    predictions: list[CalibrationPrediction],
    *,
    resamples: int = 500,
    seed: int = 20260730,
    confidence_level: float = 0.95,
) -> dict[str, MetricInterval]:
    """Return seeded percentile intervals without inferring missing scores."""

    if not predictions:
        raise ValueError("at least one prediction is required")
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")

    rng = random.Random(seed)
    count = len(predictions)
    base = evaluate_classification(
        _classification_predictions(predictions)
    )
    samples = {name: [] for name in METRIC_NAMES}
    for _ in range(resamples):
        resampled = [
            predictions[rng.randrange(count)]
            for _ in range(count)
        ]
        metrics = evaluate_classification(
            _classification_predictions(resampled)
        )
        for name in METRIC_NAMES:
            samples[name].append(getattr(metrics, name))

    tail = (1 - confidence_level) / 2
    return {
        name: MetricInterval(
            estimate=getattr(base, name),
            lower=_percentile(values, tail),
            upper=_percentile(values, 1 - tail),
        )
        for name, values in samples.items()
    }


def build_calibration_report(
    fixture: CalibrationEvaluationFixture,
    *,
    bootstrap_resamples: int = 500,
    bootstrap_seed: int = 20260730,
    confidence_level: float = 0.95,
) -> CalibrationEvaluationReport:
    """Build a reproducible fixture report without choosing a threshold."""

    metrics = evaluate_classification(
        _classification_predictions(fixture.predictions)
    )
    intervals = bootstrap_classification_intervals(
        fixture.predictions,
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
        confidence_level=confidence_level,
    )
    return CalibrationEvaluationReport(
        benchmark_version=fixture.benchmark_version,
        generated_at=datetime.now(timezone.utc),
        sample_count=len(fixture.predictions),
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
        confidence_level=confidence_level,
        metrics=metrics,
        metric_intervals=intervals,
        risk_coverage=risk_coverage_curve(fixture.predictions),
    )

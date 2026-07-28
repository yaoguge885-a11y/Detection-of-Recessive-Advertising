"""Versioned classification error reports built from explicit predictions."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .classification import (
    ClassificationMetrics,
    ClassificationPrediction,
    evaluate_classification,
)


TRUE_LABELS = ("明广", "暗广", "非广")
PREDICTED_LABELS = ("明广", "暗广", "非广", "需复核")
TRUE_BINARY_LABELS = ("dark_ad", "not_dark_ad")
PREDICTED_BINARY_LABELS = (
    "dark_ad",
    "not_dark_ad",
    "review_required",
)


class ClassificationEvaluationFixture(BaseModel):
    """A versioned prediction set used for engineering evaluation."""

    model_config = ConfigDict(extra="forbid")

    benchmark_version: str = Field(min_length=1)
    predictions: list[ClassificationPrediction] = Field(min_length=1)

    @model_validator(mode="after")
    def sample_ids_are_unique(self):
        ids = [item.sample_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("sample_id values must be unique")
        return self


class ClassificationErrorReport(BaseModel):
    """Metrics, confusion counts, and stable error buckets."""

    benchmark_version: str = Field(min_length=1)
    generated_at: datetime
    metrics: ClassificationMetrics
    multiclass_confusion: dict[str, dict[str, int]]
    binary_confusion: dict[str, dict[str, int]]
    misclassified_sample_ids: list[str]
    review_sample_ids: list[str]
    error_buckets: dict[str, list[str]]


def _predicted_binary_label(item: ClassificationPrediction) -> str:
    if item.predicted_label == "需复核":
        return "review_required"
    if item.predicted_label == "暗广":
        return "dark_ad"
    return "not_dark_ad"


def build_classification_report(
    fixture: ClassificationEvaluationFixture,
    *,
    calibration_bins: int = 10,
) -> ClassificationErrorReport:
    """Build an error report without deriving missing model scores."""

    multiclass = {
        true_label: {
            predicted_label: 0
            for predicted_label in PREDICTED_LABELS
        }
        for true_label in TRUE_LABELS
    }
    binary = {
        true_label: {
            predicted_label: 0
            for predicted_label in PREDICTED_BINARY_LABELS
        }
        for true_label in TRUE_BINARY_LABELS
    }
    misclassified: list[str] = []
    review: list[str] = []
    buckets: dict[str, list[str]] = {}

    for item in fixture.predictions:
        multiclass[item.true_label][item.predicted_label] += 1
        true_binary = (
            "dark_ad" if item.true_label == "暗广" else "not_dark_ad"
        )
        binary[true_binary][_predicted_binary_label(item)] += 1
        if item.predicted_label == "需复核":
            review.append(item.sample_id)
        if item.predicted_label != item.true_label:
            misclassified.append(item.sample_id)
            key = f"{item.true_label}->{item.predicted_label}"
            buckets.setdefault(key, []).append(item.sample_id)

    return ClassificationErrorReport(
        benchmark_version=fixture.benchmark_version,
        generated_at=datetime.now(timezone.utc),
        metrics=evaluate_classification(
            fixture.predictions,
            calibration_bins=calibration_bins,
        ),
        multiclass_confusion=multiclass,
        binary_confusion=binary,
        misclassified_sample_ids=misclassified,
        review_sample_ids=review,
        error_buckets=dict(sorted(buckets.items())),
    )

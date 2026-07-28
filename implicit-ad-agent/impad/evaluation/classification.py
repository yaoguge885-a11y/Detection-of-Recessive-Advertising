"""Three-class, dark-ad, ranking, and calibration metrics without sklearn."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


GoldLabel = Literal["明广", "暗广", "非广"]
RuntimeLabel = Literal["明广", "暗广", "非广", "需复核"]


class ClassificationPrediction(BaseModel):
    sample_id: str = Field(min_length=1)
    true_label: GoldLabel
    predicted_label: RuntimeLabel
    dark_ad_score: float = Field(ge=0, le=1)


class ClassificationMetrics(BaseModel):
    sample_count: int = Field(ge=0)
    macro_f1: float = Field(ge=0, le=1)
    dark_ad_precision: float = Field(ge=0, le=1)
    dark_ad_recall: float = Field(ge=0, le=1)
    dark_ad_f1: float = Field(ge=0, le=1)
    dark_ad_auprc: float = Field(ge=0, le=1)
    dark_ad_ece: float = Field(ge=0, le=1)
    dark_ad_brier: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    review_rate: float = Field(ge=0, le=1)


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return _safe_div(2 * precision * recall, precision + recall)


def _average_precision(items: list[ClassificationPrediction]) -> float:
    positives = sum(item.true_label == "暗广" for item in items)
    if not positives:
        return 0.0
    ordered = sorted(items, key=lambda item: item.dark_ad_score, reverse=True)
    hits = 0
    precisions = []
    for rank, item in enumerate(ordered, start=1):
        if item.true_label == "暗广":
            hits += 1
            precisions.append(hits / rank)
    return sum(precisions) / positives


def _ece(
    items: list[ClassificationPrediction],
    *,
    bins: int,
) -> float:
    if not items:
        return 0.0
    total = len(items)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            item
            for item in items
            if lower <= item.dark_ad_score < upper
            or (index == bins - 1 and item.dark_ad_score == 1.0)
        ]
        if not bucket:
            continue
        confidence = sum(item.dark_ad_score for item in bucket) / len(bucket)
        observed = sum(item.true_label == "暗广" for item in bucket) / len(
            bucket
        )
        error += len(bucket) / total * abs(confidence - observed)
    return error


def evaluate_classification(
    predictions: list[ClassificationPrediction],
    *,
    calibration_bins: int = 10,
) -> ClassificationMetrics:
    if not predictions:
        raise ValueError("at least one prediction is required")
    if calibration_bins < 2:
        raise ValueError("calibration_bins must be at least 2")
    labels = ("明广", "暗广", "非广")
    f1_values = []
    for label in labels:
        true_positive = sum(
            item.true_label == label and item.predicted_label == label
            for item in predictions
        )
        false_positive = sum(
            item.true_label != label and item.predicted_label == label
            for item in predictions
        )
        false_negative = sum(
            item.true_label == label and item.predicted_label != label
            for item in predictions
        )
        precision = _safe_div(true_positive, true_positive + false_positive)
        recall = _safe_div(true_positive, true_positive + false_negative)
        f1_values.append(_f1(precision, recall))

    dark_tp = sum(
        item.true_label == "暗广" and item.predicted_label == "暗广"
        for item in predictions
    )
    dark_fp = sum(
        item.true_label != "暗广" and item.predicted_label == "暗广"
        for item in predictions
    )
    dark_fn = sum(
        item.true_label == "暗广" and item.predicted_label != "暗广"
        for item in predictions
    )
    dark_precision = _safe_div(dark_tp, dark_tp + dark_fp)
    dark_recall = _safe_div(dark_tp, dark_tp + dark_fn)
    review_count = sum(
        item.predicted_label == "需复核" for item in predictions
    )
    brier = sum(
        (
            item.dark_ad_score
            - (1.0 if item.true_label == "暗广" else 0.0)
        ) ** 2
        for item in predictions
    ) / len(predictions)
    return ClassificationMetrics(
        sample_count=len(predictions),
        macro_f1=sum(f1_values) / len(f1_values),
        dark_ad_precision=dark_precision,
        dark_ad_recall=dark_recall,
        dark_ad_f1=_f1(dark_precision, dark_recall),
        dark_ad_auprc=_average_precision(predictions),
        dark_ad_ece=_ece(predictions, bins=calibration_bins),
        dark_ad_brier=brier,
        coverage=1.0 - review_count / len(predictions),
        review_rate=review_count / len(predictions),
    )

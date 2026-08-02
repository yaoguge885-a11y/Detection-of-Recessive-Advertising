from __future__ import annotations

import pytest
from pydantic import ValidationError

from impad.evaluation import (
    CalibrationPrediction,
    risk_coverage_curve,
)


def _prediction(
    sample_id: str,
    *,
    true_label: str,
    predicted_label: str,
    confidence: float,
    dark_ad_score: float,
) -> CalibrationPrediction:
    return CalibrationPrediction(
        sample_id=sample_id,
        true_label=true_label,
        predicted_label=predicted_label,
        decision_confidence=confidence,
        dark_ad_score=dark_ad_score,
    )


def test_risk_coverage_retains_high_confidence_predictions_first():
    predictions = [
        _prediction(
            "s3",
            true_label="非广",
            predicted_label="暗广",
            confidence=0.2,
            dark_ad_score=0.7,
        ),
        _prediction(
            "s1",
            true_label="明广",
            predicted_label="明广",
            confidence=0.9,
            dark_ad_score=0.1,
        ),
        _prediction(
            "s2",
            true_label="暗广",
            predicted_label="明广",
            confidence=0.6,
            dark_ad_score=0.4,
        ),
    ]

    curve = risk_coverage_curve(predictions)

    assert [point.coverage for point in curve] == pytest.approx([
        1 / 3,
        2 / 3,
        1.0,
    ])
    assert curve[0].retained_sample_ids == ["s1"]
    assert curve[0].risk == 0
    assert curve[1].risk == 0.5
    assert curve[-1].risk == pytest.approx(2 / 3)
    assert curve[-1].confidence_threshold == 0.2


def test_risk_coverage_breaks_confidence_ties_by_sample_id():
    predictions = [
        _prediction(
            "b",
            true_label="暗广",
            predicted_label="明广",
            confidence=0.8,
            dark_ad_score=0.4,
        ),
        _prediction(
            "a",
            true_label="明广",
            predicted_label="明广",
            confidence=0.8,
            dark_ad_score=0.1,
        ),
    ]

    curve = risk_coverage_curve(predictions)

    assert curve[0].retained_sample_ids == ["a"]
    assert curve[1].retained_sample_ids == ["a", "b"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision_confidence", -0.1),
        ("decision_confidence", 1.1),
        ("dark_ad_score", -0.1),
        ("dark_ad_score", 1.1),
    ],
)
def test_calibration_prediction_rejects_invalid_scores(field, value):
    payload = {
        "sample_id": "s1",
        "true_label": "暗广",
        "predicted_label": "暗广",
        "decision_confidence": 0.8,
        "dark_ad_score": 0.8,
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        CalibrationPrediction.model_validate(payload)


def test_risk_coverage_requires_predictions():
    with pytest.raises(ValueError, match="at least one"):
        risk_coverage_curve([])

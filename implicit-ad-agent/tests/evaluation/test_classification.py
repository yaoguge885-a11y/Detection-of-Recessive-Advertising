import pytest

from impad.evaluation import (
    ClassificationPrediction,
    evaluate_classification,
)


def test_p3_metric_bundle_contains_required_three_class_and_calibration_metrics():
    predictions = [
        ClassificationPrediction(
            sample_id="1",
            true_label="明广",
            predicted_label="明广",
            dark_ad_score=0.1,
        ),
        ClassificationPrediction(
            sample_id="2",
            true_label="暗广",
            predicted_label="暗广",
            dark_ad_score=0.9,
        ),
        ClassificationPrediction(
            sample_id="3",
            true_label="非广",
            predicted_label="非广",
            dark_ad_score=0.05,
        ),
        ClassificationPrediction(
            sample_id="4",
            true_label="暗广",
            predicted_label="需复核",
            dark_ad_score=0.6,
        ),
    ]

    metrics = evaluate_classification(predictions)

    assert metrics.sample_count == 4
    assert 0 <= metrics.macro_f1 <= 1
    assert metrics.dark_ad_precision == 1
    assert metrics.dark_ad_recall == 0.5
    assert 0 <= metrics.dark_ad_auprc <= 1
    assert 0 <= metrics.dark_ad_ece <= 1
    assert 0 <= metrics.dark_ad_brier <= 1
    assert metrics.review_rate == 0.25
    assert metrics.coverage == 0.75


def test_classification_metrics_require_real_observations():
    with pytest.raises(ValueError, match="at least one"):
        evaluate_classification([])

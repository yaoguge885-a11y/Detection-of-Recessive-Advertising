import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from impad.evaluation import evaluate_classification
from impad.evaluation.reporting import (
    ClassificationEvaluationFixture,
    build_classification_report,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "classification_eval_v1.json"
)


def _fixture() -> ClassificationEvaluationFixture:
    return ClassificationEvaluationFixture.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )


def test_classification_report_contains_hand_counted_errors_and_confusions():
    fixture = _fixture()

    report = build_classification_report(fixture)

    assert report.benchmark_version == "synthetic-classification-v1"
    assert report.metrics == evaluate_classification(fixture.predictions)
    assert report.multiclass_confusion["暗广"]["暗广"] == 1
    assert report.multiclass_confusion["暗广"]["需复核"] == 1
    assert report.multiclass_confusion["明广"]["暗广"] == 1
    assert report.binary_confusion["dark_ad"]["review_required"] == 1
    assert report.binary_confusion["not_dark_ad"]["dark_ad"] == 1
    assert report.misclassified_sample_ids == ["4", "5", "6"]
    assert report.review_sample_ids == ["4"]
    assert report.error_buckets == {
        "明广->暗广": ["5"],
        "暗广->需复核": ["4"],
        "非广->明广": ["6"],
    }


@pytest.mark.parametrize("score", [None, -0.1, 1.1])
def test_classification_fixture_requires_an_explicit_valid_dark_ad_score(
    score,
):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if score is None:
        payload["predictions"][0].pop("dark_ad_score")
    else:
        payload["predictions"][0]["dark_ad_score"] = score
    payload["predictions"][0]["confidence"] = 0.99

    with pytest.raises(ValidationError):
        ClassificationEvaluationFixture.model_validate(payload)


def test_classification_fixture_requires_unique_sample_ids():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["predictions"][1]["sample_id"] = "1"

    with pytest.raises(
        ValidationError,
        match="sample_id values must be unique",
    ):
        ClassificationEvaluationFixture.model_validate(payload)

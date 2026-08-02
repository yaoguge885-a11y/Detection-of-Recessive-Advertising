from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from impad.evaluation import (
    CalibrationEvaluationFixture,
    bootstrap_classification_intervals,
    build_calibration_report,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "calibration_eval_v1.json"
)


def _fixture() -> CalibrationEvaluationFixture:
    return CalibrationEvaluationFixture.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )


def test_bootstrap_intervals_are_seeded_and_bounded():
    fixture = _fixture()

    first = bootstrap_classification_intervals(
        fixture.predictions,
        resamples=100,
        seed=20260730,
    )
    second = bootstrap_classification_intervals(
        fixture.predictions,
        resamples=100,
        seed=20260730,
    )

    assert first == second
    assert set(first) == {
        "macro_f1",
        "dark_ad_f1",
        "dark_ad_auprc",
        "dark_ad_ece",
        "dark_ad_brier",
    }
    for interval in first.values():
        assert 0 <= interval.estimate <= 1
        assert 0 <= interval.lower <= interval.upper <= 1


@pytest.mark.parametrize(
    ("resamples", "confidence_level"),
    [(0, 0.95), (10, 0), (10, 1)],
)
def test_bootstrap_rejects_invalid_configuration(
    resamples,
    confidence_level,
):
    with pytest.raises(ValueError):
        bootstrap_classification_intervals(
            _fixture().predictions,
            resamples=resamples,
            confidence_level=confidence_level,
        )


def test_calibration_report_records_metrics_intervals_and_curve():
    report = build_calibration_report(
        _fixture(),
        bootstrap_resamples=100,
        bootstrap_seed=20260730,
    )

    assert report.benchmark_version == "synthetic-calibration-v1"
    assert report.sample_count == 6
    assert report.bootstrap_resamples == 100
    assert report.bootstrap_seed == 20260730
    assert report.confidence_level == 0.95
    assert report.risk_coverage[-1].coverage == 1
    assert report.risk_coverage[-1].risk == 0.5
    assert report.metrics.sample_count == 6


def test_calibration_fixture_requires_unique_sample_ids():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["predictions"][1]["sample_id"] = "s1"

    with pytest.raises(
        ValidationError,
        match="sample_id values must be unique",
    ):
        CalibrationEvaluationFixture.model_validate(payload)

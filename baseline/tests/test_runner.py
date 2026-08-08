"""TDD coverage for fixed baseline classifiers and privacy-safe reporting."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from baseline.contracts import ContentPost, GoldRecord, InputBundle, SplitAssignments
from baseline.features import build_common_cohort
from baseline.reporting import build_report, serialize_report
from baseline.runner import METHODS, evaluate_predictions, run_baselines


LABELS = ("明广", "暗广", "非广")
UTC = timezone.utc


def _fixture_bundle() -> InputBundle:
    posts: dict[str, ContentPost] = {}
    gold: dict[str, GoldRecord] = {}
    split_ids: dict[str, set[str]] = {"train": set(), "dev": set(), "test": set()}
    start = datetime(2024, 1, 1, tzinfo=UTC)

    for split_index, split in enumerate(split_ids):
        for label_index, label in enumerate(LABELS):
            target_id = f"target-{split}-{label_index}"
            creator = f"creator-{split}-{label_index}"
            target_time = start + timedelta(days=split_index * 20 + 10)
            history_refs: list[str] = []
            for history_index in range(3):
                history_id = f"{target_id}-history-{history_index}"
                history_refs.append(history_id)
                posts[history_id] = ContentPost(
                    post_id=history_id,
                    blogger_id=creator,
                    published_at=target_time - timedelta(days=history_index + 1),
                    text=f"history text {history_index}",
                    history_refs=(),
                    content_group_id=None,
                )
            posts[target_id] = ContentPost(
                post_id=target_id,
                blogger_id=creator,
                published_at=target_time,
                text="品牌赞助，限时优惠，点击链接购买，今天分享体验",
                history_refs=tuple(history_refs),
                content_group_id=None,
            )
            gold[target_id] = GoldRecord(post_id=target_id, label=label)
            split_ids[split].add(target_id)

    return InputBundle(
        mode="synthetic",
        posts=posts,
        gold=gold,
        splits=SplitAssignments(
            train=frozenset(split_ids["train"]),
            dev=frozenset(split_ids["dev"]),
            test=frozenset(split_ids["test"]),
        ),
        evaluation_split="dev",
        confirm_test_evaluation=False,
        input_hashes={
            "content": "content-hash",
            "gold": "gold-hash",
            "train_ids": "train-hash",
            "dev_ids": "dev-hash",
            "test_ids": "test-hash",
            "split_report": "split-hash",
            "m1_gate": "gate-hash",
        },
    )


@pytest.fixture()
def bundle() -> InputBundle:
    return _fixture_bundle()


@pytest.fixture()
def cohort(bundle: InputBundle):
    return build_common_cohort(bundle)


def test_four_methods_are_deterministic_and_share_sample_counts(cohort, bundle):
    first = run_baselines(bundle, cohort)
    second = run_baselines(bundle, cohort)

    assert first == second
    assert tuple(first) == METHODS == (
        "single_post",
        "history_mean",
        "history_max",
        "history_ema",
    )
    assert {result.train_count for result in first.values()} == {
        cohort.split_cohort_counts["train"]
    }
    assert {result.evaluation_count for result in first.values()} == {
        cohort.split_cohort_counts["dev"]
    }


def test_dark_ad_probability_uses_named_class_mapping(cohort, bundle):
    results = run_baselines(bundle, cohort)

    for result in results.values():
        assert result.class_order == LABELS
        assert len(result.dark_ad_scores) == result.evaluation_count
        assert all(0.0 <= score <= 1.0 for score in result.dark_ad_scores)


def test_report_metrics_include_fixed_confusion_and_history_deltas(cohort, bundle):
    results = run_baselines(bundle, cohort)
    report = build_report(bundle, cohort, results)

    for method in METHODS:
        method_report = report["methods"][method]
        assert set(method_report) >= {
            "macro_f1",
            "dark_ad_precision",
            "dark_ad_recall",
            "dark_ad_f1",
            "dark_ad_auprc",
            "dark_ad_brier",
            "ece",
            "confusion_counts",
            "delta_vs_single_post",
        }
        assert set(method_report["confusion_counts"]) == set(LABELS)
        assert all(
            set(method_report["confusion_counts"][actual]) == set(LABELS)
            for actual in LABELS
        )
        assert sum(
            sum(row.values()) for row in method_report["confusion_counts"].values()
        ) == 3
    assert report["methods"]["single_post"]["delta_vs_single_post"] == {
        "macro_f1": 0.0,
        "dark_ad_f1": 0.0,
        "dark_ad_auprc": 0.0,
    }


def test_serialized_report_is_deterministic_except_generated_at(cohort, bundle):
    results = run_baselines(bundle, cohort)
    first = json.loads(serialize_report(build_report(bundle, cohort, results)))
    second = json.loads(serialize_report(build_report(bundle, cohort, results)))

    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_serialized_report_contains_aggregate_metadata_only(cohort, bundle):
    report = build_report(bundle, cohort, run_baselines(bundle, cohort))
    serialized = serialize_report(report)

    assert report["mode"] == "synthetic"
    assert report["dataset_kind"] == "synthetic_fixture"
    assert report["research_claims_allowed"] is False
    assert report["input_hashes"] == bundle.input_hashes
    assert "classifier" in report["parameters"]
    assert "python" in report["versions"]
    assert "scikit_learn" in report["versions"]
    assert "品牌赞助" not in serialized
    assert "https://" not in serialized
    assert "target-dev-0" not in serialized
    assert "creator-dev-0" not in serialized
    assert "annotator" not in serialized.lower()
    assert "dark_ad_scores" not in serialized


def test_report_serialization_rejects_non_mapping():
    with pytest.raises(TypeError, match="report must be a mapping"):
        serialize_report([])  # type: ignore[arg-type]


def test_evaluate_predictions_uses_fixed_metrics_and_last_ece_bin():
    result = evaluate_predictions(
        LABELS,
        LABELS,
        (0.0, 1.0, 1.0),
        method="single_post",
        train_count=3,
    )

    assert result.macro_f1 == pytest.approx(1.0)
    assert result.dark_ad_precision == pytest.approx(1.0)
    assert result.dark_ad_recall == pytest.approx(1.0)
    assert result.dark_ad_f1 == pytest.approx(1.0)
    assert result.dark_ad_auprc == pytest.approx(0.5)
    assert result.dark_ad_brier == pytest.approx(1 / 3)
    assert result.confusion_counts["暗广"]["暗广"] == 1
    assert result.ece == pytest.approx(1 / 3)


def test_evaluate_predictions_maps_named_probability_column():
    result = evaluate_predictions(
        LABELS,
        LABELS,
        probabilities=(
            (0.8, 0.1, 0.1),
            (0.1, 0.8, 0.1),
            (0.1, 0.1, 0.8),
        ),
    )

    assert result.dark_ad_scores == pytest.approx((0.1, 0.8, 0.1))

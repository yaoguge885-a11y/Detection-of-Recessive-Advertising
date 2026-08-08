"""Aggregate, deterministic, privacy-safe baseline report assembly."""

from __future__ import annotations

import json
import hashlib
import platform
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib import metadata
from typing import Any

from .contracts import BaselineInputError, InputBundle
from .features import Cohort, FEATURE_VERSION
from .runner import METHODS, ClassifierConfig, MethodResult


REPORT_VERSION = "merged-history-baseline-report-v1"
SCHEMA_VERSION = "schema_v1.2"
POOLING_VERSION = "mean_max_ema_v1"
CLASSIFIER_VERSION = "standard_scaler_logistic_regression_v1"


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unavailable"


def _method_report(result: MethodResult) -> dict[str, Any]:
    return {
        "class_order": list(result.class_order),
        "train_count": result.train_count,
        "evaluation_count": result.evaluation_count,
        "macro_f1": result.macro_f1,
        "dark_ad_precision": result.dark_ad_precision,
        "dark_ad_recall": result.dark_ad_recall,
        "dark_ad_f1": result.dark_ad_f1,
        "dark_ad_auprc": result.dark_ad_auprc,
        "dark_ad_brier": result.dark_ad_brier,
        "dark_ad_ece": result.ece,
        "ece": result.ece,
        "confusion_counts": {
            actual: {predicted: result.confusion_counts[actual][predicted] for predicted in result.class_order}
            for actual in result.class_order
        },
        "delta_vs_single_post": {
            key: result.delta_vs_single_post[key]
            for key in ("macro_f1", "dark_ad_f1", "dark_ad_auprc")
        },
    }


def _coerce_results(
    results: Mapping[str, MethodResult] | Sequence[MethodResult],
) -> dict[str, MethodResult]:
    if isinstance(results, Mapping):
        values = dict(results)
    else:
        try:
            values = {result.method: result for result in results}
        except (TypeError, AttributeError) as exc:
            raise BaselineInputError("baseline results are invalid") from exc
    if set(values) != set(METHODS) or any(
        not isinstance(values.get(method), MethodResult) for method in METHODS
    ):
        raise BaselineInputError("baseline results are incomplete")
    return {method: values[method] for method in METHODS}


def build_report(
    bundle: InputBundle,
    cohort: Cohort,
    results: Mapping[str, MethodResult] | Sequence[MethodResult],
    *,
    config: ClassifierConfig | None = None,
) -> dict[str, Any]:
    """Build an aggregate-only report with one intentionally variable timestamp."""

    if not isinstance(bundle, InputBundle):
        raise BaselineInputError("baseline input bundle is invalid")
    if not isinstance(cohort, Cohort):
        raise BaselineInputError("baseline cohort is invalid")
    normalized = _coerce_results(results)
    selected_config = config or ClassifierConfig()
    config_payload = json.dumps(
        selected_config.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    config_hash = hashlib.sha256(config_payload).hexdigest()
    dataset_kind = (
        "synthetic_fixture" if bundle.mode == "synthetic" else "formal_gold"
    )
    report = {
        "report_version": REPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": bundle.mode,
        "dataset_kind": dataset_kind,
        "research_claims_allowed": bundle.mode == "formal",
        "evaluation_split": bundle.evaluation_split,
        "confirm_test_evaluation": bundle.confirm_test_evaluation,
        "versions": {
            "schema": SCHEMA_VERSION,
            "feature": FEATURE_VERSION,
            "pooling": POOLING_VERSION,
            "classifier": CLASSIFIER_VERSION,
            "python": platform.python_version(),
            "scikit_learn": _package_version("scikit-learn"),
        },
        "parameters": {
            "feature_version": FEATURE_VERSION,
            "pooling": {
                "history_methods": ["mean", "max", "ema"],
                "ema_alpha": 0.5,
            },
            "classifier": selected_config.as_dict(),
            "config_sha256": config_hash,
            "labels": ["明广", "暗广", "非广"],
            "ece": {"bins": 10, "intervals": "[lower, upper), last includes 1.0"},
        },
        "input_hashes": {key: bundle.input_hashes[key] for key in sorted(bundle.input_hashes)},
        "counts": {
            "gold_count": cohort.gold_count,
            "split_gold_counts": {
                key: cohort.split_gold_counts[key]
                for key in ("train", "dev", "test")
            },
            "cohort_count": len(cohort.samples),
            "split_cohort_counts": {
                key: cohort.split_cohort_counts[key]
                for key in ("train", "dev", "test")
            },
            "coverage": {
                "overall": len(cohort.samples) / cohort.gold_count
                if cohort.gold_count
                else 0.0,
                "by_split": {
                    key: (
                        cohort.split_cohort_counts[key] / cohort.split_gold_counts[key]
                        if cohort.split_gold_counts[key]
                        else 0.0
                    )
                    for key in ("train", "dev", "test")
                },
            },
            "exclusions": {
                key: cohort.exclusion_counts[key]
                for key in sorted(cohort.exclusion_counts)
            },
        },
        "methods": {method: _method_report(normalized[method]) for method in METHODS},
    }
    return report


def serialize_report(report: Mapping[str, Any]) -> str:
    """Serialize a report with stable key and separator choices."""

    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    try:
        return json.dumps(
            dict(report),
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError("report contains non-serializable values") from exc


__all__ = [
    "REPORT_VERSION",
    "SCHEMA_VERSION",
    "POOLING_VERSION",
    "CLASSIFIER_VERSION",
    "build_report",
    "serialize_report",
]

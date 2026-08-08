"""Fixed, deterministic classifiers for the isolated history baseline."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Sequence

from .contracts import LABELS, BaselineInputError, InputBundle
from .features import Cohort, method_vector


METHODS = ("single_post", "history_mean", "history_max", "history_ema")


@dataclass(frozen=True)
class ClassifierConfig:
    """The classifier and scaler settings pinned by the baseline design."""

    scaler: str = "standard_scaler"
    classifier: str = "logistic_regression"
    solver: str = "lbfgs"
    C: float = 1.0
    max_iter: int = 1000
    random_state: int = 0
    class_weight: None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scaler": self.scaler,
            "classifier": self.classifier,
            "solver": self.solver,
            "C": self.C,
            "max_iter": self.max_iter,
            "random_state": self.random_state,
            "class_weight": self.class_weight,
        }


@dataclass(frozen=True)
class MethodResult:
    """Aggregate evaluation for one fixed-feature baseline.

    ``dark_ad_scores`` is retained in memory for callers that need to inspect
    probability mapping.  Reporting intentionally omits it and all other
    row-level values.
    """

    method: str
    class_order: tuple[str, ...]
    train_count: int
    evaluation_count: int
    macro_f1: float
    dark_ad_precision: float
    dark_ad_recall: float
    dark_ad_f1: float
    dark_ad_auprc: float
    dark_ad_brier: float
    ece: float
    confusion_counts: dict[str, dict[str, int]]
    delta_vs_single_post: dict[str, float]
    dark_ad_scores: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return aggregate fields in the same shape used by reports."""

        return {
            "method": self.method,
            "class_order": self.class_order,
            "train_count": self.train_count,
            "evaluation_count": self.evaluation_count,
            "macro_f1": self.macro_f1,
            "dark_ad_precision": self.dark_ad_precision,
            "dark_ad_recall": self.dark_ad_recall,
            "dark_ad_f1": self.dark_ad_f1,
            "dark_ad_auprc": self.dark_ad_auprc,
            "dark_ad_brier": self.dark_ad_brier,
            "dark_ad_ece": self.ece,
            "ece": self.ece,
            "confusion_counts": self.confusion_counts,
            "delta_vs_single_post": self.delta_vs_single_post,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow metric consumers to use either attribute or mapping syntax."""

        if key == "dark_scores":
            return self.dark_ad_scores
        return self.as_dict()[key]

    @property
    def brier(self) -> float:
        """Short alias used by metric consumers."""

        return self.dark_ad_brier

    @property
    def dark_ad_ece(self) -> float:
        return self.ece

    @property
    def auprc(self) -> float:
        """Short alias used by metric consumers."""

        return self.dark_ad_auprc

    @property
    def dark_precision(self) -> float:
        return self.dark_ad_precision

    @property
    def dark_recall(self) -> float:
        return self.dark_ad_recall

    @property
    def dark_f1(self) -> float:
        return self.dark_ad_f1

    @property
    def delta(self) -> dict[str, float]:
        return self.delta_vs_single_post


def _new_pipeline(config: ClassifierConfig | None = None) -> Any:
    """Build one fresh sklearn pipeline, importing sklearn lazily."""

    selected = config or ClassifierConfig()
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise BaselineInputError(
            "scikit-learn is required; install baseline/requirements.txt"
        ) from exc
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    solver=selected.solver,
                    C=selected.C,
                    max_iter=selected.max_iter,
                    random_state=selected.random_state,
                    class_weight=selected.class_weight,
                ),
            ),
        ]
    )


def _finite_probability(value: Any) -> float:
    if isinstance(value, bool):
        raise BaselineInputError("model probability is invalid")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise BaselineInputError("model probability is invalid") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise BaselineInputError("model probability is invalid")
    return score


def _validate_sequence_lengths(
    y_true: Sequence[str], y_pred: Sequence[str], dark_scores: Sequence[float]
) -> None:
    if len(y_true) == 0:
        raise BaselineInputError("evaluation samples are empty")
    if len(y_true) != len(y_pred) or len(y_true) != len(dark_scores):
        raise BaselineInputError("evaluation arrays have inconsistent lengths")
    if any(label not in LABELS for label in y_true):
        raise BaselineInputError("evaluation labels are invalid")
    if any(label not in LABELS for label in y_pred):
        raise BaselineInputError("predicted labels are invalid")


def _dark_score_values(
    values: Sequence[Any], class_order: Sequence[str]
) -> tuple[float, ...]:
    """Accept either dark-score values or full class probability rows."""

    materialized = tuple(values)
    dark_index = tuple(class_order).index(LABELS[1])
    scores: list[float] = []
    for value in materialized:
        try:
            scores.append(_finite_probability(value))
            continue
        except BaselineInputError:
            pass
        if isinstance(value, (str, bytes)):
            raise BaselineInputError("model probability is invalid")
        try:
            row = tuple(value)
        except TypeError as exc:
            raise BaselineInputError("model probability is invalid") from exc
        if len(row) != len(class_order):
            raise BaselineInputError("model probability row is invalid")
        scores.append(_finite_probability(row[dark_index]))
    return tuple(scores)


def _ece(dark_true: Sequence[bool], dark_scores: Sequence[float]) -> float:
    """Compute ten-bin expected calibration error for the dark-ad score."""

    total = len(dark_true)
    if total == 0:
        raise BaselineInputError("evaluation samples are empty")
    error = 0.0
    for index in range(10):
        lower = index / 10.0
        upper = (index + 1) / 10.0
        if index == 9:
            members = [
                position
                for position, score in enumerate(dark_scores)
                if lower <= score <= upper
            ]
        else:
            members = [
                position
                for position, score in enumerate(dark_scores)
                if lower <= score < upper
            ]
        if not members:
            continue
        confidence = sum(dark_scores[position] for position in members) / len(members)
        accuracy = sum(bool(dark_true[position]) for position in members) / len(members)
        error += len(members) / total * abs(accuracy - confidence)
    return float(error)


def _confusion_counts(
    y_true: Sequence[str], y_pred: Sequence[str]
) -> dict[str, dict[str, int]]:
    matrix = {actual: {predicted: 0 for predicted in LABELS} for actual in LABELS}
    for actual, predicted in zip(y_true, y_pred):
        matrix[actual][predicted] += 1
    return matrix


def evaluate_predictions(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    dark_scores: Sequence[Any] | None = None,
    *,
    probabilities: Sequence[Any] | None = None,
    method: str = "",
    train_count: int = 0,
    evaluation_count: int | None = None,
    class_order: Sequence[str] = LABELS,
) -> MethodResult:
    """Calculate the fixed aggregate metrics for one prediction set."""

    if tuple(class_order) != LABELS:
        raise BaselineInputError("classifier class order is invalid")
    if dark_scores is None:
        dark_scores = probabilities
    elif probabilities is not None:
        raise BaselineInputError("multiple probability inputs were provided")
    if dark_scores is None:
        raise BaselineInputError("model probabilities are missing")
    score_values = _dark_score_values(dark_scores, class_order)
    _validate_sequence_lengths(y_true, y_pred, score_values)
    scores = score_values

    try:
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            f1_score,
            precision_recall_fscore_support,
        )
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise BaselineInputError(
            "scikit-learn is required; install baseline/requirements.txt"
        ) from exc

    dark_true = tuple(label == LABELS[1] for label in y_true)
    dark_pred = tuple(label == LABELS[1] for label in y_pred)
    macro_f1 = float(
        f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)
    )
    dark_precision, dark_recall, dark_f1, _ = precision_recall_fscore_support(
        dark_true,
        dark_pred,
        average="binary",
        zero_division=0,
    )
    dark_auprc = (
        float(average_precision_score(dark_true, scores))
        if any(dark_true)
        else 0.0
    )
    dark_brier = float(brier_score_loss(dark_true, scores))
    result = MethodResult(
        method=method,
        class_order=LABELS,
        train_count=int(train_count),
        evaluation_count=(
            len(y_true) if evaluation_count is None else int(evaluation_count)
        ),
        macro_f1=macro_f1,
        dark_ad_precision=float(dark_precision),
        dark_ad_recall=float(dark_recall),
        dark_ad_f1=float(dark_f1),
        dark_ad_auprc=dark_auprc,
        dark_ad_brier=dark_brier,
        ece=_ece(dark_true, scores),
        confusion_counts=_confusion_counts(y_true, y_pred),
        delta_vs_single_post={
            "macro_f1": 0.0,
            "dark_ad_f1": 0.0,
            "dark_ad_auprc": 0.0,
        },
        dark_ad_scores=scores,
    )
    return result


def _samples_for_split(cohort: Cohort, split: str) -> list[Any]:
    samples = [sample for sample in cohort.samples if sample.split == split]
    if not samples:
        raise BaselineInputError("cohort split is empty")
    return samples


def run_baselines(
    bundle: InputBundle,
    cohort: Cohort,
    *,
    config: ClassifierConfig | None = None,
) -> dict[str, MethodResult]:
    """Fit and evaluate all four fixed methods on one shared cohort."""

    if not isinstance(bundle, InputBundle):
        raise BaselineInputError("baseline input bundle is invalid")
    if not isinstance(cohort, Cohort):
        raise BaselineInputError("baseline cohort is invalid")
    if bundle.evaluation_split not in {"train", "dev", "test"}:
        raise BaselineInputError("evaluation split is invalid")
    selected_config = config or ClassifierConfig()

    train_samples = _samples_for_split(cohort, "train")
    evaluation_samples = _samples_for_split(cohort, bundle.evaluation_split)
    y_train = [sample.label for sample in train_samples]
    y_true = [sample.label for sample in evaluation_samples]
    if set(y_train) != set(LABELS) or set(y_true) != set(LABELS):
        raise BaselineInputError("cohort split must contain all three labels")

    results: dict[str, MethodResult] = {}
    for method in METHODS:
        try:
            train_features = [method_vector(sample, method) for sample in train_samples]
            evaluation_features = [
                method_vector(sample, method) for sample in evaluation_samples
            ]
        except BaselineInputError:
            raise
        except (TypeError, ValueError) as exc:
            raise BaselineInputError("baseline feature vectors are invalid") from exc

        pipeline = _new_pipeline(selected_config)
        try:
            pipeline.fit(train_features, y_train)
            y_pred = tuple(pipeline.predict(evaluation_features))
            raw_probabilities = pipeline.predict_proba(evaluation_features)
            classes = tuple(pipeline.named_steps["classifier"].classes_)
        except BaselineInputError:
            raise
        except (TypeError, ValueError, AttributeError) as exc:
            raise BaselineInputError("baseline classifier could not be fitted") from exc

        if set(classes) != set(LABELS):
            raise BaselineInputError("classifier did not produce all three classes")
        class_indexes = {label: index for index, label in enumerate(classes)}
        dark_index = class_indexes[LABELS[1]]
        try:
            dark_scores = tuple(
                _finite_probability(probability_row[dark_index])
                for probability_row in raw_probabilities
            )
        except (IndexError, TypeError) as exc:
            raise BaselineInputError("classifier probabilities are invalid") from exc

        results[method] = evaluate_predictions(
            y_true,
            y_pred,
            dark_scores,
            method=method,
            train_count=len(train_samples),
            evaluation_count=len(evaluation_samples),
        )

    reference = results["single_post"]
    for method in METHODS:
        result = results[method]
        if method == "single_post":
            delta = {
                "macro_f1": 0.0,
                "dark_ad_f1": 0.0,
                "dark_ad_auprc": 0.0,
            }
        else:
            delta = {
                "macro_f1": result.macro_f1 - reference.macro_f1,
                "dark_ad_f1": result.dark_ad_f1 - reference.dark_ad_f1,
                "dark_ad_auprc": result.dark_ad_auprc - reference.dark_ad_auprc,
            }
        results[method] = replace(result, delta_vs_single_post=delta)
    return results


__all__ = [
    "METHODS",
    "ClassifierConfig",
    "MethodResult",
    "evaluate_predictions",
    "run_baselines",
]

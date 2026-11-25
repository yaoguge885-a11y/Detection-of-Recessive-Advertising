"""Strict, label-only before/after evaluation for one post cohort.

The existing classification score contract is intentionally not used here:
this module compares only the three-class labels and ``需复核`` decisions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


GOLD_LABELS = ("明广", "暗广", "非广")
PREDICTED_LABELS = (*GOLD_LABELS, "需复核")
REPORT_SCHEMA = "paired-label-evaluation/v1"


class PairingError(ValueError):
    """Raised when prediction sets cannot be safely paired."""


@dataclass(frozen=True)
class PredictionRow:
    post_id: str
    gold_label: str
    predicted_label: str


@dataclass(frozen=True)
class LoadedPredictions:
    rows: tuple[PredictionRow, ...]
    schema: str
    arm: str | None


@dataclass(frozen=True)
class _Pair:
    post_id: str
    gold_label: str
    before_label: str
    after_label: str


def _div(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return _div(2 * precision * recall, precision + recall)


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    )


def _rows_from_payload(payload: Any, source: str) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    elif (
        isinstance(payload, Mapping)
        and isinstance(payload.get("all"), Mapping)
        and isinstance(payload["all"].get("rows"), list)
    ):
        rows = payload["all"]["rows"]
    elif isinstance(payload, Mapping) and "post_id" in payload:
        rows = [payload]
    else:
        raise PairingError(
            f"{source}: expected a JSON array, an object with rows, or one row"
        )
    if not all(isinstance(row, Mapping) for row in rows):
        raise PairingError(f"{source}: every row must be a JSON object")
    return list(rows)


def _label(value: Any, field: str, source: str, index: int) -> str:
    if not isinstance(value, str) or value not in PREDICTED_LABELS:
        raise PairingError(
            f"{source}: row {index} has invalid {field} {value!r}; "
            f"expected one of {', '.join(PREDICTED_LABELS)}"
        )
    return value


def _normalize(
    rows: Iterable[Mapping[str, Any]], *, arm: str | None, source: str
) -> LoadedPredictions:
    raw_rows = list(rows)
    if not raw_rows:
        raise PairingError(f"{source}: at least one row is required")
    first = raw_rows[0]
    if "predictions" in first:
        schema = "expanded_agent_rows"
        if not isinstance(first["predictions"], Mapping):
            raise PairingError(f"{source}: predictions must be a JSON object")
    elif "predicted_label" in first:
        schema = "minimal_rows"
    else:
        raise PairingError(
            f"{source}: expected minimal post_id,label,predicted_label rows or "
            "expanded post_id,gold_label,predictions rows"
        )

    normalized: list[PredictionRow] = []
    seen: set[str] = set()
    for index, row in enumerate(raw_rows):
        expanded = "predictions" in row
        if expanded != (schema == "expanded_agent_rows"):
            raise PairingError(f"{source}: mixed expanded/minimal rows are not supported")
        post_id = row.get("post_id")
        if not isinstance(post_id, str) or not post_id.strip():
            raise PairingError(f"{source}: row {index} needs a non-empty string post_id")
        if post_id in seen:
            raise PairingError(f"{source}: duplicate post_id {post_id!r}")
        seen.add(post_id)

        gold = row.get("gold_label", row.get("label"))
        if not isinstance(gold, str) or gold not in GOLD_LABELS:
            raise PairingError(
                f"{source}: row {index} has invalid or missing gold label {gold!r}"
            )

        if schema == "minimal_rows":
            predicted = row.get("predicted_label")
        else:
            choices = row["predictions"]
            if not isinstance(choices, Mapping):
                raise PairingError(f"{source}: row {index} predictions must be an object")
            chosen_arm = arm
            if chosen_arm is None:
                if len(choices) != 1:
                    raise PairingError(
                        f"{source}: row {index} has multiple prediction arms; "
                        "select one with --*-arm"
                    )
                chosen_arm = next(iter(choices))
            if chosen_arm not in choices:
                raise PairingError(
                    f"{source}: prediction arm {chosen_arm!r} is not present "
                    f"in row {index}"
                )
            predicted = choices[chosen_arm]
        normalized.append(
            PredictionRow(post_id, gold, _label(predicted, "predicted_label", source, index))
        )
    normalized.sort(key=lambda row: row.post_id)
    return LoadedPredictions(
        tuple(normalized),
        schema,
        arm if schema == "expanded_agent_rows" else None,
    )


def load_prediction_file(
    path: str | Path, *, arm: str | None = None
) -> tuple[LoadedPredictions, dict[str, Any]]:
    """Load one expanded-agent or minimal JSON/JSONL set."""
    source_path = Path(path)
    raw = source_path.read_bytes()
    source = str(source_path)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PairingError(f"{source}: expected UTF-8 JSON/JSONL") from exc
    try:
        payload = json.loads(text)
        format_name = "json"
        rows = _rows_from_payload(payload, source)
    except json.JSONDecodeError:
        rows = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PairingError(
                    f"{source}: invalid JSONL at line {line_number}: {exc.msg}"
                ) from exc
            if not isinstance(row, Mapping):
                raise PairingError(f"{source}: JSONL line {line_number} is not an object")
            rows.append(row)
        format_name = "jsonl"
    loaded = _normalize(rows, arm=arm, source=source)
    return loaded, {
        "path": str(source_path.resolve()),
        "sha256": _hash_bytes(raw),
        "format": format_name,
        "schema": loaded.schema,
        "arm": arm,
        "n": len(loaded.rows),
    }


def _metrics(rows: list[_Pair], field: str) -> dict[str, int | float]:
    n = len(rows)
    correct = sum(getattr(row, field) == row.gold_label for row in rows)
    f1_values = []
    for label in GOLD_LABELS:
        tp = sum(row.gold_label == label and getattr(row, field) == label for row in rows)
        fp = sum(row.gold_label != label and getattr(row, field) == label for row in rows)
        fn = sum(row.gold_label == label and getattr(row, field) != label for row in rows)
        f1_values.append(_f1(_div(tp, tp + fp), _div(tp, tp + fn)))
    dark_total = sum(row.gold_label == "暗广" for row in rows)
    dark_hits = sum(row.gold_label == "暗广" and getattr(row, field) == "暗广" for row in rows)
    overt_total = sum(row.gold_label == "明广" for row in rows)
    overt_hits = sum(row.gold_label == "明广" and getattr(row, field) == "明广" for row in rows)
    normal_total = sum(row.gold_label == "非广" for row in rows)
    normal_fp = sum(
        row.gold_label == "非广" and getattr(row, field) in {"明广", "暗广"}
        for row in rows
    )
    reviews = sum(getattr(row, field) == "需复核" for row in rows)
    return {
        "n": n,
        "correct": correct,
        "accuracy": _div(correct, n),
        "macro_f1": sum(f1_values) / len(f1_values),
        "dark_recall": _div(dark_hits, dark_total),
        "overt_recall": _div(overt_hits, overt_total),
        "normal_commercial_false_positive_count": normal_fp,
        "normal_commercial_false_positive_rate": _div(normal_fp, normal_total),
        "review_count": reviews,
        "review_rate": _div(reviews, n),
    }


def _transitions(rows: list[_Pair], gold: str | None = None) -> dict[str, Any]:
    selected = [row for row in rows if gold is None or row.gold_label == gold]
    changed = sorted(row.post_id for row in selected if row.before_label != row.after_label)
    corrected = sorted(
        row.post_id
        for row in selected
        if row.before_label != row.gold_label and row.after_label == row.gold_label
    )
    regressed = sorted(
        row.post_id
        for row in selected
        if row.before_label == row.gold_label and row.after_label != row.gold_label
    )
    before_review = {row.post_id for row in selected if row.before_label == "需复核"}
    after_review = {row.post_id for row in selected if row.after_label == "需复核"}
    reduced = sorted(before_review - after_review)
    increased = sorted(after_review - before_review)
    net = len(before_review) - len(after_review)
    return {
        "n": len(selected),
        "changed": len(changed),
        "changed_ids": changed,
        "corrected": len(corrected),
        "corrected_ids": corrected,
        "regressed": len(regressed),
        "regressed_ids": regressed,
        "review_reduction": net,
        "review_reduction_rate": _div(net, len(selected)),
        "review_reduced_ids": reduced,
        "review_increased_ids": increased,
        "before_review_count": len(before_review),
        "after_review_count": len(after_review),
    }


def _cohort(rows: list[_Pair]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row.post_id)
    ids = [row.post_id for row in ordered]
    gold_pairs = [[row.post_id, row.gold_label] for row in ordered]
    counts = Counter(row.gold_label for row in ordered)
    return {
        "n": len(rows),
        "post_ids": ids,
        "post_ids_sha256": _hash_json(ids),
        "gold_counts": {label: counts.get(label, 0) for label in GOLD_LABELS},
        "gold_by_post_id_sha256": _hash_json(gold_pairs),
    }


def build_paired_report(
    before: LoadedPredictions,
    after: LoadedPredictions,
    *,
    source_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pair exact IDs and produce metrics plus deterministic transition lists."""
    before_by_id = {row.post_id: row for row in before.rows}
    after_by_id = {row.post_id: row for row in after.rows}
    if len(before_by_id) != len(before.rows):
        raise PairingError("before: duplicate post_id values")
    if len(after_by_id) != len(after.rows):
        raise PairingError("after: duplicate post_id values")
    before_ids, after_ids = set(before_by_id), set(after_by_id)
    if before_ids != after_ids:
        raise PairingError(
            "cohort mismatch: exact post_id sets are required; "
            f"missing from before={sorted(after_ids - before_ids)!r}, "
            f"missing from after={sorted(before_ids - after_ids)!r}"
        )
    conflicts = [
        post_id
        for post_id in sorted(before_ids)
        if before_by_id[post_id].gold_label != after_by_id[post_id].gold_label
    ]
    if conflicts:
        detail = ", ".join(
            f"{post_id!r} ({before_by_id[post_id].gold_label!r} vs "
            f"{after_by_id[post_id].gold_label!r})"
            for post_id in conflicts
        )
        raise PairingError(f"gold label conflict for post_id values: {detail}")
    rows = [
        _Pair(
            row.post_id,
            row.gold_label,
            row.predicted_label,
            after_by_id[row.post_id].predicted_label,
        )
        for row in sorted(before.rows, key=lambda row: row.post_id)
    ]
    metadata = dict(source_metadata or {})
    return {
        "schema": REPORT_SCHEMA,
        "source": metadata,
        "source_hashes": {
            name: item["sha256"]
            for name, item in metadata.items()
            if isinstance(item, Mapping) and item.get("sha256")
        },
        "schema_manifest": {
            "before": {"schema": before.schema, "arm": before.arm},
            "after": {"schema": after.schema, "arm": after.arm},
            "gold_labels": list(GOLD_LABELS),
            "predicted_labels": list(PREDICTED_LABELS),
        },
        "cohort_manifest": _cohort(rows),
        "n": len(rows),
        "before": _metrics(rows, "before_label"),
        "after": _metrics(rows, "after_label"),
        "overall": _transitions(rows),
        "by_gold_label": {
            label: _transitions(rows, label) for label in GOLD_LABELS
        },
    }


def evaluate_paired(
    before_rows: Iterable[Mapping[str, Any]] | LoadedPredictions,
    after_rows: Iterable[Mapping[str, Any]] | LoadedPredictions,
    *,
    before_arm: str | None = None,
    after_arm: str | None = None,
    source_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate two normalized or raw row sets with strict same-target pairing."""
    before = (
        before_rows
        if isinstance(before_rows, LoadedPredictions)
        else _normalize(before_rows, arm=before_arm, source="before")
    )
    after = (
        after_rows
        if isinstance(after_rows, LoadedPredictions)
        else _normalize(after_rows, arm=after_arm, source="after")
    )
    return build_paired_report(before, after, source_metadata=source_metadata)


__all__ = [
    "GOLD_LABELS",
    "PREDICTED_LABELS",
    "LoadedPredictions",
    "PairingError",
    "PredictionRow",
    "build_paired_report",
    "evaluate_paired",
    "load_prediction_file",
]

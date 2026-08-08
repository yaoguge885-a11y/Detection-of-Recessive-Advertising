"""Input contracts for the isolated history baseline.

The loader in this module is deliberately independent from the Agent package.  It
performs all governance and join checks before any later training code is allowed
to consume an :class:`InputBundle`.  Error messages contain only aggregate reasons
and field names; source values and identifiers are never included.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


Mode = Literal["formal", "synthetic"]
SplitName = Literal["train", "dev", "test"]
LABELS = ("明广", "暗广", "非广")


class BaselineInputError(ValueError):
    """Privacy-safe input or governance failure raised before training."""


@dataclass(frozen=True)
class ContentPost:
    post_id: str
    blogger_id: str
    published_at: datetime | None
    text: str
    history_refs: tuple[str, ...]
    content_group_id: str | None


@dataclass(frozen=True)
class GoldRecord:
    post_id: str
    label: str


@dataclass(frozen=True)
class SplitAssignments:
    train: frozenset[str]
    dev: frozenset[str]
    test: frozenset[str]


@dataclass(frozen=True)
class InputBundle:
    mode: Mode
    posts: dict[str, ContentPost]
    gold: dict[str, GoldRecord]
    splits: SplitAssignments
    evaluation_split: SplitName
    confirm_test_evaluation: bool
    input_hashes: dict[str, str]


_SPLITS: tuple[SplitName, ...] = ("train", "dev", "test")
_SYNTHETIC_FIXTURE_VERSION = "merged-history-synthetic-v1"
_LEAKAGE_FIELDS: tuple[str, ...] = (
    "post_leakage_count",
    "creator_leakage_count",
    "content_group_leakage_count",
    "near_duplicate_leakage_count",
)


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 digest of *path* without exposing its name on failure."""

    try:
        file_path = Path(path)
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, TypeError, ValueError) as exc:
        raise BaselineInputError("input file could not be hashed") from exc


def load_input_bundle(
    mode: Mode,
    *,
    content_path: Path | str | None = None,
    gold_path: Path | str | None = None,
    train_ids_path: Path | str | None = None,
    dev_ids_path: Path | str | None = None,
    test_ids_path: Path | str | None = None,
    split_report_path: Path | str | None = None,
    m1_gate_path: Path | str | None = None,
    fixture_metadata_path: Path | str | None = None,
    evaluation_split: SplitName = "dev",
    confirm_test_evaluation: bool = False,
) -> InputBundle:
    """Load and validate all baseline inputs before training.

    The M1 and explicit-test guards intentionally run before checking the other
    paths.  This makes a failed formal gate cheap and deterministic, and prevents
    downstream/model imports from being reached for a disallowed evaluation.
    """

    if mode not in ("formal", "synthetic"):
        raise BaselineInputError("mode must be formal or synthetic")
    if evaluation_split not in _SPLITS:
        raise BaselineInputError("evaluation split must be train, dev, or test")

    if m1_gate_path is None:
        raise BaselineInputError("M1 gate path is required")
    gate = _read_json_object(m1_gate_path, "M1 gate")
    if mode == "formal" and (
        gate.get("gate") != "M1" or gate.get("passed") is not True
    ):
        raise BaselineInputError("M1 gate has not passed")
    if evaluation_split == "test" and confirm_test_evaluation is not True:
        raise BaselineInputError("test evaluation requires explicit confirmation")

    if mode == "synthetic":
        if fixture_metadata_path is None:
            raise BaselineInputError(
                "synthetic mode requires fixture metadata"
            )
        metadata = _read_json_object(fixture_metadata_path, "fixture metadata")
        if (
            metadata.get("dataset_kind") != "synthetic_fixture"
            or metadata.get("fixture_version") != _SYNTHETIC_FIXTURE_VERSION
        ):
            raise BaselineInputError(
                "synthetic mode requires dataset_kind and fixture_version metadata"
            )

    paths: dict[str, Path | str | None] = {
        "content": content_path,
        "Gold": gold_path,
        "train IDs": train_ids_path,
        "dev IDs": dev_ids_path,
        "test IDs": test_ids_path,
        "split report": split_report_path,
    }
    missing_count = sum(value is None for value in paths.values())
    if missing_count:
        raise BaselineInputError(
            f"required baseline input paths are missing (count={missing_count})"
        )

    # The values are known to be non-None after the check above; keeping the
    # explicit assertions makes that contract clear to type checkers as well.
    assert content_path is not None
    assert gold_path is not None
    assert train_ids_path is not None
    assert dev_ids_path is not None
    assert test_ids_path is not None
    assert split_report_path is not None

    posts = _load_content_jsonl(content_path)
    gold = _load_gold_jsonl(gold_path)
    split_values = {
        "train": _load_split_ids(train_ids_path, "train"),
        "dev": _load_split_ids(dev_ids_path, "dev"),
        "test": _load_split_ids(test_ids_path, "test"),
    }
    _validate_join_and_splits(posts, gold, split_values)
    split_report = _read_json_object(split_report_path, "split report")
    _validate_split_report(split_report)

    input_hashes = {
        "content": sha256_file(content_path),
        "gold": sha256_file(gold_path),
        "train_ids": sha256_file(train_ids_path),
        "dev_ids": sha256_file(dev_ids_path),
        "test_ids": sha256_file(test_ids_path),
        "split_report": sha256_file(split_report_path),
        "m1_gate": sha256_file(m1_gate_path),
    }
    if fixture_metadata_path is not None:
        input_hashes["fixture_metadata"] = sha256_file(fixture_metadata_path)

    return InputBundle(
        mode=mode,
        posts=posts,
        gold=gold,
        splits=SplitAssignments(
            train=frozenset(split_values["train"]),
            dev=frozenset(split_values["dev"]),
            test=frozenset(split_values["test"]),
        ),
        evaluation_split=evaluation_split,
        confirm_test_evaluation=bool(confirm_test_evaluation),
        input_hashes=input_hashes,
    )


def _read_json(path: Path | str, context: str) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, TypeError, ValueError) as exc:
        raise BaselineInputError(f"{context} input could not be read") from exc
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BaselineInputError(f"{context} JSON is invalid") from exc


def _read_json_object(path: Path | str, context: str) -> dict[str, Any]:
    value = _read_json(path, context)
    if not isinstance(value, dict):
        raise BaselineInputError(f"{context} must be a JSON object")
    return value


def _read_jsonl(path: Path | str, context: str) -> list[dict[str, Any]]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, TypeError, ValueError) as exc:
        raise BaselineInputError(f"{context} input could not be read") from exc

    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BaselineInputError(f"{context} JSONL row is invalid") from exc
        if not isinstance(value, dict):
            raise BaselineInputError(f"{context} JSONL rows must be objects")
        rows.append(value)
    return rows


def _load_content_jsonl(path: Path | str) -> dict[str, ContentPost]:
    rows = _read_jsonl(path, "content")
    posts: dict[str, ContentPost] = {}
    for row in rows:
        post_id = _required_text(row, "post_id", "content")
        if post_id in posts:
            raise BaselineInputError("duplicate content post_id")
        blogger_id = _required_text(row, "blogger_id", "content")
        text = _required_field_text(row, "text", "content")
        published_at = _parse_published_at(row.get("published_at"))
        history_key = (
            "blogger_history_refs"
            if "blogger_history_refs" in row
            else "history_refs"
        )
        raw_history = row.get(history_key, [])
        if not isinstance(raw_history, list) or not all(
            isinstance(ref, str) and bool(ref.strip()) for ref in raw_history
        ):
            raise BaselineInputError("content history_refs field is invalid")
        content_group_id = row.get("content_group_id")
        if content_group_id is not None and not isinstance(content_group_id, str):
            raise BaselineInputError("content content_group_id field is invalid")
        posts[post_id] = ContentPost(
            post_id=post_id,
            blogger_id=blogger_id,
            published_at=published_at,
            text=text,
            history_refs=tuple(raw_history),
            content_group_id=content_group_id,
        )
    return posts


def _load_gold_jsonl(path: Path | str) -> dict[str, GoldRecord]:
    rows = _read_jsonl(path, "Gold")
    gold: dict[str, GoldRecord] = {}
    for row in rows:
        post_id = _required_text(row, "post_id", "Gold")
        if post_id in gold:
            raise BaselineInputError("duplicate Gold post_id")
        label = row.get("label")
        if not isinstance(label, str) or label not in LABELS:
            raise BaselineInputError("invalid formal Gold label")
        gold[post_id] = GoldRecord(post_id=post_id, label=label)
    return gold


def _load_split_ids(path: Path | str, split: SplitName) -> set[str]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, TypeError, ValueError) as exc:
        raise BaselineInputError(f"{split} split IDs input could not be read") from exc

    values: set[str] = set()
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        if value in values:
            raise BaselineInputError("duplicate split IDs")
        values.add(value)
    return values


def _validate_join_and_splits(
    posts: dict[str, ContentPost],
    gold: dict[str, GoldRecord],
    split_values: dict[str, set[str]],
) -> None:
    post_ids = set(posts)
    gold_ids = set(gold)
    # Gold is defined only for target posts.  Content may additionally carry
    # anonymous history-only rows referenced by those targets; every Gold ID
    # must still resolve to content.
    if not gold_ids.issubset(post_ids):
        raise BaselineInputError("Gold/content coverage mismatch")

    split_names = ("train", "dev", "test")
    overlap_count = 0
    seen: set[str] = set()
    for split in split_names:
        current = split_values[split]
        overlap_count += len(seen.intersection(current))
        seen.update(current)
    if overlap_count:
        raise BaselineInputError("split IDs overlap")
    if seen != gold_ids:
        raise BaselineInputError("split/Gold coverage mismatch")

    labels = set(LABELS)
    for split in split_names:
        split_labels = {gold[post_id].label for post_id in split_values[split]}
        if split_labels != labels:
            raise BaselineInputError("each split must contain all three labels")


def _validate_split_report(report: dict[str, Any]) -> None:
    values: dict[str, Any] = {}
    for field in _LEAKAGE_FIELDS:
        value = _lookup_split_report_field(report, field)
        if value is _MISSING:
            raise BaselineInputError("split leakage evidence is incomplete")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BaselineInputError("split leakage evidence is invalid")
        values[field] = value

    if any(value != 0 for value in values.values()):
        raise BaselineInputError("split leakage check failed")

    status = _lookup_split_report_field(report, "near_duplicate_check_status")
    if status is _MISSING:
        raise BaselineInputError("split leakage evidence is incomplete")
    if not isinstance(status, str) or status.strip().lower() not in {
        "passed",
        "pass",
        "complete",
    }:
        raise BaselineInputError("split leakage evidence is incomplete")


_MISSING = object()


def _lookup_split_report_field(report: dict[str, Any], field: str) -> Any:
    """Find a leakage field in common flat or nested split-report layouts."""

    if field in report:
        return report[field]
    candidates: list[Any] = []
    for key in ("split_leakage", "leakage", "leakage_checks"):
        value = report.get(key)
        if isinstance(value, dict):
            candidates.append(value)
            observed = value.get("observed")
            if isinstance(observed, dict):
                candidates.append(observed)
    checks = report.get("checks")
    if isinstance(checks, dict):
        split_check = checks.get("split_leakage")
        if isinstance(split_check, dict):
            candidates.append(split_check)
            observed = split_check.get("observed")
            if isinstance(observed, dict):
                candidates.append(observed)
    for candidate in candidates:
        if field in candidate:
            return candidate[field]
    return _MISSING


def _required_text(row: dict[str, Any], field: str, context: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BaselineInputError(f"{context} {field} field is invalid")
    return value


def _required_field_text(row: dict[str, Any], field: str, context: str) -> str:
    if field not in row:
        raise BaselineInputError(f"{context} {field} field is missing")
    value = row.get(field)
    if not isinstance(value, str):
        raise BaselineInputError(f"{context} {field} field is invalid")
    # Empty text is valid for image-first records in Schema v1.2.
    return value


def _parse_published_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BaselineInputError("content published_at field is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BaselineInputError("content published_at field is invalid") from exc


__all__ = [
    "Mode",
    "SplitName",
    "LABELS",
    "BaselineInputError",
    "ContentPost",
    "GoldRecord",
    "SplitAssignments",
    "InputBundle",
    "load_input_bundle",
    "sha256_file",
]

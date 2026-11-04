#!/usr/bin/env python3
"""Validate B's completed M1 10% privacy spotcheck export.

The validator is deliberately read-only with respect to the reviewed data.  It
compares the exported review against the frozen sampling manifest and, when a
canonical dataset is supplied, verifies the recorded dataset fingerprint and
that every sampled post still exists exactly once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


ALLOWED_DECISIONS = {"allow", "redact", "exclude"}
COMPLETED_STATUS = "completed_B_spotcheck_10pct_review"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def duplicate_values(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def valid_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def canonical_ids(path: Path) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    malformed: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(f"line {line_number}: invalid JSON")
            continue
        post_id = row.get("post_id") if isinstance(row, dict) else None
        if not isinstance(post_id, str) or not post_id:
            malformed.append(f"line {line_number}: missing post_id")
            continue
        ids.append(post_id)
    return ids, malformed


def validate(
    *,
    manifest_path: Path,
    review_path: Path,
    dataset_path: Path | None = None,
) -> dict[str, Any]:
    manifest = load_object(manifest_path)
    review = load_object(review_path)
    errors: list[str] = []
    warnings: list[str] = []

    manifest_ids_raw = manifest.get("post_ids")
    if not isinstance(manifest_ids_raw, list) or not all(
        isinstance(post_id, str) and post_id for post_id in manifest_ids_raw
    ):
        errors.append("manifest.post_ids must be a list of non-empty strings")
        manifest_ids: list[str] = []
    else:
        manifest_ids = list(manifest_ids_raw)

    manifest_duplicates = duplicate_values(manifest_ids)
    if manifest_duplicates:
        errors.append(f"manifest contains duplicate post_ids: {manifest_duplicates[:5]}")

    manifest_sample_size = manifest.get("sample_size")
    if manifest_sample_size != len(manifest_ids):
        errors.append(
            "manifest.sample_size does not equal the number of manifest post_ids: "
            f"{manifest_sample_size!r} != {len(manifest_ids)}"
        )

    if review.get("status") != COMPLETED_STATUS:
        errors.append(
            f"review.status must be {COMPLETED_STATUS!r}, got {review.get('status')!r}"
        )
    if review.get("reviewer") != "B":
        errors.append(f"review.reviewer must be 'B', got {review.get('reviewer')!r}")
    if not valid_iso8601(review.get("exported_at")):
        errors.append("review.exported_at must be a valid ISO-8601 timestamp")

    actual_manifest_sha = sha256_file(manifest_path)
    recorded_manifest_sha = str(review.get("manifest_sha256", "")).lower()
    if recorded_manifest_sha != actual_manifest_sha:
        errors.append(
            "review.manifest_sha256 does not match the frozen manifest: "
            f"{recorded_manifest_sha or '<missing>'} != {actual_manifest_sha}"
        )

    for field in ("seed", "population"):
        if review.get(field) != manifest.get(field):
            errors.append(
                f"review.{field} does not match manifest.{field}: "
                f"{review.get(field)!r} != {manifest.get(field)!r}"
            )

    items_raw = review.get("items")
    if not isinstance(items_raw, list):
        errors.append("review.items must be a list")
        items: list[Mapping[str, Any]] = []
    else:
        items = [item for item in items_raw if isinstance(item, dict)]
        if len(items) != len(items_raw):
            errors.append("every review.items entry must be a JSON object")

    if review.get("sample_count") != len(items):
        errors.append(
            "review.sample_count does not equal review item count: "
            f"{review.get('sample_count')!r} != {len(items)}"
        )
    if len(items) != len(manifest_ids):
        errors.append(
            f"review item count does not match manifest: {len(items)} != {len(manifest_ids)}"
        )

    item_ids: list[str] = []
    calculated_counts = Counter({decision: 0 for decision in ALLOWED_DECISIONS})
    for position, item in enumerate(items, 1):
        post_id = item.get("post_id")
        if not isinstance(post_id, str) or not post_id:
            errors.append(f"item {position} has no valid post_id")
            continue
        item_ids.append(post_id)
        if item.get("number") != position:
            errors.append(
                f"item {position} has unexpected number {item.get('number')!r}"
            )
        if item.get("reviewed") is not True:
            errors.append(f"item {position} ({post_id}) is not reviewed=true")
        decision = item.get("decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(
                f"item {position} ({post_id}) has invalid decision {decision!r}"
            )
        else:
            calculated_counts[decision] += 1
        notes = item.get("notes")
        if not isinstance(notes, str):
            errors.append(f"item {position} ({post_id}) notes must be a string")
        elif decision in {"redact", "exclude"} and not notes.strip():
            errors.append(
                f"item {position} ({post_id}) decision {decision!r} requires notes"
            )
        if not valid_iso8601(item.get("updated_at")):
            errors.append(
                f"item {position} ({post_id}) has no valid updated_at timestamp"
            )

    item_duplicates = duplicate_values(item_ids)
    if item_duplicates:
        errors.append(f"review contains duplicate post_ids: {item_duplicates[:5]}")

    manifest_set = set(manifest_ids)
    item_set = set(item_ids)
    missing_from_review = sorted(manifest_set - item_set)
    unexpected_in_review = sorted(item_set - manifest_set)
    if missing_from_review:
        errors.append(
            f"review is missing {len(missing_from_review)} manifest post_ids: "
            f"{missing_from_review[:5]}"
        )
    if unexpected_in_review:
        errors.append(
            f"review contains {len(unexpected_in_review)} unexpected post_ids: "
            f"{unexpected_in_review[:5]}"
        )
    if item_ids and item_ids != manifest_ids:
        errors.append("review item order does not exactly match manifest.post_ids order")

    recorded_counts = review.get("decision_counts")
    expected_counts = {
        decision: calculated_counts[decision]
        for decision in ("allow", "redact", "exclude")
    }
    if recorded_counts != expected_counts:
        errors.append(
            f"review.decision_counts is inconsistent: {recorded_counts!r} != {expected_counts!r}"
        )

    dataset_summary: dict[str, Any] | None = None
    if dataset_path is not None:
        actual_dataset_sha = sha256_file(dataset_path)
        recorded_dataset_sha = str(review.get("dataset_sha256", "")).lower()
        if recorded_dataset_sha != actual_dataset_sha:
            errors.append(
                "review.dataset_sha256 does not match the supplied canonical dataset: "
                f"{recorded_dataset_sha or '<missing>'} != {actual_dataset_sha}"
            )
        dataset_post_ids, malformed = canonical_ids(dataset_path)
        dataset_duplicates = duplicate_values(dataset_post_ids)
        if malformed:
            errors.extend(f"canonical dataset {message}" for message in malformed[:20])
        if dataset_duplicates:
            errors.append(
                f"canonical dataset contains duplicate post_ids: {dataset_duplicates[:5]}"
            )
        absent = sorted(manifest_set - set(dataset_post_ids))
        if absent:
            errors.append(
                f"canonical dataset is missing {len(absent)} sampled post_ids: {absent[:5]}"
            )
        dataset_summary = {
            "path": str(dataset_path),
            "sha256": actual_dataset_sha,
            "record_count": len(dataset_post_ids),
            "sample_ids_missing": len(absent),
        }
    elif not review.get("dataset_sha256"):
        warnings.append("review.dataset_sha256 is missing and no dataset was supplied")

    return {
        "validator": "m1_spotcheck_review_v1",
        "passed": not errors,
        "manifest": {
            "path": str(manifest_path),
            "sha256": actual_manifest_sha,
            "status": manifest.get("status"),
            "population": manifest.get("population"),
            "sample_size": len(manifest_ids),
        },
        "review": {
            "path": str(review_path),
            "sha256": sha256_file(review_path),
            "status": review.get("status"),
            "reviewer": review.get("reviewer"),
            "sample_count": len(items),
            "decision_counts": expected_counts,
        },
        "dataset": dataset_summary,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate B's completed M1 10% privacy spotcheck export"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = validate(
            manifest_path=args.manifest,
            review_path=args.review,
            dataset_path=args.dataset,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "validator": "m1_spotcheck_review_v1",
            "passed": False,
            "errors": [str(exc)],
            "warnings": [],
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

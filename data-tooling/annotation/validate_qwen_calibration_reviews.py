#!/usr/bin/env python3
"""Validate independent A/B reviews of the fixed Qwen calibration sample.

The script validates one or both reviewer exports against the same manifest.  It
only computes descriptive counts; it deliberately does not choose 4B versus
``--no-llm`` because the task guide leaves that as an A/B decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


LABELS = {"明广", "暗广", "非广", "uncertain", "out_of_scope"}
TERNARY = {"yes", "no", "na"}
ERROR_TYPES = {"", "none", "wrong_label", "unsupported_evidence", "missing_evidence", "model_error", "other"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_review(
    manifest: dict[str, Any], review: dict[str, Any], reviewer: str, path: Path
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    expected_items = manifest.get("items") or []
    expected_ids = [str(item.get("post_id") or "") for item in expected_items]
    items = review.get("items") or []
    item_ids = [str(item.get("post_id") or "") for item in items]

    if review.get("status") != "completed_independent_human_review":
        errors.append(f"{reviewer}: status is not completed_independent_human_review")
    if review.get("reviewer") != reviewer:
        errors.append(f"{reviewer}: reviewer field is {review.get('reviewer')!r}")
    if review.get("dataset_fingerprint_sha256") != manifest.get("dataset_fingerprint_sha256"):
        errors.append(f"{reviewer}: dataset fingerprint does not match manifest")
    if review.get("sample_count") != len(expected_ids):
        errors.append(f"{reviewer}: sample_count must be {len(expected_ids)}")
    if len(items) != len(expected_ids):
        errors.append(f"{reviewer}: items count must be {len(expected_ids)}")
    if len(item_ids) != len(set(item_ids)):
        errors.append(f"{reviewer}: duplicate post_id values")
    if item_ids != expected_ids:
        errors.append(f"{reviewer}: post_id sequence does not exactly match manifest")

    for index, item in enumerate(items, start=1):
        prefix = f"{reviewer}: item {index}"
        if item.get("number") != index:
            errors.append(f"{prefix}: number must be {index}")
        if item.get("label") not in LABELS:
            errors.append(f"{prefix}: invalid label {item.get('label')!r}")
        if item.get("reasonable") not in TERNARY:
            errors.append(f"{prefix}: invalid reasonable value {item.get('reasonable')!r}")
        if item.get("saved_time") not in TERNARY:
            errors.append(f"{prefix}: invalid saved_time value {item.get('saved_time')!r}")
        if item.get("error_type", "") not in ERROR_TYPES:
            errors.append(f"{prefix}: invalid error_type {item.get('error_type')!r}")
        if item.get("reviewed") is not True:
            errors.append(f"{prefix}: reviewed must be true")
        if not str(item.get("notes") or "").strip():
            errors.append(f"{prefix}: notes must not be blank")

    summary = {
        "reviewer": reviewer,
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "valid": not errors,
        "item_count": len(items),
        "labels": dict(Counter(str(item.get("label")) for item in items)),
        "reasonable": dict(Counter(str(item.get("reasonable")) for item in items)),
        "saved_time": dict(Counter(str(item.get("saved_time")) for item in items)),
        "error_types": dict(Counter(str(item.get("error_type") or "") for item in items)),
    }
    return errors, summary


def validate(manifest_path: Path, review_paths: dict[str, Path]) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    all_errors: list[str] = []
    summaries: dict[str, Any] = {}
    reviews: dict[str, dict[str, Any]] = {}
    for reviewer, path in review_paths.items():
        review = read_json(path)
        reviews[reviewer] = review
        errors, summary = validate_review(manifest, review, reviewer, path)
        all_errors.extend(errors)
        summaries[reviewer] = summary

    comparison: dict[str, Any] | None = None
    if set(reviews) == {"A", "B"} and not all_errors:
        a_items = reviews["A"]["items"]
        b_items = reviews["B"]["items"]
        comparison = {
            "human_label_agreement_count": sum(a["label"] == b["label"] for a, b in zip(a_items, b_items)),
            "reasonable_agreement_count": sum(a["reasonable"] == b["reasonable"] for a, b in zip(a_items, b_items)),
            "saved_time_agreement_count": sum(a["saved_time"] == b["saved_time"] for a, b in zip(a_items, b_items)),
            "sample_count": len(a_items),
            "final_model_choice": "pending_A_B_joint_decision",
        }

    return {
        "passed": not all_errors,
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256(manifest_path),
        "dataset_fingerprint_sha256": manifest.get("dataset_fingerprint_sha256"),
        "reviews": summaries,
        "comparison": comparison,
        "errors": all_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-a", type=Path)
    parser.add_argument("--review-b", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.review_a and not args.review_b:
        parser.error("at least one of --review-a or --review-b is required")
    review_paths = {
        reviewer: path
        for reviewer, path in (("A", args.review_a), ("B", args.review_b))
        if path is not None
    }
    result = validate(args.manifest, review_paths)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

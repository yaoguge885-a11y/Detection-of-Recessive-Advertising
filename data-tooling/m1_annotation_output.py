#!/usr/bin/env python3
"""Validate one human annotation stream against its locked M1 batch.

The manual annotator writes consecutive pretty-printed JSON objects rather than
strict one-object-per-line JSONL.  This validator deliberately supports both
formats and rejects duplicate IDs, skipped IDs, non-human methods, wrong
annotators, invalid labels, and unlocked manifests when formal mode is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


LABELS = {"明广", "暗广", "非广", "uncertain", "out_of_scope"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_stream(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        value, index = decoder.raw_decode(text, index)
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError(f"{path}: annotation stream contains a non-object")
            rows.append(candidate)
    return rows


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected one JSON object")
    return payload


def validate_annotation(
    *,
    batch_path: Path,
    manifest_path: Path,
    annotation_path: Path,
    annotator_id: str,
    expected_count: int,
    allow_partial: bool,
    require_locked: bool,
    mode: str,
) -> dict[str, Any]:
    errors: list[str] = []
    batch = load_stream(batch_path)
    manifest = load_object(manifest_path)
    annotations = load_stream(annotation_path)

    batch_ids = [str(row.get("post_id") or "") for row in batch]
    manifest_ids = manifest.get("post_ids")
    if not isinstance(manifest_ids, list):
        manifest_ids = []
        errors.append("manifest.post_ids must be a list")
    else:
        manifest_ids = [str(post_id) for post_id in manifest_ids]
    annotation_ids = [str(row.get("post_id") or "") for row in annotations]

    if len(batch_ids) != expected_count:
        errors.append(f"batch count is {len(batch_ids)}, expected {expected_count}")
    if len(set(batch_ids)) != len(batch_ids):
        errors.append("batch contains duplicate post_ids")
    if batch_ids != manifest_ids:
        errors.append("batch IDs/order do not exactly match manifest.post_ids")
    if require_locked and manifest.get("status") != "locked":
        errors.append("formal validation requires manifest.status='locked'")
    if len(set(annotation_ids)) != len(annotation_ids):
        errors.append("annotation stream contains duplicate post_ids")
    if allow_partial:
        if annotation_ids != batch_ids[: len(annotation_ids)]:
            errors.append("partial annotations must be an exact prefix of the locked batch")
    elif annotation_ids != batch_ids:
        errors.append("complete annotations must exactly match locked batch IDs/order")

    for number, row in enumerate(annotations, start=1):
        prefix = f"annotation {number}"
        if not annotation_ids[number - 1]:
            errors.append(f"{prefix}: missing post_id")
        if row.get("annotator_id") != annotator_id:
            errors.append(f"{prefix}: annotator_id must be {annotator_id!r}")
        if row.get("annotation_method") != "human":
            errors.append(f"{prefix}: annotation_method must be 'human'")
        if row.get("label") not in LABELS:
            errors.append(f"{prefix}: invalid label {row.get('label')!r}")
        confidence = row.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append(f"{prefix}: confidence must be numeric")
        elif not 0 <= float(confidence) <= 1:
            errors.append(f"{prefix}: confidence must be in [0, 1]")

    completed = len(annotations)
    return {
        "passed": not errors,
        "mode": mode,
        "allow_partial": allow_partial,
        "annotator_id": annotator_id,
        "expected_count": expected_count,
        "completed_count": completed,
        "remaining_count": max(0, expected_count - completed),
        "batch": {
            "path": str(batch_path.resolve()),
            "sha256": sha256_file(batch_path),
        },
        "manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": sha256_file(manifest_path),
            "status": manifest.get("status"),
        },
        "annotation": {
            "path": str(annotation_path.resolve()),
            "sha256": sha256_file(annotation_path),
            "label_counts": dict(Counter(str(row.get("label")) for row in annotations)),
            "annotation_method_counts": dict(
                Counter(str(row.get("annotation_method")) for row in annotations)
            ),
        },
        "limitations": [
            "The output proves saved method/annotator fields, not that media were actually viewed.",
            "Human-process evidence and command receipts remain required.",
        ],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an M1 human annotation stream")
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--annotation", type=Path, required=True)
    parser.add_argument("--annotator-id", choices=("A", "B"), required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument("--mode", choices=("human_only", "qwen_assisted"), required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--technical-only", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate_annotation(
            batch_path=args.batch,
            manifest_path=args.manifest,
            annotation_path=args.annotation,
            annotator_id=args.annotator_id,
            expected_count=args.expected_count,
            allow_partial=args.allow_partial,
            require_locked=not args.technical_only,
            mode=args.mode,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"passed": False, "errors": [str(exc)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

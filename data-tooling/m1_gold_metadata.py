#!/usr/bin/env python3
"""Attach creator/content-group metadata to Gold with strict leakage prerequisites."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


GOLD_LABELS = {"明广", "暗广", "非广"}


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
        values = value if isinstance(value, list) else [value]
        for row in values:
            if not isinstance(row, dict):
                raise ValueError(f"{path}: stream contains a non-object")
            rows.append(row)
    return rows


def unique_index(rows: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, start=1):
        post_id = row.get("post_id")
        if not isinstance(post_id, str) or not post_id:
            raise ValueError(f"{name} row {number}: missing post_id")
        if post_id in result:
            raise ValueError(f"{name}: duplicate post_id {post_id}")
        result[post_id] = row
    return result


def attach_metadata(
    *, gold_path: Path, canonical_path: Path, minimum_count: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    gold_rows = load_stream(gold_path)
    canonical_rows = load_stream(canonical_path)
    gold = unique_index(gold_rows, "gold")
    canonical = unique_index(canonical_rows, "canonical")
    errors: list[str] = []
    output: list[dict[str, Any]] = []
    content_group_count = 0

    if len(gold_rows) < minimum_count:
        errors.append(f"gold count is {len(gold_rows)}, below required {minimum_count}")
    for post_id, row in gold.items():
        if row.get("label") not in GOLD_LABELS:
            errors.append(f"{post_id}: invalid Gold label {row.get('label')!r}")
        source = canonical.get(post_id)
        if source is None:
            errors.append(f"{post_id}: missing from canonical")
            continue
        blogger_id = source.get("blogger_id")
        if not isinstance(blogger_id, str) or not blogger_id.strip():
            errors.append(f"{post_id}: canonical blogger_id is missing")
            continue
        content_group_id = source.get("content_group_id")
        if content_group_id not in (None, ""):
            content_group_count += 1
        enriched = dict(row)
        enriched["blogger_id"] = blogger_id
        enriched["content_group_id"] = content_group_id or None
        output.append(enriched)

    report = {
        "passed": not errors and len(output) == len(gold_rows),
        "gold_path": str(gold_path.resolve()),
        "gold_sha256": sha256_file(gold_path),
        "canonical_path": str(canonical_path.resolve()),
        "canonical_sha256": sha256_file(canonical_path),
        "gold_count": len(gold_rows),
        "enriched_count": len(output),
        "unique_blogger_count": len({row["blogger_id"] for row in output}),
        "content_group_populated_count": content_group_count,
        "minimum_count": minimum_count,
        "errors": errors,
    }
    return output, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach split metadata to M1 Gold")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-count", type=int, default=1500)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        rows, report = attach_metadata(
            gold_path=args.gold,
            canonical_path=args.canonical,
            minimum_count=args.minimum_count,
        )
        if not args.check_only:
            if args.output is None:
                raise ValueError("--output is required unless --check-only is used")
            if args.output.exists():
                raise FileExistsError(f"refusing to overwrite {args.output}")
            if report["passed"]:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("w", encoding="utf-8", newline="\n") as handle:
                    for row in rows:
                        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                report["output_path"] = str(args.output.resolve())
                report["output_sha256"] = sha256_file(args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"passed": False, "errors": [str(exc)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

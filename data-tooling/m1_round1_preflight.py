#!/usr/bin/env python3
"""Preflight B's Round-1 human-only annotation entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def load_batch(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        if not isinstance(record, dict) or not record.get("post_id"):
            errors.append(f"line {line_number}: invalid record/post_id")
            continue
        records.append(record)
    return records, errors


def inspect_existing_annotations(output_dir: Path) -> dict[str, Any]:
    files = sorted(output_dir.glob("B_*.json*")) if output_dir.exists() else []
    errors: list[str] = []
    completed: set[str] = set()
    methods: set[str] = set()
    annotators: set[str] = set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            errors.append(f"invalid annotation JSON: {path}")
            continue
        rows = payload if isinstance(payload, list) else [payload]
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"annotation entry is not an object: {path}")
                continue
            post_id = row.get("post_id")
            if isinstance(post_id, str) and post_id:
                completed.add(post_id)
            methods.add(str(row.get("annotation_method", "")))
            annotators.add(str(row.get("annotator_id", "")))
    illegal_methods = sorted(methods - {"", "human"})
    illegal_annotators = sorted(annotators - {"", "B"})
    if illegal_methods:
        errors.append(f"existing output has illegal annotation methods: {illegal_methods}")
    if illegal_annotators:
        errors.append(f"existing output has non-B annotators: {illegal_annotators}")
    return {
        "output_dir": str(output_dir),
        "existing_files": [str(path) for path in files],
        "completed_post_id_count": len(completed),
        "annotation_methods": sorted(methods - {""}),
        "annotator_ids": sorted(annotators - {""}),
        "errors": errors,
    }


def preflight(
    *,
    batch_path: Path,
    manifest_path: Path,
    guide_path: Path,
    media_base: Path,
    output_dir: Path,
    require_locked: bool,
) -> dict[str, Any]:
    manifest = load_object(manifest_path)
    records, errors = load_batch(batch_path)
    manifest_ids = manifest.get("post_ids", [])
    if not isinstance(manifest_ids, list):
        errors.append("manifest.post_ids must be a list")
        manifest_ids = []
    batch_ids = [str(record["post_id"]) for record in records]
    if len(batch_ids) != 100:
        errors.append(f"Round 1 batch must contain 100 records, got {len(batch_ids)}")
    if len(set(batch_ids)) != len(batch_ids):
        errors.append("Round 1 batch contains duplicate post_ids")
    if batch_ids != manifest_ids:
        errors.append("Round 1 JSONL order/IDs do not exactly match the manifest")
    if manifest.get("batch_kind") != "pilot":
        errors.append("Round 1 manifest batch_kind must be pilot")
    if manifest.get("formal_second_round") is not False:
        errors.append("Round 1 manifest must not be marked formal_second_round")
    if require_locked and manifest.get("status") != "locked":
        errors.append("formal Round 1 entry requires a manifest with status='locked'")

    media_refs = 0
    missing_media: list[dict[str, str]] = []
    for record in records:
        for media in record.get("media", []) or []:
            if not isinstance(media, dict) or not media.get("ref"):
                continue
            media_refs += 1
            ref = str(media["ref"])
            path = media_base / ref
            if not path.is_file() or path.stat().st_size == 0:
                missing_media.append({"post_id": str(record["post_id"]), "ref": ref})
    if missing_media:
        errors.append(f"Round 1 has {len(missing_media)} missing/zero-byte media refs")

    output = inspect_existing_annotations(output_dir)
    errors.extend(output["errors"])
    guide_text = guide_path.read_text(encoding="utf-8-sig")
    if "人工标注指南" not in guide_text:
        errors.append("annotation guide heading was not recognized")

    command = [
        "<Python>",
        "data-tooling/annotation/manual_review_annotate.py",
        "--input",
        str(batch_path),
        "--guide",
        str(guide_path),
        "--output-dir",
        str(output_dir),
        "--limit",
        "100",
        "--no-llm",
        "--no-supplement",
        "--media-base",
        str(media_base),
        "--auto-view",
        "--annotator-id",
        "B",
        "--auto-threshold",
        "0",
    ]
    return {
        "preflight": "m1_round1_B_v1",
        "passed": not errors,
        "mode": "formal_locked" if require_locked else "technical_preflight_only",
        "batch": {
            "path": str(batch_path),
            "sha256": sha256_file(batch_path),
            "record_count": len(batch_ids),
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "manifest_status": manifest.get("status"),
        },
        "guide": {"path": str(guide_path), "sha256": sha256_file(guide_path)},
        "media": {
            "base": str(media_base),
            "reference_count": media_refs,
            "missing_or_zero_byte_count": len(missing_media),
            "examples": missing_media[:20],
        },
        "output": output,
        "required_human_only_options": {
            "annotator_id": "B",
            "no_llm": True,
            "auto_threshold": 0,
            "no_supplement": True,
            "auto_view": True,
        },
        "command_argv": command,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight B Round-1 entry")
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--media-base", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--technical-only", action="store_true")
    args = parser.parse_args()
    try:
        report = preflight(
            batch_path=args.batch,
            manifest_path=args.manifest,
            guide_path=args.guide,
            media_base=args.media_base,
            output_dir=args.output_dir,
            require_locked=not args.technical_only,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"preflight": "m1_round1_B_v1", "passed": False, "errors": [str(exc)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

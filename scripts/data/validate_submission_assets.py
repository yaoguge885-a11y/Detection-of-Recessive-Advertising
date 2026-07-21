#!/usr/bin/env python3
"""Validate the two P1 JSON submission assets using only the Python standard library."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "data" / "schema" / "data_schema_v1.json"
DATASET_PATH = ROOT / "data" / "synthetic" / "simulated_posts_v1.json"

CONTENT_REQUIRED = {"schema_version", "post_id", "platform", "source_type", "blogger_id", "text", "media", "provenance", "privacy"}
CONTENT_ALLOWED = CONTENT_REQUIRED | {"published_at", "comments", "blogger_history_refs"}
ANNOTATION_REQUIRED = {"post_id", "annotator_id", "guide_version", "label", "confidence", "evidence_codes", "evidence", "uncertain_reason", "annotated_at"}
ANNOTATION_ALLOWED = ANNOTATION_REQUIRED
MEDIA_REQUIRED = {"media_id", "type", "local_ref", "sha256", "phash", "ocr_text"}
COMMENT_REQUIRED = {"comment_id", "author_id", "text", "like_count", "is_pinned"}
PROVENANCE_REQUIRED = {"source_ref_hash", "collected_at", "collector", "terms_checked_at"}
PRIVACY_REQUIRED = {"anonymized", "contains_sensitive_data"}
VALID_LABELS = {"明广", "暗广", "非广", "out_of_scope", "uncertain"}
VALID_CODES = {"D", "C", "P", "A", "V", "B", "M"}
EXPECTED_DISTRIBUTION = {"明广": 5, "暗广": 12, "非广": 8, "out_of_scope": 3, "uncertain": 2}


def error(errors: list[str], message: str) -> None:
    errors.append(message)


def assert_keys(errors: list[str], value: dict[str, Any], required: set[str], allowed: set[str], where: str) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        error(errors, f"{where}: missing fields {sorted(missing)}")
    if unknown:
        error(errors, f"{where}: unknown fields {sorted(unknown)}")


def validate_content(record: Any, index: int, errors: list[str]) -> None:
    where = f"content_records[{index}]"
    if not isinstance(record, dict):
        error(errors, f"{where}: must be an object")
        return
    assert_keys(errors, record, CONTENT_REQUIRED, CONTENT_ALLOWED, where)
    if record.get("schema_version") != "1.0":
        error(errors, f"{where}: schema_version must be 1.0")
    if not isinstance(record.get("post_id"), str) or not record["post_id"].startswith("post_"):
        error(errors, f"{where}: post_id must start with post_")
    if record.get("platform") not in {"wechat_official_account", "weibo", "xiaohongshu", "douyin", "synthetic", "other"}:
        error(errors, f"{where}: invalid platform")
    if record.get("source_type") not in {"public_dataset", "manual_public_collection", "authorized_export", "synthetic"}:
        error(errors, f"{where}: invalid source_type")
    if not isinstance(record.get("blogger_id"), str) or not record["blogger_id"].startswith("blogger_"):
        error(errors, f"{where}: blogger_id must start with blogger_")
    if not isinstance(record.get("text"), str):
        error(errors, f"{where}: text must be a string")
    if not isinstance(record.get("media"), list) or not isinstance(record.get("comments", []), list) or not isinstance(record.get("blogger_history_refs", []), list):
        error(errors, f"{where}: media/comments/blogger_history_refs must be arrays")
    for media_index, item in enumerate(record.get("media", [])):
        if not isinstance(item, dict):
            error(errors, f"{where}.media[{media_index}]: must be object")
            continue
        assert_keys(errors, item, MEDIA_REQUIRED, MEDIA_REQUIRED, f"{where}.media[{media_index}]")
    for comment_index, item in enumerate(record.get("comments", [])):
        if not isinstance(item, dict):
            error(errors, f"{where}.comments[{comment_index}]: must be object")
            continue
        assert_keys(errors, item, COMMENT_REQUIRED, COMMENT_REQUIRED, f"{where}.comments[{comment_index}]")
        if not isinstance(item.get("like_count"), int) or item.get("like_count", -1) < 0:
            error(errors, f"{where}.comments[{comment_index}]: like_count must be a nonnegative integer")
        if not isinstance(item.get("is_pinned"), bool):
            error(errors, f"{where}.comments[{comment_index}]: is_pinned must be boolean")
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        error(errors, f"{where}: provenance must be object")
    else:
        assert_keys(errors, provenance, PROVENANCE_REQUIRED, PROVENANCE_REQUIRED, f"{where}.provenance")
    privacy = record.get("privacy")
    if not isinstance(privacy, dict):
        error(errors, f"{where}: privacy must be object")
    else:
        assert_keys(errors, privacy, PRIVACY_REQUIRED, PRIVACY_REQUIRED, f"{where}.privacy")
        if privacy.get("anonymized") is not True or privacy.get("contains_sensitive_data") is not False:
            error(errors, f"{where}: synthetic records must be anonymized and contain no sensitive data")


def validate_annotation(record: Any, index: int, post_ids: set[str], errors: list[str]) -> None:
    where = f"reference_annotations[{index}]"
    if not isinstance(record, dict):
        error(errors, f"{where}: must be an object")
        return
    assert_keys(errors, record, ANNOTATION_REQUIRED, ANNOTATION_ALLOWED, where)
    if record.get("post_id") not in post_ids:
        error(errors, f"{where}: post_id does not refer to a content record")
    if record.get("guide_version") != "1.0":
        error(errors, f"{where}: guide_version must be 1.0")
    if record.get("label") not in VALID_LABELS:
        error(errors, f"{where}: invalid label")
    confidence = record.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        error(errors, f"{where}: confidence must be in [0, 1]")
    codes = record.get("evidence_codes")
    if not isinstance(codes, list) or any(code not in VALID_CODES for code in codes) or len(codes) != len(set(codes)):
        error(errors, f"{where}: evidence_codes must be unique known codes")
    if not isinstance(record.get("evidence"), list) or not all(isinstance(text, str) for text in record.get("evidence", [])):
        error(errors, f"{where}: evidence must be an array of strings")
    if record.get("label") == "uncertain" and not isinstance(record.get("uncertain_reason"), str):
        error(errors, f"{where}: uncertain label must have uncertain_reason")
    if record.get("label") != "uncertain" and record.get("uncertain_reason") is not None:
        error(errors, f"{where}: non-uncertain label must have null uncertain_reason")


def main() -> int:
    errors: list[str] = []
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to read submission assets: {exc}")
        return 1

    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        error(errors, "schema: unsupported or missing JSON Schema draft")
    if not {"content_record", "annotation_record"}.issubset(schema.get("$defs", {})):
        error(errors, "schema: content_record and annotation_record definitions are required")

    metadata = dataset.get("dataset_metadata")
    if not isinstance(metadata, dict):
        error(errors, "dataset_metadata must be an object")
    elif metadata.get("synthetic_only") is not True or metadata.get("contains_real_personal_data") is not False:
        error(errors, "dataset_metadata must declare synthetic_only=true and no real personal data")

    contents = dataset.get("content_records")
    annotations = dataset.get("reference_annotations")
    if not isinstance(contents, list) or not isinstance(annotations, list):
        error(errors, "content_records and reference_annotations must be arrays")
        contents, annotations = [], []

    for index, record in enumerate(contents):
        validate_content(record, index, errors)
    post_id_list = [record.get("post_id") for record in contents if isinstance(record, dict)]
    post_ids = set(post_id_list)
    if len(post_ids) != len(post_id_list):
        error(errors, "content_records: post_id values must be unique")

    for index, record in enumerate(annotations):
        validate_annotation(record, index, post_ids, errors)
    annotation_ids = [record.get("post_id") for record in annotations if isinstance(record, dict)]
    if set(annotation_ids) != post_ids or len(annotation_ids) != len(post_ids):
        error(errors, "every content record must have exactly one reference annotation")

    distribution = Counter(record.get("label") for record in annotations if isinstance(record, dict))
    if dict(distribution) != EXPECTED_DISTRIBUTION:
        error(errors, f"label distribution must be {EXPECTED_DISTRIBUTION}, got {dict(distribution)}")

    if errors:
        print("VALIDATION FAILED")
        for item in errors:
            print(f"- {item}")
        return 2

    print("VALIDATION PASSED")
    print(f"schema: {SCHEMA_PATH.relative_to(ROOT)}")
    print(f"dataset: {DATASET_PATH.relative_to(ROOT)}")
    print(f"content records: {len(contents)}")
    print("label distribution: " + ", ".join(f"{label}={distribution[label]}" for label in EXPECTED_DISTRIBUTION))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

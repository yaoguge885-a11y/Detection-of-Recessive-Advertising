#!/usr/bin/env python3
"""Validate P1 JSON assets, including annotation supplements, using only the standard library."""
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
MEDIA_REQUIRED = {"media_id", "type", "ref", "sha256", "phash", "ocr_text"}
COMMENT_REQUIRED = {"comment_id", "author_id", "text", "like_count", "is_pinned"}
SUPPLEMENT_REQUIRED = {"post_id", "annotator_id", "supplement_version", "image_analyses", "markdown_notes", "created_at", "updated_at"}
SUPPLEMENT_ALLOWED = SUPPLEMENT_REQUIRED | {"edge_case_discussion"}
IMAGE_ANALYSIS_REQUIRED = {"media_ref", "image_index", "analysis_method", "description", "detected_elements", "visual_evidence_codes", "relevance_to_annotation", "analyzed_at"}
IMAGE_ANALYSIS_ALLOWED = IMAGE_ANALYSIS_REQUIRED | {"source_url", "ocr_text", "image_quality_notes"}
DETECTED_ELEMENTS_REQUIRED = {"has_logo", "has_qr_code", "has_price_info", "has_product_image", "has_chart_or_table", "has_promotional_text", "has_contact_info"}
EDGE_CASE_ALLOWED = {"is_edge_case", "edge_case_category", "difficulty", "alternative_label", "reason_for_uncertainty", "suggested_guide_update", "needs_team_discussion", "discussion_tags"}
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



def validate_supplement(record: Any, index: int, post_media_refs: dict[str, set[str]], errors: list[str]) -> None:
    where = f"reference_annotation_supplements[{index}]"
    if not isinstance(record, dict):
        error(errors, f"{where}: must be an object")
        return
    assert_keys(errors, record, SUPPLEMENT_REQUIRED, SUPPLEMENT_ALLOWED, where)
    post_id = record.get("post_id")
    if post_id not in post_media_refs:
        error(errors, f"{where}: post_id does not refer to a content record")
    if record.get("annotator_id") != "synthetic_reference":
        error(errors, f"{where}: synthetic fixture must use annotator_id=synthetic_reference")
    if record.get("supplement_version") != "1.0":
        error(errors, f"{where}: supplement_version must be 1.0")
    if not isinstance(record.get("markdown_notes"), str):
        error(errors, f"{where}: markdown_notes must be a string")
    if not isinstance(record.get("created_at"), str) or not isinstance(record.get("updated_at"), str):
        error(errors, f"{where}: created_at and updated_at must be strings")
    analyses = record.get("image_analyses")
    if not isinstance(analyses, list):
        error(errors, f"{where}: image_analyses must be an array")
        return
    expected_refs = post_media_refs.get(post_id, set())
    observed_refs: list[str] = []
    for image_index, analysis in enumerate(analyses):
        image_where = f"{where}.image_analyses[{image_index}]"
        if not isinstance(analysis, dict):
            error(errors, f"{image_where}: must be an object")
            continue
        assert_keys(errors, analysis, IMAGE_ANALYSIS_REQUIRED, IMAGE_ANALYSIS_ALLOWED, image_where)
        media_ref = analysis.get("media_ref")
        observed_refs.append(media_ref)
        if media_ref not in expected_refs:
            error(errors, f"{image_where}: media_ref must match a media[].ref for the same post")
        if not isinstance(analysis.get("image_index"), int) or analysis.get("image_index", 0) < 1:
            error(errors, f"{image_where}: image_index must be a positive integer")
        if analysis.get("analysis_method") not in {"manual", "llm_vision", "ocr_auto", "hybrid"}:
            error(errors, f"{image_where}: invalid analysis_method")
        if not isinstance(analysis.get("description"), str) or not analysis["description"].strip():
            error(errors, f"{image_where}: description must be a nonempty string")
        if analysis.get("ocr_text") is not None and not isinstance(analysis.get("ocr_text"), str):
            error(errors, f"{image_where}: ocr_text must be a string or null")
        elements = analysis.get("detected_elements")
        if not isinstance(elements, dict):
            error(errors, f"{image_where}: detected_elements must be an object")
        else:
            assert_keys(errors, elements, DETECTED_ELEMENTS_REQUIRED, DETECTED_ELEMENTS_REQUIRED, f"{image_where}.detected_elements")
            if any(not isinstance(elements.get(field), bool) for field in DETECTED_ELEMENTS_REQUIRED):
                error(errors, f"{image_where}.detected_elements: all flags must be booleans")
        visual_codes = analysis.get("visual_evidence_codes")
        if not isinstance(visual_codes, list) or any(code not in {"V", "A", "D"} for code in visual_codes) or len(visual_codes) != len(set(visual_codes)):
            error(errors, f"{image_where}: visual_evidence_codes must be unique values from V/A/D")
        if not isinstance(analysis.get("relevance_to_annotation"), str) or not analysis["relevance_to_annotation"].strip():
            error(errors, f"{image_where}: relevance_to_annotation must be a nonempty string")
        if not isinstance(analysis.get("analyzed_at"), str):
            error(errors, f"{image_where}: analyzed_at must be a string")
    if set(observed_refs) != expected_refs or len(observed_refs) != len(expected_refs):
        error(errors, f"{where}: image analyses must cover every media[].ref exactly once")
    edge_case = record.get("edge_case_discussion")
    if edge_case is not None:
        if not isinstance(edge_case, dict):
            error(errors, f"{where}: edge_case_discussion must be an object or null")
        else:
            if "is_edge_case" not in edge_case:
                error(errors, f"{where}.edge_case_discussion: missing is_edge_case")
            unknown = set(edge_case) - EDGE_CASE_ALLOWED
            if unknown:
                error(errors, f"{where}.edge_case_discussion: unknown fields {sorted(unknown)}")
            if not isinstance(edge_case.get("is_edge_case"), bool):
                error(errors, f"{where}.edge_case_discussion: is_edge_case must be boolean")
            if edge_case.get("difficulty") not in {"easy", "medium", "hard"}:
                error(errors, f"{where}.edge_case_discussion: invalid difficulty")
            if edge_case.get("alternative_label") not in {"明广", "暗广", "非广", "out_of_scope"}:
                error(errors, f"{where}.edge_case_discussion: invalid alternative_label")


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
    if not {"content_record", "annotation_record", "annotation_supplement_record"}.issubset(schema.get("$defs", {})):
        error(errors, "schema: content_record, annotation_record, and annotation_supplement_record definitions are required")

    metadata = dataset.get("dataset_metadata")
    if not isinstance(metadata, dict):
        error(errors, "dataset_metadata must be an object")
    elif metadata.get("synthetic_only") is not True or metadata.get("contains_real_personal_data") is not False:
        error(errors, "dataset_metadata must declare synthetic_only=true and no real personal data")

    contents = dataset.get("content_records")
    annotations = dataset.get("reference_annotations")
    supplements = dataset.get("reference_annotation_supplements")
    if not isinstance(contents, list) or not isinstance(annotations, list) or not isinstance(supplements, list):
        error(errors, "content_records, reference_annotations, and reference_annotation_supplements must be arrays")
        contents, annotations, supplements = [], [], []

    for index, record in enumerate(contents):
        validate_content(record, index, errors)
    post_id_list = [record.get("post_id") for record in contents if isinstance(record, dict)]
    post_ids = set(post_id_list)
    post_media_refs = {
        record.get("post_id"): {item.get("ref") for item in record.get("media", []) if isinstance(item, dict)}
        for record in contents if isinstance(record, dict)
    }
    if len(post_ids) != len(post_id_list):
        error(errors, "content_records: post_id values must be unique")

    for index, record in enumerate(annotations):
        validate_annotation(record, index, post_ids, errors)
    annotation_ids = [record.get("post_id") for record in annotations if isinstance(record, dict)]
    if set(annotation_ids) != post_ids or len(annotation_ids) != len(post_ids):
        error(errors, "every content record must have exactly one reference annotation")

    for index, record in enumerate(supplements):
        validate_supplement(record, index, post_media_refs, errors)
    supplement_ids = [record.get("post_id") for record in supplements if isinstance(record, dict)]
    if set(supplement_ids) != post_ids or len(supplement_ids) != len(post_ids):
        error(errors, "every content record must have exactly one reference annotation supplement")

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
    print(f"annotation supplements: {len(supplements)}")
    print("label distribution: " + ", ".join(f"{label}={distribution[label]}" for label in EXPECTED_DISTRIBUTION))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

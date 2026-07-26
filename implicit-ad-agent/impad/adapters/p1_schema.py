"""Validate P1 content records against the authoritative schema and map them."""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from ..contracts.post import (
    CaptureModality,
    CaptureStatus,
    CommentRecord,
    MediaRecord,
    PostRecord,
    PrivacyRecord,
    ProvenanceRecord,
)


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "schema"
    / "data_schema_v1.json"
)


def _load_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


_VALIDATOR = _load_validator()


def _format_error(error) -> str:
    path = "$"
    if error.absolute_path:
        for part in error.absolute_path:
            if isinstance(part, int):
                path += f"[{part}]"
            else:
                path += f".{part}"
    return f"{path}: {error.message}"


def _validate_content_record(record: dict) -> None:
    errors = sorted(
        _VALIDATOR.iter_errors(record),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        raise ValueError(
            "P1 content_record validation failed: "
            + "; ".join(_format_error(error) for error in errors)
        )


def _capture_status(record: dict) -> CaptureStatus:
    text_status = "complete" if record["text"].strip() else "not_applicable"
    image_items = [
        item for item in record["media"] if item["type"] == "image"
    ]
    unsupported_media_types = sorted({
        item["type"]
        for item in record["media"]
        if item["type"] != "image"
    })
    image_refs = [item.get("ref") for item in image_items]
    if not image_items:
        image_status = "not_applicable"
        image_missing = []
    elif all(image_refs):
        image_status = "complete"
        image_missing = []
    elif any(image_refs):
        image_status = "partial"
        image_missing = ["media.ref"]
    else:
        image_status = "missing"
        image_missing = ["media.ref"]

    history_refs = record.get("blogger_history_refs", [])
    history_status = "partial" if history_refs else "not_applicable"
    disclosure_complete = (
        record["source_type"] == "synthetic"
        and text_status in {"complete", "not_applicable"}
        and image_status in {"complete", "not_applicable"}
        and not unsupported_media_types
    )
    return CaptureStatus(
        source="p1_schema_v1",
        captured_at=record["provenance"]["collected_at"],
        can_assess_disclosure=disclosure_complete,
        modalities={
            "text": CaptureModality(
                status=text_status,
                captured_fields=["text"],
            ),
            "image": CaptureModality(
                status=image_status,
                captured_fields=["media"] if image_items else [],
                missing_fields=image_missing,
            ),
            "comment": CaptureModality(
                status="complete" if "comments" in record else "missing",
                captured_fields=["comments"] if "comments" in record else [],
                missing_fields=[] if "comments" in record else ["comments"],
            ),
            "history": CaptureModality(
                status=history_status,
                captured_fields=["blogger_history_refs"]
                if history_refs
                else [],
                missing_fields=["resolved_history"] if history_refs else [],
            ),
            "metadata": CaptureModality(
                status="complete",
                captured_fields=["provenance", "privacy"],
                issues=[
                    f"unsupported_media_for_disclosure:{media_type}"
                    for media_type in unsupported_media_types
                ],
            ),
        },
    )


def post_record_from_content_record(record: dict) -> PostRecord:
    """Validate and convert one P1 content_record without dropping fields."""

    _validate_content_record(record)
    return PostRecord(
        schema_version=record["schema_version"],
        post_id=record["post_id"],
        platform=record["platform"],
        source_type=record["source_type"],
        creator_id=record["blogger_id"],
        published_at=record.get("published_at"),
        text=record["text"],
        media=[MediaRecord.model_validate(item) for item in record["media"]],
        comments=[
            CommentRecord.model_validate(item)
            for item in record.get("comments", [])
        ],
        history_refs=list(record.get("blogger_history_refs", [])),
        provenance=ProvenanceRecord.model_validate(record["provenance"]),
        privacy=PrivacyRecord.model_validate(record["privacy"]),
        capture_status=_capture_status(record),
    )

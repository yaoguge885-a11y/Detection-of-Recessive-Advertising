"""Normalize manual and legacy graph inputs into PostRecord."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from ..contracts.post import (
    CaptureModality,
    CaptureStatus,
    CommentRecord,
    HistoryPost,
    MediaRecord,
    PostRecord,
    PrivacyRecord,
    ProvenanceRecord,
)


def _digest(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _is_remote(ref: str) -> bool:
    return urlparse(ref).scheme.lower() in {"http", "https"}


def _comments(raw_comments) -> list[CommentRecord]:
    comments = []
    for index, item in enumerate(raw_comments or []):
        if isinstance(item, str):
            comments.append(CommentRecord(
                comment_id=f"comment_manual_{index}",
                text=item,
            ))
        else:
            normalized = dict(item)
            normalized.setdefault(
                "comment_id",
                f"comment_manual_{index}",
            )
            comments.append(CommentRecord.model_validate(normalized))
    return comments


def _history(raw_history, creator_id: str) -> list[HistoryPost]:
    history = []
    for index, item in enumerate(raw_history or []):
        if isinstance(item, str):
            history.append(HistoryPost(
                post_id=f"post_history_{index}_{_digest(item)}",
                creator_id=creator_id,
                text=item,
            ))
        else:
            normalized = dict(item)
            normalized["creator_id"] = normalized.pop(
                "blogger_id",
                normalized.get("creator_id", creator_id),
            )
            normalized.setdefault(
                "post_id",
                f"post_history_{index}_{_digest(normalized)}",
            )
            history.append(HistoryPost.model_validate(normalized))
    return history


def _media(record: dict) -> list[MediaRecord]:
    media = [
        MediaRecord.model_validate(item)
        for item in record.get("media", [])
    ]
    refs = {item.ref for item in media}
    for field in ("image_path", "image_url"):
        ref = record.get(field)
        if not ref or ref in refs:
            continue
        media.append(MediaRecord(
            media_id=f"media_manual_{len(media)}",
            type="image",
            ref=str(ref),
        ))
        refs.add(str(ref))
    return media


def _capture_status(
    record: dict,
    media: list[MediaRecord],
    comments: list[CommentRecord],
    history: list[HistoryPost],
) -> CaptureStatus:
    text_status = "complete" if str(record.get("text", "")).strip() else (
        "not_applicable"
    )
    image_refs = [
        item.ref for item in media if item.type == "image"
    ]
    local_image_refs = [
        ref
        for ref in image_refs
        if ref and not _is_remote(ref) and Path(ref).is_file()
    ]
    unsupported_media_types = sorted({
        item.type for item in media if item.type != "image"
    })
    if not image_refs:
        image_status = "not_applicable"
        image_missing = []
    elif len(local_image_refs) == len(image_refs):
        image_status = "complete"
        image_missing = []
    else:
        image_status = "partial"
        image_missing = ["local_media.ref"]

    capture_complete = bool(record.get("capture_complete", False))
    can_assess_disclosure = (
        capture_complete
        and text_status in {"complete", "not_applicable"}
        and image_status in {"complete", "not_applicable"}
        and not unsupported_media_types
    )
    return CaptureStatus(
        source="manual",
        can_assess_disclosure=can_assess_disclosure,
        modalities={
            "text": CaptureModality(
                status=text_status,
                captured_fields=["text"],
            ),
            "image": CaptureModality(
                status=image_status,
                captured_fields=["media"] if image_refs else [],
                missing_fields=image_missing,
            ),
            "comment": CaptureModality(
                status="complete" if comments else "not_applicable",
                captured_fields=["comments"] if comments else [],
            ),
            "history": CaptureModality(
                status="complete" if history else "not_applicable",
                captured_fields=["history"] if history else [],
            ),
            "metadata": CaptureModality(
                status="partial",
                captured_fields=["platform"],
                missing_fields=["verified_provenance"],
                issues=[
                    f"unsupported_media_for_disclosure:{media_type}"
                    for media_type in unsupported_media_types
                ],
            ),
        },
    )


def post_record_from_manual(record: dict) -> PostRecord:
    """Convert manual/legacy input without treating remote URLs as local media."""

    text = str(record.get("text", ""))
    creator_source = (
        record.get("creator_id")
        or record.get("blogger_id")
        or record.get("blogger")
        or "unknown"
    )
    creator_id = record.get("creator_id") or record.get("blogger_id")
    if not creator_id:
        creator_id = f"blogger_manual_{_digest(creator_source)}"
    post_id = record.get("post_id") or f"post_manual_{_digest(record)}"
    comments = _comments(record.get("comments"))
    history = _history(record.get("history"), creator_id)
    media = _media(record)
    capture_status = _capture_status(
        record,
        media,
        comments,
        history,
    )
    return PostRecord(
        schema_version=str(record.get("schema_version", "runtime-1")),
        post_id=post_id,
        platform=str(record.get("platform", "other")),
        source_type=str(record.get("source_type", "manual")),
        creator_id=creator_id,
        published_at=record.get("published_at"),
        text=text,
        media=media,
        comments=comments,
        history_refs=list(record.get("blogger_history_refs", [])),
        history=history,
        provenance=ProvenanceRecord(
            source_ref_hash=f"manual:{_digest(record)}",
            collector="manual_input",
        ),
        privacy=PrivacyRecord(),
        capture_status=capture_status,
    )

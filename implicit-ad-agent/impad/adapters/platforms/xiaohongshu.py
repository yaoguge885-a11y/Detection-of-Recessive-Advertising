"""Deterministic Xiaohongshu synthetic-fixture adapter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from ...contracts import (
    CaptureModality,
    CommentRecord,
    DisclosureRecord,
    MediaRecord,
    PostRecord,
)
from .embedded_json import extract_assigned_json
from .normalization import ParsedPlatformPost, build_platform_post


_XHS_TIMEZONE = timezone(timedelta(hours=8))
_DISCLOSURE_HASHTAGS = ("#广告", "#品牌合作", "#赞助")
_SUPPORTED_TYPES = frozenset({"normal", "video"})


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Xiaohongshu note requires non-empty {field}")
    return value


def _timestamp_from_millis(value: Any, field: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Xiaohongshu {field} must be milliseconds")
    if not isfinite(float(value)):
        raise ValueError(f"Xiaohongshu {field} must be milliseconds")
    try:
        return datetime.fromtimestamp(float(value) / 1000, _XHS_TIMEZONE)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"Xiaohongshu {field} must be milliseconds") from exc


def _captured_at(state: dict[str, Any]) -> datetime:
    value = state.get("fixtureCapturedAt")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Xiaohongshu fixtureCapturedAt is required")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Xiaohongshu fixtureCapturedAt is invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=_XHS_TIMEZONE)
    return timestamp


def _contains_exact_hashtag(text: str, marker: str) -> bool:
    start = 0
    while True:
        position = text.find(marker, start)
        if position < 0:
            return False
        end = position + len(marker)
        if end == len(text) or not (
            text[end].isalnum() or text[end] == "_"
        ):
            return True
        start = end


def _select_note(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("Xiaohongshu state must be an object")
    note_root = state.get("note")
    if not isinstance(note_root, dict):
        raise ValueError("Xiaohongshu state note is invalid")
    detail_map = note_root.get("noteDetailMap")
    if not isinstance(detail_map, dict) or len(detail_map) != 1:
        raise ValueError(
            "Xiaohongshu state must contain exactly one note"
        )
    entry = next(iter(detail_map.values()))
    if not isinstance(entry, dict) or not isinstance(entry.get("note"), dict):
        raise ValueError("Xiaohongshu note entry is invalid")
    return entry["note"]


def _image_media(note: dict[str, Any]) -> tuple[list[MediaRecord], list[str]]:
    raw_images = note.get("imageList", [])
    if raw_images is None:
        raw_images = []
    if not isinstance(raw_images, list):
        raise ValueError("Xiaohongshu imageList is invalid")
    media: list[MediaRecord] = []
    markers: list[str] = []
    for index, raw_image in enumerate(raw_images):
        if not isinstance(raw_image, dict):
            raise ValueError("Xiaohongshu imageList entry is invalid")
        reference = raw_image.get("urlDefault")
        if reference is not None and not isinstance(reference, str):
            raise ValueError("Xiaohongshu image URL is invalid")
        media.append(MediaRecord(
            media_id=f"xiaohongshu_image_{index}",
            type="image",
            ref=reference or None,
        ))
        markers.append(f"<图片{index + 1}>")
    return media, markers


def _video_media(note: dict[str, Any]) -> list[MediaRecord]:
    if note.get("type") != "video":
        return []
    return [MediaRecord(
        media_id="xiaohongshu_video_0",
        type="video",
        ref=None,
    )]


def _comments(note: dict[str, Any]) -> tuple[list[CommentRecord], str]:
    raw_comments = note.get("comments")
    interact_info = note.get("interactInfo")
    comment_count = None
    if isinstance(interact_info, dict):
        comment_count = interact_info.get("commentCount")

    if isinstance(raw_comments, list):
        comments: list[CommentRecord] = []
        for raw_comment in raw_comments:
            if not isinstance(raw_comment, dict):
                raise ValueError("Xiaohongshu comment entry is invalid")
            comment_id = _required_string(
                raw_comment.get("id"), "comment id"
            )
            author = raw_comment.get("user")
            author_id = (
                author.get("userId")
                if isinstance(author, dict)
                else None
            )
            if author_id is not None and not isinstance(author_id, str):
                raise ValueError("Xiaohongshu comment userId is invalid")
            content = raw_comment.get("content", "")
            if not isinstance(content, str):
                raise ValueError("Xiaohongshu comment content is invalid")
            like_count = raw_comment.get("likeCount", 0)
            if isinstance(like_count, bool) or not isinstance(like_count, int):
                raise ValueError("Xiaohongshu comment likeCount is invalid")
            is_pinned = raw_comment.get("isPinned", False)
            if not isinstance(is_pinned, bool):
                raise ValueError("Xiaohongshu comment isPinned is invalid")
            created_at = None
            if raw_comment.get("time") is not None:
                created_at = _timestamp_from_millis(
                    raw_comment["time"], "comment time"
                )
            comments.append(CommentRecord(
                comment_id=comment_id,
                author_id=author_id,
                text=content,
                like_count=like_count,
                is_pinned=is_pinned,
                created_at=created_at,
            ))
        return comments, "complete"

    if comment_count == 0:
        return [], "complete"
    return [], "missing"


def _disclosures(note: dict[str, Any], text: str) -> tuple[
    list[DisclosureRecord], str
]:
    if "disclosureLabels" not in note:
        return [], "missing"
    labels = note.get("disclosureLabels")
    if not isinstance(labels, list):
        raise ValueError("Xiaohongshu disclosureLabels is invalid")
    disclosures: list[DisclosureRecord] = []
    for label in labels:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Xiaohongshu disclosure label is invalid")
        disclosures.append(DisclosureRecord(
            kind="platform_badge",
            text=label,
            source="platform_metadata",
        ))
    for marker in _DISCLOSURE_HASHTAGS:
        if _contains_exact_hashtag(text, marker):
            disclosures.append(DisclosureRecord(
                kind="hashtag",
                text=marker,
                source="post_text",
            ))
    return disclosures, "complete"


def parse_xiaohongshu_state(
    state: dict[str, Any],
    source_ref_hash: str,
) -> PostRecord:
    """Parse one synthetic Xiaohongshu note into the shared PostRecord."""
    note = _select_note(state)
    post_id = _required_string(note.get("noteId"), "noteId")
    user = note.get("user")
    if not isinstance(user, dict):
        raise ValueError("Xiaohongshu note requires non-empty user.userId")
    creator_id = _required_string(user.get("userId"), "user.userId")
    content_type = note.get("type")
    if content_type not in _SUPPORTED_TYPES:
        raise ValueError("unsupported Xiaohongshu note type")

    title = note.get("title", "")
    description = note.get("desc", "")
    if not isinstance(title, str) or not isinstance(description, str):
        raise ValueError("Xiaohongshu title or desc is invalid")
    media, image_markers = _image_media(note)
    media.extend(_video_media(note))
    text_parts = [
        value.strip()
        for value in (title, description)
        if value.strip()
    ]
    text_parts.extend(image_markers)
    text = "\n".join(text_parts)

    comments, comment_status = _comments(note)
    disclosures, disclosure_status = _disclosures(note, text)
    if content_type == "video":
        image_status = "unsupported"
    elif media:
        image_status = "partial"
    else:
        image_status = "missing"

    payload = ParsedPlatformPost(
        platform="xiaohongshu",
        content_type=content_type,
        post_id=post_id,
        creator_id=creator_id,
        published_at=(
            _timestamp_from_millis(note["time"], "time")
            if note.get("time") is not None
            else None
        ),
        text=text,
        media=media,
        comments=comments,
        disclosures=disclosures,
        modalities={
            "text": CaptureModality(
                status="complete" if text else "missing"
            ),
            "image": CaptureModality(status=image_status),
            "comment": CaptureModality(status=comment_status),
            "disclosure": CaptureModality(status=disclosure_status),
        },
        captured_at=_captured_at(state),
    )
    return build_platform_post(
        payload,
        source_ref_hash=source_ref_hash,
        adapter_version=XiaohongshuAdapter.version,
    )


class XiaohongshuAdapter:
    """Injectable parser for structural Xiaohongshu fixture pages."""

    name = "xiaohongshu_fixture"
    version = "xiaohongshu-fixture-v1"
    platform = "xiaohongshu"
    supported_hosts = ("xiaohongshu.com",)

    def preview(self, source, *, fetcher):
        result = fetcher.fetch(source.fetch_url)
        html = result.body.decode("utf-8")
        state = extract_assigned_json(html, "window.__INITIAL_STATE__")
        return parse_xiaohongshu_state(
            state,
            source_ref_hash=result.source_ref_hash,
        )

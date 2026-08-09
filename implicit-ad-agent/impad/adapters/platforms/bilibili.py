"""Deterministic Bilibili synthetic-fixture adapter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

from ...contracts import (
    CaptureModality,
    DisclosureRecord,
    MediaRecord,
    PostRecord,
)
from .embedded_json import extract_assigned_json
from .normalization import ParsedPlatformPost, build_platform_post


_BILIBILI_TIMEZONE = timezone(timedelta(hours=8))
_SUPPORTED_TYPES = frozenset({"video", "opus", "article"})


def _required_string(value: Any, field: str, content_type: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Bilibili {content_type} requires non-empty {field}"
        )
    return value


def _optional_text(value: Any, field: str, content_type: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Bilibili {content_type} {field} is invalid")
    return value


def _captured_at(state: dict[str, Any]) -> datetime:
    if not isinstance(state, dict):
        raise ValueError("Bilibili state must be an object")
    value = state.get("fixtureCapturedAt")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Bilibili fixtureCapturedAt is required")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Bilibili fixtureCapturedAt is invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=_BILIBILI_TIMEZONE)
    return timestamp


def _timestamp_seconds(
    value: Any,
    field: str,
    content_type: str,
) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Bilibili {content_type} {field} must be seconds")
    if not isfinite(float(value)):
        raise ValueError(f"Bilibili {content_type} {field} must be seconds")
    try:
        return datetime.fromtimestamp(float(value), _BILIBILI_TIMEZONE)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(
            f"Bilibili {content_type} {field} must be seconds"
        ) from exc


def _timestamp_iso(value: Any, field: str, content_type: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Bilibili {content_type} {field} is invalid")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Bilibili {content_type} {field} is invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=_BILIBILI_TIMEZONE)
    return timestamp


def _section(state: dict[str, Any], key: str) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("Bilibili state must be an object")
    value = state.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Bilibili state {key} is invalid")
    return value


def _image_media(
    section: dict[str, Any],
    key: str,
    content_type: str,
) -> tuple[list[MediaRecord], list[str]]:
    raw_images = section.get(key, [])
    if raw_images is None:
        raw_images = []
    if not isinstance(raw_images, list):
        raise ValueError(f"Bilibili {content_type} {key} is invalid")

    media: list[MediaRecord] = []
    markers: list[str] = []
    for index, raw_image in enumerate(raw_images):
        if not isinstance(raw_image, dict):
            raise ValueError(
                f"Bilibili {content_type} {key} entry is invalid"
            )
        reference = raw_image.get("url")
        if reference is not None and not isinstance(reference, str):
            raise ValueError(
                f"Bilibili {content_type} image URL is invalid"
            )
        media.append(MediaRecord(
            media_id=f"bilibili_{content_type}_image_{index}",
            type="image",
            ref=reference or None,
        ))
        markers.append(f"<图片{index + 1}>")
    return media, markers


def _disclosures(
    section: dict[str, Any],
    content_type: str,
    *,
    surface_captured: bool = True,
) -> tuple[list[DisclosureRecord], str]:
    if not surface_captured:
        return [], "missing"
    if "disclosureLabels" not in section:
        return [], "missing"
    labels = section.get("disclosureLabels")
    if not isinstance(labels, list):
        raise ValueError(
            f"Bilibili {content_type} disclosureLabels is invalid"
        )
    disclosures: list[DisclosureRecord] = []
    for label in labels:
        if not isinstance(label, str) or not label.strip():
            raise ValueError(
                f"Bilibili {content_type} disclosure label is invalid"
            )
        disclosures.append(DisclosureRecord(
            kind="platform_badge",
            text=label,
            source="platform_metadata",
        ))
    return disclosures, "complete"


def _build(
    *,
    content_type: str,
    section: dict[str, Any],
    post_id: str,
    creator_id: str,
    published_at: datetime | None,
    title: Any,
    body: Any,
    image_key: str | None,
    captured_at: datetime,
    source_ref_hash: str,
    surface_captured: bool = True,
) -> PostRecord:
    title_text = _optional_text(title, "title", content_type)
    body_text = _optional_text(body, "body", content_type)
    media: list[MediaRecord] = []
    image_markers: list[str] = []
    if image_key is not None:
        media, image_markers = _image_media(section, image_key, content_type)

    text_parts = [
        value.strip()
        for value in (title_text, body_text)
        if value.strip()
    ]
    text_parts.extend(image_markers)
    text = "\n".join(text_parts)

    disclosures, disclosure_status = _disclosures(
        section,
        content_type,
        surface_captured=surface_captured,
    )
    if content_type == "video":
        image_status = "unsupported"
    elif media:
        image_status = "partial"
    else:
        image_status = "missing"

    payload = ParsedPlatformPost(
        platform="bilibili",
        content_type=content_type,
        post_id=post_id,
        creator_id=creator_id,
        published_at=published_at,
        text=text,
        media=media,
        comments=[],
        disclosures=disclosures,
        modalities={
            "text": CaptureModality(
                status="complete" if text else "missing"
            ),
            "image": CaptureModality(status=image_status),
            "comment": CaptureModality(status="unsupported"),
            "disclosure": CaptureModality(status=disclosure_status),
        },
        captured_at=captured_at,
    )
    return build_platform_post(
        payload,
        source_ref_hash=source_ref_hash,
        adapter_version=BilibiliAdapter.version,
    )


def parse_bilibili_state(
    state: dict[str, Any],
    content_type: str,
    source_ref_hash: str,
) -> PostRecord:
    """Parse one synthetic Bilibili payload into the shared PostRecord."""
    if content_type not in _SUPPORTED_TYPES:
        raise ValueError("unsupported Bilibili content type")
    if not isinstance(state, dict):
        raise ValueError("Bilibili state must be an object")
    captured_at = _captured_at(state)

    if content_type == "video":
        section = _section(state, "videoData")
        post_id = _required_string(section.get("bvid"), "bvid", content_type)
        owner = section.get("owner")
        if not isinstance(owner, dict):
            raise ValueError(
                "Bilibili video requires non-empty creator_id"
            )
        creator_id = _required_string(
            owner.get("mid"), "creator_id", content_type
        )
        published_at = (
            _timestamp_seconds(section["pubdate"], "pubdate", content_type)
            if section.get("pubdate") is not None
            else None
        )
        return _build(
            content_type=content_type,
            section=section,
            post_id=post_id,
            creator_id=creator_id,
            published_at=published_at,
            title=section.get("title"),
            body=section.get("desc"),
            image_key=None,
            captured_at=captured_at,
            source_ref_hash=source_ref_hash,
        )

    if content_type == "opus":
        section = _section(state, "opusModule")
        post_id = _required_string(
            section.get("dynamic_id"), "dynamic_id", content_type
        )
        author = section.get("author")
        if not isinstance(author, dict):
            raise ValueError(
                "Bilibili opus requires non-empty creator_id"
            )
        creator_id = _required_string(
            author.get("mid"), "creator_id", content_type
        )
        published_at = (
            _timestamp_iso(
                section["published_at"], "published_at", content_type
            )
            if section.get("published_at") is not None
            else None
        )
        return _build(
            content_type=content_type,
            section=section,
            post_id=post_id,
            creator_id=creator_id,
            published_at=published_at,
            title=section.get("title"),
            body=section.get("description"),
            image_key="pictures",
            captured_at=captured_at,
            source_ref_hash=source_ref_hash,
        )

    section = _section(state, "readInfo")
    post_id = _required_string(section.get("id"), "cv_id", content_type)
    author = section.get("author")
    if not isinstance(author, dict):
        raise ValueError(
            "Bilibili article requires non-empty creator_id"
        )
    creator_id = _required_string(
        author.get("mid"), "creator_id", content_type
    )
    published_at = (
        _timestamp_seconds(
            section["publish_time"], "publish_time", content_type
        )
        if section.get("publish_time") is not None
        else None
    )
    surface = section.get("disclosureSurfaceCaptured", False)
    if not isinstance(surface, bool):
        raise ValueError(
            "Bilibili article disclosureSurfaceCaptured is invalid"
        )
    return _build(
        content_type=content_type,
        section=section,
        post_id=post_id,
        creator_id=creator_id,
        published_at=published_at,
        title=section.get("title"),
        body=section.get("body"),
        image_key="images",
        captured_at=captured_at,
        source_ref_hash=source_ref_hash,
        surface_captured=surface,
    )


def content_type_from_url(url: str) -> str:
    """Resolve supported Bilibili URL forms without following redirects."""
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValueError("unsupported Bilibili content type") from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path or "/"
    if hostname == "t.bilibili.com":
        return "opus"
    if hostname != "bilibili.com" and not hostname.endswith(".bilibili.com"):
        raise ValueError("unsupported Bilibili content type")
    if path.startswith("/video/"):
        return "video"
    if path.startswith("/opus/"):
        return "opus"
    if path.startswith("/read/cv"):
        return "article"
    raise ValueError("unsupported Bilibili content type")


class BilibiliAdapter:
    """Injectable parser for structural Bilibili fixture pages."""

    name = "bilibili_fixture"
    version = "bilibili-fixture-v1"
    platform = "bilibili"
    supported_hosts = ("bilibili.com",)

    def preview(self, source, *, fetcher):
        result = fetcher.fetch(source.fetch_url)
        html = result.body.decode("utf-8")
        state = extract_assigned_json(html, "window.__INITIAL_STATE__")
        content_type = content_type_from_url(source.display_url)
        return parse_bilibili_state(
            state,
            content_type=content_type,
            source_ref_hash=result.source_ref_hash,
        )

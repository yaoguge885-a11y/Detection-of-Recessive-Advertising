"""Normalized runtime post and capture contracts."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


CaptureState = Literal[
    "complete",
    "partial",
    "missing",
    "unsupported",
    "not_applicable",
]
CaptureModalityName = Literal[
    "text",
    "image",
    "comment",
    "disclosure",
    "history",
    "metadata",
]
DisclosureKind = Literal[
    "platform_badge",
    "hashtag",
    "text_statement",
]
DisclosureSource = Literal["platform_metadata", "post_text"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaptureModality(_StrictModel):
    """Capture completeness for one input modality."""

    status: CaptureState
    captured_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class CaptureStatus(_StrictModel):
    """Auditable capture state; it never implies an advertising label."""

    source: str = Field(min_length=1)
    modalities: dict[CaptureModalityName, CaptureModality]
    can_assess_disclosure: bool = False
    adapter_version: str = Field(default="1.0", min_length=1)
    captured_at: datetime | None = None
    user_corrections: list[str] = Field(default_factory=list)


class MediaRecord(_StrictModel):
    media_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    ref: str | None = None
    sha256: str | None = None
    phash: str | None = None
    ocr_text: str | None = None


class CommentRecord(_StrictModel):
    comment_id: str = Field(min_length=1)
    author_id: str | None = None
    text: str
    like_count: int = Field(default=0, ge=0)
    is_pinned: bool = False
    created_at: datetime | None = None


class DisclosureRecord(_StrictModel):
    """One structured disclosure marker captured from the platform."""

    kind: DisclosureKind
    text: str = Field(min_length=1)
    source: DisclosureSource


class HistoryPost(_StrictModel):
    post_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    text: str
    published_at: datetime | None = None

    @field_validator("published_at")
    @classmethod
    def published_at_is_timezone_aware(cls, value):
        if (
            value is not None
            and (value.tzinfo is None or value.utcoffset() is None)
        ):
            raise ValueError("published_at must be timezone-aware")
        return value


class ProvenanceRecord(_StrictModel):
    source_ref_hash: str | None = None
    collected_at: datetime | None = None
    collector: str | None = None
    terms_checked_at: date | None = None


class PrivacyRecord(_StrictModel):
    anonymized: bool | None = None
    contains_sensitive_data: bool | None = None


class PostRecord(_StrictModel):
    """The single normalized input consumed by runtime orchestration."""

    schema_version: str = Field(min_length=1)
    post_id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    published_at: datetime | None = None
    text: str
    media: list[MediaRecord] = Field(default_factory=list)
    comments: list[CommentRecord] = Field(default_factory=list)
    disclosures: list[DisclosureRecord] = Field(default_factory=list)
    history_refs: list[str] = Field(default_factory=list)
    history: list[HistoryPost] = Field(default_factory=list)
    provenance: ProvenanceRecord = Field(default_factory=ProvenanceRecord)
    privacy: PrivacyRecord = Field(default_factory=PrivacyRecord)
    capture_status: CaptureStatus

    @field_validator("published_at")
    @classmethod
    def published_at_is_timezone_aware(cls, value):
        if (
            value is not None
            and (value.tzinfo is None or value.utcoffset() is None)
        ):
            raise ValueError("published_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def resolved_history_is_leakage_safe(self):
        history_ids = [item.post_id for item in self.history]
        if len(history_ids) != len(set(history_ids)):
            raise ValueError("history post_id values must be unique")
        for item in self.history:
            if item.post_id == self.post_id:
                raise ValueError(
                    "resolved history cannot contain the target post_id"
                )
            if item.creator_id != self.creator_id:
                raise ValueError(
                    "resolved history must belong to the same creator"
                )
            if self.published_at is None or item.published_at is None:
                continue
            try:
                is_earlier = item.published_at < self.published_at
            except TypeError as exc:
                raise ValueError(
                    "history and target timestamps must use compatible timezones"
                ) from exc
            if not is_earlier:
                raise ValueError(
                    "resolved history must be strictly earlier than target"
                )
        self.history.sort(key=lambda item: (
            item.published_at is None,
            item.published_at.timestamp() if item.published_at else 0.0,
        ))
        return self

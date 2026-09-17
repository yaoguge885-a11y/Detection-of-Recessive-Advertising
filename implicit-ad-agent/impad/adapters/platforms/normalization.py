"""Shared normalization for platform fixture payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...contracts import (
    CaptureModality,
    CaptureStatus,
    CommentRecord,
    DisclosureRecord,
    MediaRecord,
    PostRecord,
    PrivacyRecord,
    ProvenanceRecord,
)


TargetModality = Literal["text", "image", "comment", "disclosure"]


class ParsedPlatformPost(BaseModel):
    """Strict intermediate payload shared by platform-specific adapters."""

    model_config = ConfigDict(extra="forbid")

    platform: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    post_id: str = Field(min_length=1)
    creator_id: str = Field(min_length=1)
    published_at: datetime | None = None
    text: str
    media: list[MediaRecord] = Field(default_factory=list)
    comments: list[CommentRecord] = Field(default_factory=list)
    disclosures: list[DisclosureRecord] = Field(default_factory=list)
    modalities: dict[TargetModality, CaptureModality]
    captured_at: datetime

    @model_validator(mode="after")
    def require_target_modalities(self):
        required = {"text", "image", "comment", "disclosure"}
        missing = sorted(required - set(self.modalities))
        if missing:
            raise ValueError("missing target modalities: " + ", ".join(missing))
        return self


def build_platform_post(
    payload: ParsedPlatformPost,
    *,
    source_ref_hash: str,
    adapter_version: str,
) -> PostRecord:
    """Build the runtime ``PostRecord`` from a validated fixture payload."""
    disclosure_complete = (
        payload.modalities["disclosure"].status == "complete"
        and payload.modalities["text"].status == "complete"
        and payload.modalities["image"].status in {"complete", "unsupported"}
        and all(item.type == "image" for item in payload.media)
    )
    return PostRecord(
        schema_version="1.0",
        post_id=payload.post_id,
        platform=payload.platform,
        source_type="platform_fixture",
        creator_id=payload.creator_id,
        published_at=payload.published_at,
        text=payload.text,
        media=payload.media,
        comments=payload.comments,
        disclosures=payload.disclosures,
        provenance=ProvenanceRecord(
            source_ref_hash=source_ref_hash,
            collected_at=payload.captured_at,
            collector="synthetic_fixture",
        ),
        privacy=PrivacyRecord(
            anonymized=True,
            contains_sensitive_data=False,
        ),
        capture_status=CaptureStatus(
            source=f"fixture:{payload.platform}",
            modalities=payload.modalities,
            can_assess_disclosure=disclosure_complete,
            adapter_version=adapter_version,
            captured_at=payload.captured_at,
        ),
    )

"""Contracts shared by safe platform URL adapters."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

from ...contracts import (
    CaptureStatus,
    CommentRecord,
    DisclosureRecord,
    HistoryPost,
    MediaRecord,
    PostRecord,
)

if TYPE_CHECKING:
    from .safe_fetch import SafeURLFetcher


@dataclass(frozen=True)
class ValidatedSourceURL:
    """Internal URL form with a secret-free display representation."""

    fetch_url: str
    display_url: str
    hostname: str
    source_ref_hash: str
    sensitive_tokens: tuple[str, ...] = ()


class URLImportError(Exception):
    """Stable safe error for URL import and confirmation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PlatformAdapter(Protocol):
    """One explicitly registered platform-to-PostRecord adapter."""

    name: str
    version: str
    platform: str
    supported_hosts: tuple[str, ...]

    def preview(
        self,
        source: ValidatedSourceURL,
        *,
        fetcher: "SafeURLFetcher",
    ) -> PostRecord:
        """Return a normalized post without running classification."""


class URLImportPreview(BaseModel):
    """Normalized capture awaiting explicit user confirmation."""

    model_config = ConfigDict(extra="forbid")

    preview_id: str = Field(pattern=r"^preview_[0-9a-f]{32}$")
    platform: str = Field(min_length=1)
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    display_url: str = Field(min_length=1)
    source_ref_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime
    post: PostRecord


class URLImportCorrections(BaseModel):
    """Allowlisted user corrections applied before analysis."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    creator_id: str | None = None
    published_at: datetime | None = None
    media: list[MediaRecord] | None = None
    comments: list[CommentRecord] | None = None
    disclosures: list[DisclosureRecord] | None = None
    history: list[HistoryPost] | None = None
    capture_status: CaptureStatus | None = None

"""Contracts shared by safe platform URL adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...contracts import PostRecord


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

    def preview(self, source: ValidatedSourceURL) -> PostRecord:
        """Return a normalized post without running classification."""

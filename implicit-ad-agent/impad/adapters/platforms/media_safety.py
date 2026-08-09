"""Safety policy for media references returned by platform adapters."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from ...contracts import MediaRecord
from .contracts import URLImportError


MAX_MEDIA_REF_LENGTH = 2048
ALLOWED_MEDIA_TYPES = frozenset({"image", "video"})


def _resolve_path(path: Path) -> Path:
    return path.resolve(strict=False)


def _unsafe_media_reference(cause: Exception | None = None):
    error = URLImportError(
        "unsafe_media_reference",
        "Platform media reference is unsafe.",
    )
    if cause is None:
        raise error
    raise error from cause


class PlatformMediaPolicy:
    def __init__(self, *, fetcher, cache_root: Path | None):
        self.fetcher = fetcher
        self.cache_root = (
            _resolve_path(Path(cache_root))
            if cache_root is not None
            else None
        )

    def normalize(self, media: list[MediaRecord]) -> list[MediaRecord]:
        return [self._normalize_item(item) for item in media]

    def _normalize_item(self, item: MediaRecord) -> MediaRecord:
        if item.type not in ALLOWED_MEDIA_TYPES:
            _unsafe_media_reference()
        if item.ref is None:
            return item
        ref = item.ref
        if (
            not ref
            or len(ref) > MAX_MEDIA_REF_LENGTH
            or any(ord(char) < 32 or ord(char) == 127 for char in ref)
        ):
            _unsafe_media_reference()

        try:
            parsed = urlsplit(ref)
        except ValueError as exc:
            _unsafe_media_reference(exc)
        scheme = parsed.scheme.lower()
        if scheme:
            if scheme != "https":
                _unsafe_media_reference()
            try:
                target = self.fetcher.validate_target(ref)
            except Exception as exc:
                _unsafe_media_reference(exc)
            return item.model_copy(update={
                "ref": target.source.display_url,
            })

        normalized = ref.replace("\\", "/")
        if (
            normalized.startswith("/")
            or ref.startswith(("\\\\", "//"))
            or ":" in normalized
            or ".." in Path(normalized).parts
            or self.cache_root is None
        ):
            _unsafe_media_reference()
        try:
            candidate = (
                self.cache_root / normalized
            )
            candidate = _resolve_path(candidate)
            if not candidate.is_relative_to(self.cache_root):
                _unsafe_media_reference()
            safe_ref = candidate.relative_to(self.cache_root).as_posix()
        except (OSError, ValueError) as exc:
            _unsafe_media_reference(exc)
        return item.model_copy(update={"ref": safe_ref})

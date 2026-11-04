"""Process-local URL preview and explicit confirmation workflow."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import ValidationError

from ...contracts import PostRecord
from ...services import AnalysisResult, AnalysisService, RuntimeMode
from .contracts import (
    URLImportCorrections,
    URLImportError,
    URLImportPreview,
)
from .registry import PlatformAdapterRegistry
from .media_safety import PlatformMediaPolicy
from .safe_fetch import DisabledURLFetcher, SafeURLFetcher
from .url_safety import validate_public_https_url


def _string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _string_values(item)


def _contains_sensitive_source_data(
    payload: dict,
    sensitive_tokens: tuple[str, ...],
) -> bool:
    for value in _string_values(payload):
        for token in sensitive_tokens:
            if value == token or (len(token) >= 4 and token in value):
                return True
    return False


class InMemoryURLPreviewStore:
    """Bounded one-process preview store; not a durable queue."""

    def __init__(self, *, max_entries: int = 100):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._records: OrderedDict[str, URLImportPreview] = OrderedDict()
        self._claimed: set[str] = set()
        self._lock = Lock()

    def put(self, preview: URLImportPreview) -> None:
        with self._lock:
            self._records[preview.preview_id] = preview.model_copy(deep=True)
            self._records.move_to_end(preview.preview_id)
            while len(self._records) > self.max_entries:
                evictable = next((
                    preview_id
                    for preview_id in self._records
                    if (
                        preview_id not in self._claimed
                        and preview_id != preview.preview_id
                    )
                ), None)
                if evictable is None:
                    break
                self._records.pop(evictable)

    def get(self, preview_id: str) -> URLImportPreview | None:
        with self._lock:
            preview = self._records.get(preview_id)
            return (
                preview.model_copy(deep=True)
                if preview is not None
                else None
            )

    def claim(self, preview_id: str) -> URLImportPreview | None:
        with self._lock:
            preview = self._records.get(preview_id)
            if preview is None or preview_id in self._claimed:
                return None
            self._claimed.add(preview_id)
            return preview.model_copy(deep=True)

    def release(self, preview_id: str) -> None:
        with self._lock:
            self._claimed.discard(preview_id)

    def consume(self, preview_id: str) -> None:
        with self._lock:
            self._records.pop(preview_id, None)
            self._claimed.discard(preview_id)

    def delete(self, preview_id: str) -> None:
        self.consume(preview_id)


class URLImportService:
    """Validate, preview, correct, and then analyze a platform URL."""

    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        registry: PlatformAdapterRegistry | None = None,
        preview_store: InMemoryURLPreviewStore | None = None,
        fetcher: SafeURLFetcher | None = None,
        media_cache_root: Path | None = None,
    ):
        self.analysis_service = analysis_service
        self.registry = registry or PlatformAdapterRegistry()
        self.preview_store = (
            preview_store or InMemoryURLPreviewStore()
        )
        self.fetcher = fetcher or DisabledURLFetcher()
        self.media_policy = PlatformMediaPolicy(
            fetcher=self.fetcher,
            cache_root=media_cache_root,
        )

    def preview(self, url: str) -> URLImportPreview:
        source = validate_public_https_url(url)
        adapter = self.registry.resolve(source)
        try:
            post = PostRecord.model_validate(adapter.preview(
                source,
                fetcher=self.fetcher,
            ))
        except Exception as exc:
            raise URLImportError(
                "adapter_failed",
                "Platform adapter could not normalize this URL.",
            ) from exc
        post = post.model_copy(update={
            "media": self.media_policy.normalize(post.media),
        })
        if post.platform != adapter.platform:
            raise URLImportError(
                "adapter_failed",
                "Platform adapter returned an unexpected platform.",
            )
        if _contains_sensitive_source_data(
            post.model_dump(mode="python"),
            source.sensitive_tokens,
        ):
            raise URLImportError(
                "adapter_failed",
                "Platform adapter returned unsafe source data.",
            )

        payload = post.model_dump(mode="python")
        provenance = dict(payload["provenance"])
        provenance["source_ref_hash"] = source.source_ref_hash
        capture_status = dict(payload["capture_status"])
        capture_status["source"] = f"url:{adapter.platform}"
        capture_status["adapter_version"] = adapter.version
        payload["provenance"] = provenance
        payload["capture_status"] = capture_status
        normalized = PostRecord.model_validate(payload)
        preview = URLImportPreview(
            preview_id=f"preview_{uuid4().hex}",
            platform=adapter.platform,
            adapter_name=adapter.name,
            adapter_version=adapter.version,
            display_url=source.display_url,
            source_ref_hash=source.source_ref_hash,
            created_at=datetime.now(timezone.utc),
            post=normalized,
        )
        self.preview_store.put(preview)
        return preview

    def confirm(
        self,
        preview_id: str,
        corrections: URLImportCorrections,
        *,
        runtime_mode: RuntimeMode = "local",
    ) -> AnalysisResult:
        preview = self.preview_store.claim(preview_id)
        if preview is None:
            raise URLImportError(
                "preview_not_found",
                "URL preview was not found.",
                status_code=404,
            )

        try:
            payload = preview.post.model_dump(mode="python")
            for field, value in corrections.model_dump(
                mode="python",
                exclude_unset=True,
            ).items():
                payload[field] = value
            original_capture = (
                preview.post.capture_status.model_dump(mode="python")
            )
            capture_status = dict(payload["capture_status"])
            capture_status["source"] = original_capture["source"]
            capture_status["adapter_version"] = (
                original_capture["adapter_version"]
            )
            capture_status["user_corrections"] = original_capture.get(
                "user_corrections",
                [],
            )
            payload["capture_status"] = capture_status
            candidate = PostRecord.model_validate(payload)
            changed_fields = sorted(
                field
                for field in corrections.model_fields_set
                if (
                    getattr(candidate, field)
                    != getattr(preview.post, field)
                )
            )
            corrected_payload = candidate.model_dump(mode="python")
            corrected_capture = dict(corrected_payload["capture_status"])
            corrected_capture["user_corrections"] = list(dict.fromkeys([
                *original_capture.get("user_corrections", []),
                *changed_fields,
            ]))
            corrected_payload["capture_status"] = corrected_capture
            corrected = PostRecord.model_validate(corrected_payload)
        except (TypeError, ValueError, ValidationError) as exc:
            self.preview_store.release(preview_id)
            raise URLImportError(
                "invalid_corrections",
                "URL preview corrections are invalid.",
            ) from exc

        try:
            result = self.analysis_service.analyze(
                corrected,
                runtime_mode=runtime_mode,
            )
        except Exception:
            self.preview_store.release(preview_id)
            raise

        self.preview_store.consume(preview_id)
        return result

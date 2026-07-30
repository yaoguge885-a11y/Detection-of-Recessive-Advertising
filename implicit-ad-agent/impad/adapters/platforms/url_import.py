"""Process-local URL preview and explicit confirmation workflow."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
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
from .url_safety import validate_public_https_url


class InMemoryURLPreviewStore:
    """Bounded one-process preview store; not a durable queue."""

    def __init__(self, *, max_entries: int = 100):
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._records: OrderedDict[str, URLImportPreview] = OrderedDict()

    def put(self, preview: URLImportPreview) -> None:
        self._records[preview.preview_id] = preview
        self._records.move_to_end(preview.preview_id)
        while len(self._records) > self.max_entries:
            self._records.popitem(last=False)

    def get(self, preview_id: str) -> URLImportPreview | None:
        return self._records.get(preview_id)

    def delete(self, preview_id: str) -> None:
        self._records.pop(preview_id, None)


class URLImportService:
    """Validate, preview, correct, and then analyze a platform URL."""

    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        registry: PlatformAdapterRegistry | None = None,
        preview_store: InMemoryURLPreviewStore | None = None,
    ):
        self.analysis_service = analysis_service
        self.registry = registry or PlatformAdapterRegistry()
        self.preview_store = (
            preview_store or InMemoryURLPreviewStore()
        )

    def preview(self, url: str) -> URLImportPreview:
        source = validate_public_https_url(url)
        adapter = self.registry.resolve(source)
        try:
            post = PostRecord.model_validate(adapter.preview(source))
        except Exception as exc:
            raise URLImportError(
                "adapter_failed",
                "Platform adapter could not normalize this URL.",
            ) from exc
        if post.platform != adapter.platform:
            raise URLImportError(
                "adapter_failed",
                "Platform adapter returned an unexpected platform.",
            )
        serialized = post.model_dump_json()
        if any(
            token in serialized
            for token in source.sensitive_tokens
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
        preview = self.preview_store.get(preview_id)
        if preview is None:
            raise URLImportError(
                "preview_not_found",
                "URL preview was not found.",
                status_code=404,
            )

        payload = preview.post.model_dump(mode="python")
        changed_fields = sorted(corrections.model_fields_set)
        for field, value in corrections.model_dump(
            mode="python",
            exclude_unset=True,
        ).items():
            payload[field] = value
        try:
            capture_status = dict(payload["capture_status"])
            capture_status["user_corrections"] = list(dict.fromkeys([
                *capture_status.get("user_corrections", []),
                *changed_fields,
            ]))
            payload["capture_status"] = capture_status
            corrected = PostRecord.model_validate(payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise URLImportError(
                "invalid_corrections",
                "URL preview corrections are invalid.",
            ) from exc

        result = self.analysis_service.analyze(
            corrected,
            runtime_mode=runtime_mode,
        )
        self.preview_store.delete(preview_id)
        return result

from __future__ import annotations

from pathlib import Path

import pytest

from impad.adapters import post_record_from_manual
from impad.adapters.platforms import (
    PlatformAdapterRegistry,
    URLImportCorrections,
    URLImportError,
    URLImportService,
)
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


class StaticAdapter:
    name = "static"
    version = "static-v1"
    platform = "fixture"
    supported_hosts = ("example.test",)

    def __init__(self):
        self.calls = 0
        self.last_source = None

    def preview(self, source):
        self.calls += 1
        self.last_source = source
        return post_record_from_manual({
            "post_id": "fixture-post",
            "platform": self.platform,
            "source_type": "url_import",
            "creator_id": "creator-1",
            "published_at": "2026-07-30T00:00:00Z",
            "text": "适配器提取正文",
            "history": [{
                "post_id": "history-1",
                "creator_id": "creator-1",
                "published_at": "2026-07-29T00:00:00Z",
                "text": "历史正文",
            }],
        })


class QueryValueLeakingAdapter(StaticAdapter):
    def preview(self, source):
        post = super().preview(source)
        return post.model_copy(update={"text": "do-not-store"})


def _analysis_service(tmp_path: Path) -> AnalysisService:
    return AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )


def _url_service(tmp_path: Path):
    analysis = _analysis_service(tmp_path)
    adapter = StaticAdapter()
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([adapter]),
    )
    return service, adapter


def test_preview_normalizes_source_without_running_analysis(tmp_path):
    service, adapter = _url_service(tmp_path)

    preview = service.preview(
        "https://example.test/post/1?token=secret#fragment"
    )

    assert preview.display_url == "https://example.test/post/1"
    assert preview.post.provenance.source_ref_hash == (
        preview.source_ref_hash
    )
    assert preview.post.capture_status.source == "url:fixture"
    assert preview.post.capture_status.adapter_version == adapter.version
    assert "token=secret" not in preview.model_dump_json()
    assert "fragment" not in preview.model_dump_json()
    assert adapter.last_source.fetch_url == (
        "https://example.test/post/1?token=secret"
    )
    assert not (tmp_path / "runs").exists()


def test_unsupported_host_fails_before_adapter_call(tmp_path):
    service, adapter = _url_service(tmp_path)

    with pytest.raises(URLImportError) as exc:
        service.preview("https://other.test/post/1")

    assert exc.value.code == "unsupported_url_host"
    assert adapter.calls == 0


def test_preview_rejects_adapter_output_containing_query_value(tmp_path):
    analysis = _analysis_service(tmp_path)
    adapter = QueryValueLeakingAdapter()
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([adapter]),
    )

    with pytest.raises(URLImportError) as exc:
        service.preview(
            "https://example.test/post/1"
            "?api_key=do-not-store"
        )

    assert exc.value.code == "adapter_failed"
    assert "do-not-store" not in exc.value.message
    assert not (tmp_path / "runs").exists()


def test_confirm_applies_audited_corrections_and_consumes_preview(
    tmp_path,
):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")

    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(text="人工修正后的正文"),
        runtime_mode="local",
    )

    assert result.post.text == "人工修正后的正文"
    assert "text" in result.post.capture_status.user_corrections
    assert service.analysis_service.get_run(
        result.run_metadata.run_id
    ) is not None
    with pytest.raises(URLImportError) as exc:
        service.confirm(
            preview.preview_id,
            URLImportCorrections(),
        )
    assert exc.value.code == "preview_not_found"
    assert exc.value.status_code == 404


def test_invalid_correction_does_not_consume_preview(tmp_path):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")

    with pytest.raises(URLImportError) as exc:
        service.confirm(
            preview.preview_id,
            URLImportCorrections(creator_id="different"),
        )

    assert exc.value.code == "invalid_corrections"
    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(),
    )
    assert result.run_metadata.run_id


def test_unknown_preview_fails_closed(tmp_path):
    service, _ = _url_service(tmp_path)

    with pytest.raises(URLImportError) as exc:
        service.confirm(
            "preview_" + "0" * 32,
            URLImportCorrections(),
        )

    assert exc.value.code == "preview_not_found"
    assert exc.value.status_code == 404

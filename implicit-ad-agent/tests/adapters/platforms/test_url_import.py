from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread

import pytest

from impad.adapters import post_record_from_manual
from impad.adapters.platforms import (
    BilibiliAdapter,
    DisabledURLFetcher,
    PlatformAdapterRegistry,
    ResolvedTarget,
    SafeFetchResult,
    XiaohongshuAdapter,
    URLImportCorrections,
    URLImportError,
    URLImportService,
    validate_public_https_url,
)
from impad.contracts import DisclosureRecord, MediaRecord, PostRecord
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
        self.last_fetcher = None

    def preview(self, source, *, fetcher):
        self.calls += 1
        self.last_source = source
        self.last_fetcher = fetcher
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
    def preview(self, source, *, fetcher):
        post = super().preview(source, fetcher=fetcher)
        return post.model_copy(update={"text": "do-not-store"})


class TextAdapter(StaticAdapter):
    def __init__(self, text):
        super().__init__()
        self.text = text

    def preview(self, source, *, fetcher):
        post = super().preview(source, fetcher=fetcher)
        return post.model_copy(update={"text": self.text})


class UnsafeMediaAdapter(StaticAdapter):
    def __init__(self, ref):
        super().__init__()
        self.ref = ref

    def preview(self, source, *, fetcher):
        post = super().preview(source, fetcher=fetcher)
        return post.model_copy(update={
            "media": [MediaRecord(
                media_id="media-unsafe",
                type="image",
                ref=self.ref,
            )],
        })


FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "platforms"


class DeterministicFixtureFetcher:
    """Offline fetcher that only reads one checked-in fixture HTML file."""

    def __init__(self, path: Path):
        self.path = path
        self.fetch_calls: list[str] = []
        self.validate_calls: list[str] = []

    def validate_target(self, url: str) -> ResolvedTarget:
        self.validate_calls.append(url)
        source = validate_public_https_url(url)
        return ResolvedTarget(
            source=source,
            addresses=("203.0.113.1",),
            connect_ip="203.0.113.1",
        )

    def fetch(self, url: str) -> SafeFetchResult:
        self.fetch_calls.append(url)
        source = validate_public_https_url(url)
        return SafeFetchResult(
            body=self.path.read_bytes(),
            content_type="text/html",
            display_url=source.display_url,
            source_ref_hash=source.source_ref_hash,
        )


class BlockingAnalysisService(AnalysisService):
    def __init__(self, *, started, release, **kwargs):
        super().__init__(**kwargs)
        self.started = started
        self.release = release
        self.calls = 0
        self._calls_lock = Lock()

    def analyze(self, post, *, runtime_mode="local"):
        with self._calls_lock:
            self.calls += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test analysis release timed out")
        return super().analyze(post, runtime_mode=runtime_mode)


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


@pytest.mark.parametrize(
    ("platform", "case", "url", "expected_media_refs"),
    [
        (
            "xiaohongshu",
            "normal_complete",
            "https://www.xiaohongshu.com/explore/xhs_note_normal_001",
            ["https://media.example.test/xhs/image-1.jpg"],
        ),
        (
            "xiaohongshu",
            "video_missing_comments",
            "https://www.xiaohongshu.com/explore/xhs_note_video_001",
            [None],
        ),
        (
            "bilibili",
            "video_no_images",
            "https://www.bilibili.com/video/BV_SYNTHETIC_001",
            [],
        ),
        (
            "bilibili",
            "opus_partial_images",
            "https://www.bilibili.com/opus/bili_opus_001",
            ["https://media.example.test/bilibili/opus-1.jpg"],
        ),
        (
            "bilibili",
            "article_missing_disclosure_surface",
            "https://www.bilibili.com/read/cv123456",
            ["https://media.example.test/bilibili/article-1.jpg"],
        ),
    ],
)
def test_url_import_runs_all_platform_fixtures_offline(
    tmp_path,
    platform,
    case,
    url,
    expected_media_refs,
):
    fixture = FIXTURE_ROOT / platform / case
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    fetcher = DeterministicFixtureFetcher(fixture / "source.html")
    registry = PlatformAdapterRegistry([
        XiaohongshuAdapter(),
        BilibiliAdapter(),
    ])
    service = URLImportService(
        analysis_service=_analysis_service(tmp_path),
        registry=registry,
        fetcher=fetcher,
        media_cache_root=tmp_path / "media-cache",
    )

    source = validate_public_https_url(url)
    adapter = next(
        item for item in registry.adapters if item.platform == platform
    )
    expected_payload = expected.model_dump(mode="python")
    expected_payload["provenance"]["source_ref_hash"] = (
        source.source_ref_hash
    )
    expected_payload["capture_status"]["source"] = f"url:{platform}"
    expected_payload["capture_status"]["adapter_version"] = adapter.version
    expected = PostRecord.model_validate(expected_payload)

    preview = service.preview(url)

    assert preview.post == expected
    assert preview.platform == platform
    assert preview.post.post_id == expected.post_id
    assert preview.source_ref_hash == source.source_ref_hash
    assert preview.post.provenance.source_ref_hash == source.source_ref_hash
    assert preview.post.capture_status.source == f"url:{platform}"
    assert preview.post.capture_status.adapter_version == adapter.version
    assert [item.ref for item in preview.post.media] == expected_media_refs
    assert fetcher.fetch_calls == [source.fetch_url]
    assert fetcher.validate_calls == [
        ref for ref in expected_media_refs if ref is not None
    ]

    result = service.confirm(preview.preview_id, URLImportCorrections())

    assert result.post == expected
    assert result.post.platform == platform
    assert result.post.post_id == expected.post_id
    assert result.run_metadata.run_id
    assert service.analysis_service.get_run(
        result.run_metadata.run_id
    ) is not None


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
    assert isinstance(adapter.last_fetcher, DisabledURLFetcher)
    assert not (tmp_path / "runs").exists()


def test_url_import_injects_fetcher_and_rejects_unsafe_adapter_media(
    tmp_path,
):
    analysis = _analysis_service(tmp_path)
    adapter = UnsafeMediaAdapter(ref="../outside.jpg")
    fetcher = DisabledURLFetcher()
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([adapter]),
        fetcher=fetcher,
        media_cache_root=tmp_path / "cache",
    )

    with pytest.raises(URLImportError) as exc:
        service.preview("https://example.test/post/1")

    assert adapter.last_fetcher is fetcher
    assert exc.value.code == "unsafe_media_reference"
    assert service.preview_store._records == {}
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


def test_preview_allows_short_query_value_that_only_occurs_in_text(
    tmp_path,
):
    analysis = _analysis_service(tmp_path)
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([
            TextAdapter("版本 1 的正文"),
        ]),
    )

    preview = service.preview(
        "https://example.test/post/1?page=1#1"
    )

    assert preview.post.text == "版本 1 的正文"


def test_preview_rejects_json_escaped_query_value(tmp_path):
    analysis = _analysis_service(tmp_path)
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([
            TextAdapter('prefix line\n"quoted" suffix'),
        ]),
    )

    with pytest.raises(URLImportError) as exc:
        service.preview(
            "https://example.test/post/1"
            "?token=line%0A%22quoted%22"
        )

    assert exc.value.code == "adapter_failed"
    assert "quoted" not in exc.value.message


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


def test_confirm_applies_and_audits_disclosure_corrections(tmp_path):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")
    disclosures = [DisclosureRecord(
        kind="platform_badge",
        text="品牌合作",
        source="platform_metadata",
    )]

    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(disclosures=disclosures),
    )

    assert result.post.disclosures == disclosures
    assert "disclosures" in result.post.capture_status.user_corrections


def test_concurrent_confirm_reserves_preview_once(tmp_path):
    started = Event()
    release = Event()
    analysis = BlockingAnalysisService(
        started=started,
        release=release,
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    service = URLImportService(
        analysis_service=analysis,
        registry=PlatformAdapterRegistry([StaticAdapter()]),
    )
    preview = service.preview("https://example.test/post/1")
    results = []
    errors = []

    def confirm():
        try:
            results.append(service.confirm(
                preview.preview_id,
                URLImportCorrections(),
            ))
        except Exception as exc:
            errors.append(exc)

    first = Thread(target=confirm)
    second = Thread(target=confirm)
    first.start()
    assert started.wait(timeout=2)
    second.start()
    second.join(timeout=1)
    second_finished_before_release = not second.is_alive()
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert second_finished_before_release
    assert analysis.calls == 1
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], URLImportError)
    assert errors[0].code == "preview_not_found"


def test_returned_preview_cannot_mutate_pending_server_snapshot(tmp_path):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")

    preview.post.text = "绕过 corrections 的修改"
    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(),
    )

    assert result.post.text == "适配器提取正文"
    assert result.post.capture_status.user_corrections == []


def test_capture_correction_cannot_forge_adapter_audit_metadata(
    tmp_path,
):
    service, _ = _url_service(tmp_path)
    preview = service.preview("https://example.test/post/1")
    forged_capture = preview.post.capture_status.model_copy(update={
        "source": "forged",
        "adapter_version": "forged",
        "user_corrections": ["platform"],
    })

    result = service.confirm(
        preview.preview_id,
        URLImportCorrections(capture_status=forged_capture),
    )

    assert result.post.capture_status.source == "url:fixture"
    assert result.post.capture_status.adapter_version == "static-v1"
    assert result.post.capture_status.user_corrections == []


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

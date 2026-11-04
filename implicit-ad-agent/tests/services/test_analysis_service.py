from pathlib import Path
import json

import pytest

from impad.contracts import LawEvidence
import impad.services.analyze as analyze_module
from impad.services import AnalysisService, JsonRunStore
from impad.orchestration import MCPToolGateway


class StubRetriever:
    def retrieve(self, query, top_k=5):
        return [LawEvidence(
            source_id="samr_fixture",
            document_title="互联网广告管理办法",
            source_path_or_url="https://www.samr.gov.cn/example",
            article_id="第九条",
            document_version="第72号",
            quote="互联网广告应当具有可识别性。",
            retrieval_score=0.9,
        )]


class FailingMCPClient:
    def list_tools(self):
        return {
            "detection.analyze_text_intent",
            "detection.sentiment_curve",
        }

    def call_tool(self, name, arguments):
        raise ConnectionError("offline")


class ExplodingAnalysisService(AnalysisService):
    def analyze(self, post, *, runtime_mode="local"):
        raise RuntimeError("api_key=do-not-expose")


class ValueErrorAnalysisService(AnalysisService):
    def analyze(self, post, *, runtime_mode="local"):
        raise ValueError("internal execution detail")


def test_analysis_service_runs_rag_after_judge_and_persists_by_run_id(
    tmp_path: Path,
):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    result = service.analyze({
        "text": "品牌合作，广告，限时抢购",
        "capture_complete": True,
    })
    stored = service.get_run(result.run_metadata.run_id)

    assert stored is not None
    assert result.run_metadata.token_usage == {}
    assert result.run_metadata.cost_usd is None
    assert result.verdict_report.law_evidence[0].article_id == "第九条"
    assert stored.verdict_report == result.verdict_report
    assert stored.run_metadata.trace_ids
    assert {
        event.event_type for event in stored.run_events
    } >= {
        "judgment_completed",
        "rag_completed",
        "report_completed",
        "run_persisted",
    }
    assert stored.run_events[0].event_type == "analysis_started"
    assert stored.run_events[0].timestamp <= stored.run_events[1].timestamp
    assert "## 法规引用" in result.readable_report
    assert result.run_metadata.run_id in result.readable_report


def test_analysis_result_report_and_run_file_redact_sensitive_input(
    tmp_path: Path,
):
    run_dir = tmp_path / "runs"
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(run_dir),
    )
    secrets = {
        "cookie": "cookie-secret-123",
        "bearer": "bearer-secret-456",
        "query": "query-secret-abc",
        "fragment": "fragment-secret-def",
        "comment": "comment-token-secret",
        "ocr": "ocr-api-secret",
        "media_query": "media-query-secret",
    }
    text = (
        f"Cookie: sid={secrets['cookie']}\n"
        f"Authorization: Bearer {secrets['bearer']}\n"
        "查看 https://user:pass@example.test:8443/post"
        f"?token={secrets['query']}#{secrets['fragment']}"
    )

    result = service.analyze({
        "text": text,
        "comments": [{
            "comment_id": "comment-1",
            "text": f"access_token={secrets['comment']}",
        }],
        "media": [{
            "media_id": "media-1",
            "type": "image",
            "ref": (
                "https://media-user:media-pass@example.test:9443/image.jpg"
                f"?token={secrets['media_query']}#raw-fragment"
            ),
            "ocr_text": f"api_key={secrets['ocr']}",
        }],
        "capture_complete": True,
    })
    run_path = run_dir / f"{result.run_metadata.run_id}.json"
    outputs = [
        result.model_dump_json(),
        result.readable_report,
        run_path.read_text(encoding="utf-8"),
    ]

    leaked = {
        (name, output_index)
        for output_index, output in enumerate(outputs)
        for name, value in secrets.items()
        if value in output
    }
    assert leaked == set()
    for output in outputs:
        assert "user:pass" not in output
        assert "media-user:media-pass" not in output
        assert ":8443" not in output
        assert ":9443" not in output
    assert isinstance(result.run_metadata.token_usage, dict)
    stored = json.loads(run_path.read_text(encoding="utf-8"))
    assert isinstance(stored["run_metadata"]["token_usage"], dict)


def test_json_run_store_redacts_direct_store_calls(tmp_path: Path):
    run_dir = tmp_path / "runs"
    store = JsonRunStore(run_dir)
    service = AnalysisService(retriever=StubRetriever(), run_store=store)
    result = service.analyze({"text": "普通内容", "capture_complete": True})
    record = service.get_run(result.run_metadata.run_id)
    assert record is not None
    unsafe = record.model_copy(update={
        "post": record.post.model_copy(update={
            "text": "Authorization: Bearer direct-store-secret",
        }),
    })

    store.put(unsafe)

    serialized = (
        run_dir / f"{result.run_metadata.run_id}.json"
    ).read_text(encoding="utf-8")
    assert "direct-store-secret" not in serialized


def test_unknown_disclosure_is_preserved_by_unified_service(tmp_path: Path):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    result = service.analyze({
        "text": "这款面霜无限回购，链接在评论区",
    })

    assert result.verdict_report.disclosure.status == "unknown"
    assert result.verdict_report.review_required is True


def test_mcp_failure_uses_local_gateway_and_marks_hybrid_run(tmp_path: Path):
    gateway = MCPToolGateway(client=FailingMCPClient())
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
        mcp_gateway=gateway,
    )

    result = service.analyze(
        {"text": "品牌合作，广告，限时购买", "capture_complete": True},
        runtime_mode="mcp",
    )

    assert result.run_metadata.runtime_mode == "hybrid"
    assert result.run_metadata.fallback_count == 2


def test_batch_analysis_reuses_single_analysis_and_preserves_order(
    tmp_path: Path,
):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    items = [
        analyze_module.BatchAnalysisInput(
            post={"text": "普通记录"},
        ),
        analyze_module.BatchAnalysisInput(
            post={"text": "品牌合作，广告"},
        ),
    ]

    result = service.analyze_batch(items)

    assert result.total == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert [item.index for item in result.items] == [0, 1]
    assert all(item.result is not None for item in result.items)
    assert len({
        item.result.run_metadata.run_id
        for item in result.items
        if item.result is not None
    }) == 2


def test_batch_analysis_isolates_invalid_input(tmp_path: Path):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    result = service.analyze_batch([
        analyze_module.BatchAnalysisInput(post={
            "post_id": "target",
            "creator_id": "creator-a",
            "text": "invalid",
            "published_at": "2026-07-30T00:00:00Z",
            "history": [{
                "post_id": "history",
                "creator_id": "creator-b",
                "text": "other creator",
                "published_at": "2026-07-29T00:00:00Z",
            }],
        }),
        analyze_module.BatchAnalysisInput(post={"text": "valid"}),
    ])

    assert result.failed == 1
    assert result.succeeded == 1
    assert result.items[0].result is None
    assert result.items[0].error is not None
    assert result.items[0].error.code == "invalid_input"
    assert result.items[0].error.message == (
        "Input could not be normalized."
    )
    assert result.items[1].result is not None


def test_batch_analysis_hides_unexpected_error_details(tmp_path: Path):
    service = ExplodingAnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    result = service.analyze_batch([
        analyze_module.BatchAnalysisInput(post={"text": "valid"}),
    ])

    assert result.failed == 1
    assert result.items[0].error is not None
    assert result.items[0].error.code == "analysis_failed"
    assert result.items[0].error.message == "Analysis failed."
    assert "do-not-expose" not in result.model_dump_json()


def test_batch_analysis_does_not_misclassify_internal_value_error(
    tmp_path: Path,
):
    service = ValueErrorAnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    result = service.analyze_batch([
        analyze_module.BatchAnalysisInput(post={"text": "valid"}),
    ])

    assert result.failed == 1
    assert result.items[0].error is not None
    assert result.items[0].error.code == "analysis_failed"
    assert "internal execution detail" not in result.model_dump_json()


@pytest.mark.parametrize("count", [0, 51])
def test_batch_analysis_rejects_out_of_bounds_count(
    tmp_path: Path,
    count: int,
):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )

    with pytest.raises(ValueError, match="between 1 and 50"):
        service.analyze_batch([
            analyze_module.BatchAnalysisInput(
                post={"text": str(index)},
            )
            for index in range(count)
        ])

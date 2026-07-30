from pathlib import Path

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

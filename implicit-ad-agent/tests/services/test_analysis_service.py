from pathlib import Path

from impad.contracts import LawEvidence
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

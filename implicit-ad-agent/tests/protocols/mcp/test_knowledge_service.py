from impad.contracts import LawEvidence
from impad.protocols.mcp.knowledge_server import KnowledgeMCPService


class StubRetriever:
    def retrieve(self, query, top_k=5):
        if "广告" not in query:
            return []
        return [LawEvidence(
            source_id="official",
            document_title="法规",
            source_path_or_url="https://example.test/official",
            article_id="第九条",
            document_version="v1",
            quote="广告应当具有可识别性。",
            retrieval_score=0.9,
        )]


def test_knowledge_service_lists_calls_and_exposes_abstention():
    service = KnowledgeMCPService(StubRetriever())

    assert service.list_tools()[0]["name"] == (
        "knowledge.search_legal_rules"
    )
    found = service.call_tool(
        "knowledge.search_legal_rules",
        {"query": "广告可识别性", "top_k": 3},
    )
    abstained = service.call_tool(
        "knowledge.search_legal_rules",
        {"query": "天气", "top_k": 3},
    )

    assert found["abstained"] is False
    assert found["citations"][0]["article_id"] == "第九条"
    assert abstained == {
        "query": "天气",
        "abstained": True,
        "citations": [],
    }

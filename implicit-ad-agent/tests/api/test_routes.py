from fastapi.testclient import TestClient

from app import create_app
from impad.contracts import LawEvidence
from impad.services import AnalysisService, JsonRunStore


class StubRetriever:
    def retrieve(self, query, top_k=5):
        return [LawEvidence(
            source_id="official",
            document_title="法规",
            source_path_or_url="https://example.test",
            article_id="第九条",
            document_version="v1",
            quote="广告应当具有可识别性。",
            retrieval_score=0.9,
        )]


def test_versioned_analyze_and_run_query_share_the_service(tmp_path):
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    client = TestClient(create_app(service))

    analyzed = client.post("/api/v1/analyze", json={
        "text": "品牌合作，广告，限时购买",
        "capture_complete": True,
    })
    assert analyzed.status_code == 200
    payload = analyzed.json()
    run_id = payload["run_metadata"]["run_id"]

    queried = client.get(f"/api/v1/runs/{run_id}")
    assert queried.status_code == 200
    assert queried.json()["verdict_report"] == payload["verdict_report"]
    assert client.get("/api/v1/capabilities").json()["detection_tools"] == 7

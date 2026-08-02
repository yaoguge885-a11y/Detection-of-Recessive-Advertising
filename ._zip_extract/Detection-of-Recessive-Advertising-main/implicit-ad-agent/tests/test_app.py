from fastapi.testclient import TestClient

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def test_existing_health_and_single_analysis_routes_remain_available(
    tmp_path,
):
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    client = TestClient(create_app(service))

    assert client.get("/health").status_code == 200
    assert client.post(
        "/analyze",
        json={"text": "普通记录"},
    ).status_code == 200
    assert client.post(
        "/api/v1/analyze",
        json={"text": "普通记录"},
    ).status_code == 200

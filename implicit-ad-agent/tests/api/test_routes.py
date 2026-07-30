from fastapi.testclient import TestClient
import pytest

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


def _client(tmp_path) -> TestClient:
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    return TestClient(create_app(service))


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


def test_batch_route_returns_per_item_outcomes(tmp_path):
    response = _client(tmp_path).post(
        "/api/v1/analyze/batch",
        json={
            "items": [
                {"text": "普通记录"},
                {
                    "text": "品牌合作，广告",
                    "capture_complete": True,
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["succeeded"] == 2
    assert payload["failed"] == 0
    assert [item["index"] for item in payload["items"]] == [0, 1]
    assert all(item["ok"] for item in payload["items"])
    assert all(item["result"] is not None for item in payload["items"])


def test_batch_route_exposes_isolated_safe_error(tmp_path):
    response = _client(tmp_path).post(
        "/api/v1/analyze/batch",
        json={
            "items": [
                {
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
                },
                {"text": "valid"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    assert payload["items"][0] == {
        "index": 0,
        "ok": False,
        "result": None,
        "error": {
            "code": "invalid_input",
            "message": "Input could not be normalized.",
        },
    }
    assert payload["items"][1]["ok"] is True


@pytest.mark.parametrize("items", [[], [{"text": "x"}] * 51])
def test_batch_route_rejects_invalid_size(tmp_path, items):
    response = _client(tmp_path).post(
        "/api/v1/analyze/batch",
        json={"items": items},
    )

    assert response.status_code == 422

from fastapi.testclient import TestClient
import re

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def test_simple_app_serves_same_origin_assets_and_preserves_workbench(tmp_path):
    client = TestClient(create_app(AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )))

    for path in (
        "/app",
        "/app/",
        "/app/analyze",
        "/app/runs/run_example",
        "/app/history",
        "/app/unknown",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
    html = client.get("/app").text
    assets = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', html)
    assert len(assets) >= 2
    for asset in assets:
        assert client.get(asset).status_code == 200
    assert client.get("/app/assets/missing.js").status_code == 404
    assert client.get("/workbench").status_code == 200


def test_simple_app_analysis_and_run_recovery_use_same_contract(tmp_path):
    client = TestClient(create_app(AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )))

    analyzed = client.post("/api/v1/analyze", json={
        "text": "合成样例：今天记录一段日常。",
        "platform": "other",
        "capture_complete": False,
        "runtime_mode": "local",
    })
    assert analyzed.status_code == 200
    report = analyzed.json()
    run_id = report["run_metadata"]["run_id"]
    recovered = client.get(f"/api/v1/runs/{run_id}")
    assert recovered.status_code == 200
    assert recovered.json()["verdict_report"] == report["verdict_report"]
    assert recovered.json()["evidence_bundle"] == report["evidence_bundle"]
    assert report["verdict_report"]["label"] in {"明广", "暗广", "非广", "需复核"}
    assert report["verdict_report"]["disclosure"]["status"] == "unknown"
    assert report["evidence_bundle"]["missing_requirements"]
    assert client.get("/api/v1/runs/does-not-exist").status_code == 404

    needs_review = client.post("/api/v1/analyze", json={
        "text": "这款面霜无限回购，链接在评论区",
        "capture_complete": False,
    }).json()
    assert needs_review["verdict_report"]["label"] == "需复核"
    assert needs_review["verdict_report"]["review_required"] is True
    assert needs_review["verdict_report"]["disclosure"]["status"] == "unknown"

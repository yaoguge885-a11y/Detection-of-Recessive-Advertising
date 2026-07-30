from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from impad.services import AnalysisService, JsonRunStore


class EmptyRetriever:
    def retrieve(self, query, top_k=5):
        return []


def _client(tmp_path: Path) -> TestClient:
    service = AnalysisService(
        retriever=EmptyRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    return TestClient(create_app(service))


def test_workbench_document_and_assets_are_served(tmp_path):
    client = _client(tmp_path)

    document = client.get("/workbench")
    stylesheet = client.get("/workbench/assets/workbench.css")
    script = client.get("/workbench/assets/workbench.js")

    assert document.status_code == 200
    assert document.encoding.lower() == "utf-8"
    assert "text/html" in document.headers["content-type"]
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]


def test_workbench_document_has_strict_security_headers(tmp_path):
    response = _client(tmp_path).get("/workbench")

    assert response.headers["content-security-policy"] == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


def test_root_links_to_workbench(tmp_path):
    response = _client(tmp_path).get("/")

    assert response.status_code == 200
    assert 'href="/workbench"' in response.text

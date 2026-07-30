from fastapi.testclient import TestClient
import pytest

from app import create_app
from impad.adapters import post_record_from_manual
from impad.adapters.platforms import (
    PlatformAdapterRegistry,
    URLImportService,
)
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


class StaticURLAdapter:
    name = "static"
    version = "static-v1"
    platform = "fixture"
    supported_hosts = ("example.test",)

    def preview(self, source):
        return post_record_from_manual({
            "post_id": "fixture-post",
            "platform": self.platform,
            "source_type": "url_import",
            "creator_id": "creator-1",
            "published_at": "2026-07-30T00:00:00Z",
            "text": "适配器正文",
            "history": [{
                "post_id": "history-1",
                "creator_id": "creator-1",
                "published_at": "2026-07-29T00:00:00Z",
                "text": "历史正文",
            }],
        })


def _client(tmp_path) -> TestClient:
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    return TestClient(create_app(service))


def _url_client(tmp_path) -> TestClient:
    service = AnalysisService(
        retriever=StubRetriever(),
        run_store=JsonRunStore(tmp_path / "runs"),
    )
    url_service = URLImportService(
        analysis_service=service,
        registry=PlatformAdapterRegistry([StaticURLAdapter()]),
    )
    return TestClient(create_app(
        service,
        url_import_service=url_service,
    ))


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


def test_url_preview_and_confirm_routes(tmp_path):
    client = _url_client(tmp_path)

    preview_response = client.post(
        "/api/v1/import/url/preview",
        json={
            "url": (
                "https://example.test/post/1"
                "?token=secret#fragment"
            )
        },
    )

    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["display_url"] == (
        "https://example.test/post/1"
    )
    assert "token=secret" not in preview_response.text
    assert "fragment" not in preview_response.text

    confirmed = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": preview["preview_id"],
            "corrections": {"text": "人工修正"},
            "runtime_mode": "local",
        },
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["run_metadata"]["run_id"]


def test_url_query_secret_is_absent_from_confirmed_run(tmp_path):
    client = _url_client(tmp_path)
    preview = client.post(
        "/api/v1/import/url/preview",
        json={
            "url": (
                "https://example.test/post/1"
                "?api_key=do-not-store#private-fragment"
            )
        },
    ).json()

    confirmed = client.post(
        "/api/v1/import/url/confirm",
        json={"preview_id": preview["preview_id"]},
    )

    assert confirmed.status_code == 200
    run_id = confirmed.json()["run_metadata"]["run_id"]
    queried = client.get(f"/api/v1/runs/{run_id}")
    assert queried.status_code == 200
    assert "do-not-store" not in confirmed.text
    assert "private-fragment" not in confirmed.text
    assert "do-not-store" not in queried.text
    assert "private-fragment" not in queried.text


def test_default_app_rejects_unsupported_url_before_fetch():
    response = TestClient(create_app()).post(
        "/api/v1/import/url/preview",
        json={"url": "https://example.test/post/1"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == (
        "unsupported_url_host"
    )


def test_url_confirm_maps_missing_and_invalid_preview_errors(tmp_path):
    client = _url_client(tmp_path)
    missing = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": "preview_" + "0" * 32,
            "corrections": {},
        },
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "preview_not_found"

    preview = client.post(
        "/api/v1/import/url/preview",
        json={"url": "https://example.test/post/1"},
    ).json()
    invalid = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": preview["preview_id"],
            "corrections": {"creator_id": "different"},
        },
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_corrections"


@pytest.mark.parametrize(
    "immutable_field",
    ["post_id", "platform", "provenance", "privacy", "unknown"],
)
def test_url_confirm_rejects_non_allowlisted_corrections_without_consuming(
    tmp_path,
    immutable_field,
):
    client = _url_client(tmp_path)
    preview = client.post(
        "/api/v1/import/url/preview",
        json={"url": "https://example.test/post/1"},
    ).json()

    rejected = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": preview["preview_id"],
            "corrections": {immutable_field: "replacement"},
        },
    )

    assert rejected.status_code == 422
    accepted = client.post(
        "/api/v1/import/url/confirm",
        json={
            "preview_id": preview["preview_id"],
            "corrections": {},
        },
    )
    assert accepted.status_code == 200


def test_capabilities_report_batch_and_registered_url_adapters(tmp_path):
    payload = _url_client(tmp_path).get(
        "/api/v1/capabilities"
    ).json()

    assert payload["batch_analysis"] == {
        "enabled": True,
        "max_items": 50,
    }
    assert payload["url_import"]["enabled"] is True
    assert payload["url_import"]["workflow"] == ["preview", "confirm"]
    assert payload["url_import"]["platforms"] == [{
        "platform": "fixture",
        "adapter": "static",
        "version": "static-v1",
        "hosts": ["example.test"],
    }]


def test_default_capabilities_do_not_claim_live_platform_adapters():
    payload = TestClient(create_app()).get(
        "/api/v1/capabilities"
    ).json()

    assert payload["url_import"]["platforms"] == []

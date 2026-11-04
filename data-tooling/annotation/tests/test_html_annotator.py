"""Tests for the local HTML annotation workbench.

The workbench deliberately uses only the standard library plus the existing
``auto_judge`` module.  These tests exercise the storage contract directly and
the HTTP surface with a real loopback server; no Ollama process is required.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ANNOTATION_DIR = Path(__file__).resolve().parents[1]
if str(ANNOTATION_DIR) not in sys.path:
    sys.path.insert(0, str(ANNOTATION_DIR))

from annotation_workbench import ollama_bridge  # noqa: E402
from annotation_workbench.ollama_bridge import (  # noqa: E402
    AdviceDisabled,
    AdviceError,
    AdviceResult,
    OllamaBridge,
)
from annotation_workbench.server import (  # noqa: E402
    WorkbenchApp,
    create_server,
)
from annotation_workbench.store import (  # noqa: E402
    AnnotationStore,
    BatchSpec,
    ConflictError,
    ManifestError,
    NotFoundError,
    ValidationError,
    WorkbenchError,
    comments_view,
    disclosure_view,
    display_post,
    media_view,
    prepare_batch,
    resolve_media_path,
    validate_annotation_input,
)


# ---------------------------------------------------------------------------
# fixtures


def post(pid: str, **overrides):
    data = {
        "post_id": pid,
        "platform": "小红书",
        "source_type": "note",
        "blogger_id": "blogger-1",
        "title": f"标题 {pid}",
        "text": f"正文 {pid} 这是一条合成帖子。",
        "collection_complete": True,
        "comments": [{"author": "评论者", "text": f"评论 {pid}"}],
        "media": [],
        "provenance": {"collector": "synthetic"},
    }
    data.update(overrides)
    return data


def write_dataset(path: Path, posts):
    path.write_text(
        json.dumps({"content_records": posts}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def make_spec(tmp_path: Path, posts, *, manifest=None, annotator="alice",
              role="exploratory", dataset_id="synthetic", batch_id="batch1"):
    media_root = tmp_path / "media"
    media_root.mkdir(exist_ok=True)
    dataset = write_dataset(tmp_path / "dataset.json", posts)
    manifest_path = None
    if manifest is not None:
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"post_ids": manifest}), encoding="utf-8")
    return BatchSpec(
        dataset_id=dataset_id,
        batch_id=batch_id,
        annotator_id=annotator,
        dataset_path=dataset,
        output_root=tmp_path / "out",
        media_root=media_root,
        manifest_path=manifest_path,
        manifest_role=role,
    )


def valid_payload(**overrides):
    payload = {
        "label": "非广",
        "confidence": 0.8,
        "evidence_codes": [],
        "evidence": ["没有发现足够的商业推广证据。"],
        "uncertain_reason": None,
        "notes": "test",
    }
    payload.update(overrides)
    return payload


class FakeBridge:
    model = "qwen3.5:9b"
    url = "http://127.0.0.1:11434"
    enabled = True

    def suggest(self, post, *, collection_complete=None):
        raise AssertionError("fake bridge must not be called in this test")


@pytest.fixture
def store(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1"), post("p2"), post("p3")]))
    instance = AnnotationStore(prepared)
    yield instance
    instance.close()


# ---------------------------------------------------------------------------
# manifest and batch isolation


def test_manifest_preserves_order(tmp_path):
    prepared = prepare_batch(
        make_spec(
            tmp_path,
            [post("p1"), post("p2"), post("p3")],
            manifest=["p3", "p1", "p2"],
        )
    )
    assert prepared.ordered_ids == ["p3", "p1", "p2"]
    assert prepared.manifest_validation["post_count"] == 3
    assert prepared.manifest_validation["duplicate_count"] == 0
    assert prepared.manifest_validation["missing_count"] == 0


def test_manifest_rejects_duplicates(tmp_path):
    with pytest.raises(ManifestError, match="重复"):
        prepare_batch(make_spec(tmp_path, [post("p1"), post("p2")], manifest=["p1", "p1"]))


def test_manifest_rejects_missing_posts(tmp_path):
    with pytest.raises(ManifestError, match="缺失"):
        prepare_batch(make_spec(tmp_path, [post("p1")], manifest=["p1", "p_missing"]))


def test_no_manifest_is_exploratory_only(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    assert prepared.formal_gold_allowed is False
    assert any("探索性" in warning for warning in prepared.warnings)
    assert prepared.manifest["formal_gold_allowed"] is False


def test_approved_without_manifest_is_not_formal(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")], role="approved"))
    assert prepared.formal_gold_allowed is False
    assert any("approved" in warning for warning in prepared.warnings)


def test_existing_batch_metadata_mismatch_is_rejected(tmp_path):
    spec = make_spec(tmp_path, [post("p1"), post("p2")], manifest=["p1", "p2"])
    prepare_batch(spec)
    changed = BatchSpec(
        dataset_id=spec.dataset_id,
        batch_id=spec.batch_id,
        annotator_id=spec.annotator_id,
        dataset_path=spec.dataset_path,
        output_root=spec.output_root,
        media_root=spec.media_root,
        manifest_path=spec.manifest_path,
        manifest_role="approved",
    )
    with pytest.raises(ManifestError, match="批次元数据不匹配"):
        prepare_batch(changed)


def test_tampered_batch_manifest_is_rejected(tmp_path):
    spec = make_spec(tmp_path, [post("p1")])
    prepared = prepare_batch(spec)
    manifest_path = prepared.batch_dir / "batch_manifest.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["post_count"] = 999
    manifest_path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ManifestError, match="_sha256"):
        prepare_batch(spec)


# ---------------------------------------------------------------------------
# append-only storage, restart and annotator isolation


def test_save_and_restart_recovery(tmp_path):
    spec = make_spec(tmp_path, [post("p1"), post("p2")])
    first = AnnotationStore(prepare_batch(spec))
    saved = first.save("p1", valid_payload(), annotation_method="human", saw_model_advice=False)
    assert saved["revision"] == 1
    first.close()

    second = AnnotationStore(prepare_batch(spec))
    recovered = second.get("p1")
    assert recovered is not None
    assert recovered["label"] == "非广"
    assert recovered["evidence"] == ["没有发现足够的商业推广证据。"]

    updated = second.save(
        "p1",
        valid_payload(label="非广", confidence=0.7, notes="second"),
        annotation_method="human",
        saw_model_advice=False,
    )
    assert updated["revision"] == 2
    second.close()

    third = AnnotationStore(prepare_batch(spec))
    assert third.get("p1")["revision"] == 2
    assert third.get("p1")["notes"] == "second"
    third.close()


def test_corrupt_last_line_is_reported_and_ignored(tmp_path):
    spec = make_spec(tmp_path, [post("p1")])
    first = AnnotationStore(prepare_batch(spec))
    first.save("p1", valid_payload(), annotation_method="human", saw_model_advice=False)
    first.close()
    log = tmp_path / "out" / "synthetic" / "batch1" / "alice" / "annotations.jsonl"
    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"post_id": "p1", broken')

    second = AnnotationStore(prepare_batch(spec))
    assert second.get("p1") is not None
    assert any("末行" in warning for warning in second.warnings)
    second.close()


def test_annotator_directories_are_isolated(tmp_path):
    posts = [post("p1"), post("p2")]
    alice_prepared = prepare_batch(make_spec(tmp_path, posts, annotator="alice"))
    bob_prepared = prepare_batch(make_spec(tmp_path, posts, annotator="bob"))
    alice = AnnotationStore(alice_prepared)
    bob = AnnotationStore(bob_prepared)
    try:
        alice.save("p1", valid_payload(label="明广", confidence=0.9,
                                       evidence_codes=["D", "C"], evidence=["明确赞助标识"]),
                   annotation_method="human", saw_model_advice=False)
        assert bob.get("p1") is None
        bob.save("p1", valid_payload(label="非广", confidence=0.7),
                 annotation_method="human", saw_model_advice=False)
        assert alice.get("p1")["label"] == "明广"
        assert bob.get("p1")["label"] == "非广"
        assert alice.stats()["done"] == 1
        assert bob.stats()["done"] == 1
    finally:
        alice.close()
        bob.close()


def test_same_annotator_is_locked(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    first = AnnotationStore(prepared)
    try:
        with pytest.raises(WorkbenchError, match="占用"):
            AnnotationStore(prepared)
    finally:
        first.close()
    second = AnnotationStore(prepared)
    second.close()


def test_export_is_in_batch_order(tmp_path):
    prepared = prepare_batch(
        make_spec(tmp_path, [post("p1"), post("p2"), post("p3")], manifest=["p3", "p1", "p2"])
    )
    instance = AnnotationStore(prepared)
    try:
        instance.save("p1", valid_payload(), annotation_method="human", saw_model_advice=False)
        instance.save("p3", valid_payload(label="非广"), annotation_method="human", saw_model_advice=False)
        exported = instance.export_records()
        assert [row["post_id"] for row in exported] == ["p3", "p1"]
        assert [row["export_sequence"] for row in exported] == [0, 1]
        assert instance.export_records() == exported
    finally:
        instance.close()


# ---------------------------------------------------------------------------
# annotation contract


def test_annotation_validation_contract():
    assert validate_annotation_input(valid_payload())["label"] == "非广"

    with pytest.raises(ValidationError, match="D"):
        validate_annotation_input(valid_payload(label="明广", evidence_codes=["C"]))
    with pytest.raises(ValidationError, match="不得包含 D"):
        validate_annotation_input(valid_payload(label="暗广", evidence_codes=["D"]))
    with pytest.raises(ValidationError, match="B"):
        validate_annotation_input(valid_payload(label="非广", evidence_codes=["B"]))
    with pytest.raises(ValidationError, match="不确定原因"):
        validate_annotation_input(valid_payload(label="uncertain", uncertain_reason=None))
    with pytest.raises(ValidationError, match="0-1"):
        validate_annotation_input(valid_payload(confidence=1.2))
    with pytest.raises(ValidationError, match="证据说明"):
        validate_annotation_input(valid_payload(label="明广", evidence_codes=["D"], evidence=[]))


# ---------------------------------------------------------------------------
# display semantics: missing media, comments, disclosure, paths


def test_missing_media_and_path_traversal_are_explicit(tmp_path, store):
    media_root = store.spec.media_root
    (media_root / "media").mkdir(parents=True, exist_ok=True)
    (media_root / "media" / "ok.jpg").write_bytes(b"jpeg")
    record = post("p1", media=[
        {"type": "image", "ref": "media/ok.jpg"},
        {"type": "image", "ref": "../secret.txt"},
        {"type": "image", "ref": "media/nope.jpg"},
        {"type": "video", "ref": "C:\\Windows\\win.ini"},
        {"type": "image", "ref": "C:drive-relative.jpg"},
        {"type": "image", "ref": "https://example.invalid/x.jpg", "source_url": "https://example.invalid/x.jpg"},
    ])
    entries = media_view(record, media_root)
    assert [entry["status"] for entry in entries] == [
        "ok", "outside", "missing", "outside", "outside", "remote_only"
    ]
    assert entries[0]["url"].startswith("/media?post_id=p1")
    assert entries[1]["url"] is None
    assert "越界" in entries[1]["label"]
    assert "缺失" in entries[2]["label"]
    assert entries[5]["url"] is None

    with pytest.raises(ValueError):
        resolve_media_path(media_root, "../secret.txt")
    with pytest.raises(ValueError):
        resolve_media_path(media_root, "C:\\Windows\\win.ini")
    with pytest.raises(ValueError):
        resolve_media_path(media_root, "C:drive-relative.jpg")
    with pytest.raises(FileNotFoundError):
        resolve_media_path(media_root, "media/nope.jpg")


def test_comment_semantics_distinguish_missing_empty_and_complete():
    assert comments_view({})["status"] == "missing"
    assert "未采集" in comments_view({})["label"]

    complete_empty = comments_view({"collection_complete": True, "comments": []})
    assert complete_empty["status"] == "empty_complete"
    assert "无评论" in complete_empty["label"]

    incomplete_empty = comments_view({"collection_complete": False, "comments": []})
    assert incomplete_empty["status"] == "empty_uncertain"
    assert "不完整" in incomplete_empty["label"]

    truncated = comments_view({"comments": [{"text": str(i)} for i in range(250)]})
    assert truncated["total"] == 250
    assert truncated["truncated"] is True
    assert len(truncated["items"]) == 200


def test_disclosure_semantics_distinguish_absent_from_uncaptured():
    present = disclosure_view({"collection_complete": True, "disclosure": "赞助合作"})
    assert present["status"] == "present"
    assert present["detail"] == "赞助合作"

    absent = disclosure_view({"collection_complete": True})
    assert absent["status"] == "absent_complete"
    assert "未发现" in absent["label"]

    missing = disclosure_view({"collection_complete": False})
    assert missing["status"] == "missing"
    assert "不能视为" in missing["label"]

    unknown = disclosure_view({})
    assert unknown["status"] == "unknown"


def test_display_post_marks_missing_title_and_text(store):
    record = post("p1", title=None, text="")
    displayed = display_post(record, store.spec.media_root, 0)
    assert displayed["title_missing"] is True
    assert displayed["text_missing"] is True
    assert displayed["comments"]["status"] == "present"


# ---------------------------------------------------------------------------
# HTTP surface


class JsonResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def suggestion_json(label="非广", confidence=0.7):
    return {
        "label": label,
        "confidence": confidence,
        "evidence_codes": [],
        "evidence": ["合成测试证据"],
        "reasoning": "合成测试理由",
        "uncertain_reason": None,
        "information_gaps": [],
    }


def http_json(server, app, path, *, method="GET", body=None, token=True):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    headers = {}
    if token:
        headers["X-Workbench-Token"] = app.token
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}


def http_raw(server, app, path, *, token=True):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    headers = {"X-Workbench-Token": app.token} if token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


@pytest.fixture
def live_server(tmp_path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "media").mkdir()
    (media_root / "media" / "ok.jpg").write_bytes(b"jpeg-bytes")
    prepared = prepare_batch(make_spec(
        tmp_path,
        [post("p1", media=[
            {"type": "image", "ref": "media/ok.jpg"},
            {"type": "image", "ref": "../secret.txt"},
        ]), post("p2"), post("p3")],
    ))
    instance = AnnotationStore(prepared)
    app = WorkbenchApp(instance, FakeBridge(), auto_suggest=False)
    server = create_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, app
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        instance.close()


def test_http_requires_token_and_host(live_server):
    server, app = live_server
    status, payload = http_json(server, app, "/api/state", token=False)
    assert status == 403
    assert "token" in payload["error"]

    status, payload = http_json(server, app, "/api/state")
    assert status == 200
    assert payload["dataset_id"] == "synthetic"
    assert payload["blind_mode"] is True
    assert payload["formal_gold_allowed"] is False


def test_http_state_post_and_blind_mode(live_server):
    server, app = live_server
    status, payload = http_json(server, app, "/api/post?index=0")
    assert status == 200
    assert payload["post"]["post_id"] == "p1"
    assert payload["post"]["media"][0]["status"] == "ok"
    assert payload["post"]["media"][1]["status"] == "outside"
    assert "&token=" in payload["post"]["media"][0]["url"]
    assert payload["advice_state"]["status"] == "not_requested"

    status, payload = http_json(
        server, app, "/api/suggest", method="POST", body={"post_id": "p1"}
    )
    assert status == 403
    assert payload["code"] == "blind_mode"


def test_http_annotation_and_exports(live_server):
    server, app = live_server
    status, payload = http_json(
        server, app, "/api/annotation", method="POST",
        body={"post_id": "p2", "payload": valid_payload(), "saw_model_advice": False},
    )
    assert status == 200
    assert payload["annotation"]["annotation_method"] == "human"
    assert payload["progress"]["done"] == 1

    status, data, content_type = http_raw(server, app, "/api/export?format=jsonl")
    assert status == 200
    assert "ndjson" in content_type
    lines = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["post_id"] == "p2"
    assert lines[0]["export_sequence"] == 1

    status, data, _ = http_raw(server, app, "/api/export?format=json")
    assert status == 200
    exported = json.loads(data.decode("utf-8"))
    assert exported["count"] == 1
    assert exported["annotations"][0]["post_id"] == "p2"
    assert "human_assisted" in exported["annotation_method_notice"]


def test_http_media_access_and_outside_rejection(live_server):
    server, app = live_server
    status, data, _ = http_raw(server, app, "/media?post_id=p1&i=0")
    assert status == 200
    assert data == b"jpeg-bytes"

    status, _, _ = http_raw(server, app, "/media?post_id=p1&i=1")
    assert status == 403

    status, _, _ = http_raw(server, app, "/media?post_id=p1&i=9")
    assert status == 404


def test_static_index_is_served_without_token(live_server):
    server, app = live_server
    status, data, content_type = http_raw(server, app, "/", token=False)
    assert status == 200
    assert "text/html" in content_type
    assert "标注工作台" in data.decode("utf-8")


# ---------------------------------------------------------------------------
# Ollama integration contract


def bridge(tmp_path):
    guide = tmp_path / "guide.md"
    guide.write_text("# 合成指南\n版本：1.0\n", encoding="utf-8")
    return OllamaBridge(model="qwen3.5:9b", guide_path=guide)


def test_two_suggestions_send_only_current_post_and_never_save(tmp_path, monkeypatch):
    prepared = prepare_batch(make_spec(tmp_path, [
        post("p1", title="FIRST_UNIQUE_TITLE", text="FIRST_UNIQUE_BODY"),
        post("p2", title="SECOND_UNIQUE_TITLE", text="SECOND_UNIQUE_BODY"),
    ]))
    instance = AnnotationStore(prepared)
    app = WorkbenchApp(instance, bridge(tmp_path), auto_suggest=True)
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        return JsonResponse({"message": {"content": json_module.dumps(suggestion_json(), ensure_ascii=False)}})

    json_module = json
    monkeypatch.setattr(ollama_bridge.auto_judge.requests, "post", fake_post)
    try:
        app.suggest({"post_id": "p1"})
        app.suggest({"post_id": "p2"})
    finally:
        instance.close()

    assert len(calls) == 2
    for payload in calls:
        assert [message["role"] for message in payload["messages"]] == ["system", "user"]
        assert payload["think"] is False
        assert payload["format"]["required"]
        assert payload["options"]["num_predict"] == 1536
    first_user = calls[0]["messages"][1]["content"]
    second_user = calls[1]["messages"][1]["content"]
    assert "FIRST_UNIQUE_TITLE" in first_user
    assert "FIRST_UNIQUE_BODY" in first_user
    assert "FIRST_UNIQUE_TITLE" not in second_user
    assert "FIRST_UNIQUE_BODY" not in second_user
    assert "SECOND_UNIQUE_TITLE" in second_user
    assert instance.get("p1") is None
    assert instance.get("p2") is None


def test_ollama_error_is_visible_and_never_autosaved(tmp_path, monkeypatch):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    instance = AnnotationStore(prepared)
    app = WorkbenchApp(instance, bridge(tmp_path), auto_suggest=True)

    def failing_post(*args, **kwargs):
        raise ConnectionError("synthetic ollama failure")

    monkeypatch.setattr(ollama_bridge.auto_judge.requests, "post", failing_post)
    try:
        with pytest.raises(AdviceError, match="synthetic ollama failure"):
            app.suggest({"post_id": "p1"})
        state = app.post_payload(0)["advice_state"]
        assert state["status"] == "error"
        assert "synthetic ollama failure" in state["error"]
        assert instance.get("p1") is None
    finally:
        instance.close()


def test_advice_requires_explicit_ack_and_marks_human_assisted(tmp_path, monkeypatch):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    instance = AnnotationStore(prepared)
    app = WorkbenchApp(instance, bridge(tmp_path), auto_suggest=True)

    def fake_post(url, json=None, timeout=None):
        return JsonResponse({"message": {"content": json_module.dumps(suggestion_json("非广"), ensure_ascii=False)}})

    json_module = json
    monkeypatch.setattr(ollama_bridge.auto_judge.requests, "post", fake_post)
    try:
        app.suggest({"post_id": "p1"})
        with pytest.raises(ConflictError, match="看过模型建议"):
            app.save_annotation({
                "post_id": "p1",
                "payload": valid_payload(),
                "saw_model_advice": False,
            })
        saved = app.save_annotation({
            "post_id": "p1",
            "payload": valid_payload(),
            "saw_model_advice": True,
        })["annotation"]
        assert saved["annotation_method"] == "human_assisted"
        assert saved["saw_model_advice"] is True
        assert saved["model_advice_label"] == "非广"

        # Provenance is sticky: a later save without the checkbox must not
        # silently turn an assisted record into an independent human record.
        second = app.save_annotation({
            "post_id": "p1",
            "payload": valid_payload(notes="second pass"),
            "saw_model_advice": False,
        })["annotation"]
        assert second["annotation_method"] == "human_assisted"
        assert second["saw_model_advice"] is True
    finally:
        instance.close()


def test_disabling_advice_switches_to_blind_mode(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    instance = AnnotationStore(prepared)
    app = WorkbenchApp(instance, FakeBridge(), auto_suggest=True)
    try:
        assert app.state_payload()["blind_mode"] is False
        app.set_auto_suggest({"auto_suggest": False})
        assert app.state_payload()["blind_mode"] is True
        with pytest.raises(AdviceDisabled):
            app.suggest({"post_id": "p1"})
    finally:
        instance.close()


def test_startup_blind_mode_cannot_be_re_enabled_in_session(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")]))
    instance = AnnotationStore(prepared)
    bridge = FakeBridge()
    bridge.enabled = False
    app = WorkbenchApp(instance, bridge, auto_suggest=False)
    try:
        assert app.state_payload()["suggest_available"] is False
        with pytest.raises(WorkbenchError, match="no-auto-suggest"):
            app.set_auto_suggest({"auto_suggest": True})
    finally:
        instance.close()


def test_records_with_wrong_annotator_are_ignored(tmp_path):
    prepared = prepare_batch(make_spec(tmp_path, [post("p1")], annotator="alice"))
    instance = AnnotationStore(prepared)
    instance.save("p1", valid_payload(), annotation_method="human", saw_model_advice=False)
    instance.close()
    log = tmp_path / "out" / "synthetic" / "batch1" / "alice" / "annotations.jsonl"
    line = json.loads(log.read_text(encoding="utf-8"))
    line["annotator_id"] = "bob"
    log.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")

    reopened = AnnotationStore(prepare_batch(make_spec(tmp_path, [post("p1")], annotator="alice")))
    try:
        assert reopened.get("p1") is None
        assert any("annotator_id" in warning for warning in reopened.warnings)
    finally:
        reopened.close()

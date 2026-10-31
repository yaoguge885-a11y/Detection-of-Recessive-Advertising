"""Loopback-only HTTP server and JSON API for the annotation workbench."""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

from .ollama_bridge import AdviceDisabled, AdviceError, OllamaBridge
from .store import (
    AnnotationStore,
    ConflictError,
    ManifestError,
    NotFoundError,
    ValidationError,
    WorkbenchError,
    display_post,
    media_view,
    resolve_media_path,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 2 * 1024 * 1024


def _print_url(url: str) -> None:
    print("\n" + "=" * 72)
    print("HTML 标注工作台已启动（仅监听 127.0.0.1，关闭窗口即停止）：")
    print(url)
    print("=" * 72 + "\n", flush=True)


class WorkbenchApp:
    def __init__(self, store: AnnotationStore, bridge: OllamaBridge, *, auto_suggest: bool):
        self.store = store
        self.bridge = bridge
        self.auto_suggest = bool(auto_suggest)
        self.token = secrets.token_urlsafe(24)
        self._lock = threading.Lock()
        self.advice: Dict[str, Dict[str, Any]] = {}

    # ---- payloads -------------------------------------------------
    def state_payload(self) -> Dict[str, Any]:
        prepared = self.store.prepared
        stats = self.store.stats()
        manifest = prepared.manifest
        return {
            "dataset_id": self.store.spec.dataset_id,
            "batch_id": self.store.spec.batch_id,
            "annotator_id": self.store.spec.annotator_id,
            "dataset_name": self.store.spec.dataset_path.name,
            "manifest_name": self.store.spec.manifest_path.name if self.store.spec.manifest_path else None,
            "manifest_role": self.store.spec.manifest_role,
            "formal_gold_allowed": prepared.formal_gold_allowed,
            "guide_version": self.store.spec.guide_version,
            "guide_sha256": self.store.spec.guide_sha256,
            "model": self.bridge.model,
            "ollama_url": self.bridge.url,
            "auto_suggest": self.auto_suggest,
            "blind_mode": not self.auto_suggest,
            "suggest_available": self.bridge.enabled,
            "progress": stats,
            "post_count": len(prepared.ordered_ids),
            "manifest": {
                "post_count": prepared.manifest_validation.get("post_count"),
                "duplicate_count": prepared.manifest_validation.get("duplicate_count", 0),
                "missing_count": prepared.manifest_validation.get("missing_count", 0),
                "ordered_post_ids_sha256": prepared.manifest_validation.get("ordered_post_ids_sha256"),
                "dataset_sha256": manifest.get("dataset_sha256"),
                "manifest_sha256": manifest.get("manifest_sha256"),
            },
            "warnings": list(self.store.warnings),
        }

    def index_payload(self) -> Dict[str, Any]:
        rows = []
        for index, post_id in enumerate(self.store.prepared.ordered_ids):
            record = self.store.get(post_id)
            rows.append({
                "index": index,
                "post_id": post_id,
                "done": record is not None,
                "label": record.get("label") if record else None,
                "annotation_method": record.get("annotation_method") if record else None,
            })
        return {"posts": rows, "total": len(rows)}

    def post_payload(self, index: int) -> Dict[str, Any]:
        ordered = self.store.prepared.ordered_ids
        if index < 0 or index >= len(ordered):
            raise NotFoundError(f"帖子序号越界：{index}（共 {len(ordered)} 条）")
        post_id = ordered[index]
        post = self.store.prepared.by_id[post_id]
        displayed = display_post(post, self.store.spec.media_root, index)
        for item in displayed["media"]:
            if item.get("url"):
                item["url"] = f"{item['url']}&token={quote(self.token, safe='')}"
        with self._lock:
            advice = self.advice.get(post_id)
            advice = dict(advice) if advice else {"status": "not_requested"}
            if advice.get("advice"):
                advice["advice"] = dict(advice["advice"])
        return {
            "post": displayed,
            "annotation": self.store.get(post_id),
            "advice_state": advice,
            "saved": self.store.get(post_id) is not None,
            "total": len(ordered),
        }

    # ---- mutations ------------------------------------------------
    def save_annotation(self, body: Dict[str, Any]) -> Dict[str, Any]:
        post_id = body.get("post_id")
        if not isinstance(post_id, str) or post_id not in self.store.prepared.by_id:
            raise NotFoundError("post_id 不在当前批次")
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValidationError("payload 必须是对象")
        saw = bool(body.get("saw_model_advice", False))
        with self._lock:
            previous = self.store.get(post_id)
            if previous and previous.get("annotation_method") == "human_assisted":
                # Provenance is sticky: once a post was assisted, a later edit
                # cannot be relabelled as an independent human judgement.
                saw = True
            state = self.advice.get(post_id) or {"status": "not_requested"}
            status = str(state.get("status") or "not_requested")
            if not self.auto_suggest:
                if saw:
                    raise ConflictError("盲标模式下不能声称看过模型建议")
                method = "human"
                model = None
                model_label = None
                status = "not_requested"
            else:
                if saw and status not in {"ok", "error"}:
                    raise ConflictError("没有可用的模型建议记录，不能声称看过建议")
                if status == "ok" and not saw:
                    raise ConflictError(
                        "本页已显示模型建议；请勾选“我看过模型建议”，"
                        "记录将标为 human_assisted（现有 Gold/κ 工具会拒绝该记录）"
                    )
                method = "human_assisted" if saw else "human"
                model = self.bridge.model if saw and status == "ok" else None
                model_label = (state.get("advice") or {}).get("label") if saw and status == "ok" else None
            record = self.store.save(
                post_id,
                payload,
                annotation_method=method,
                saw_model_advice=saw,
                model_advice_status=status,
                model=model,
                model_advice_label=model_label,
            )
        return {"ok": True, "annotation": record, "progress": self.store.stats()}

    def set_auto_suggest(self, body: Dict[str, Any]) -> Dict[str, Any]:
        if "auto_suggest" not in body:
            raise ValidationError("请求体必须包含 auto_suggest 布尔值")
        enabled = bool(body.get("auto_suggest"))
        if enabled and not self.bridge.enabled:
            raise WorkbenchError(
                "本次启动使用了 --no-auto-suggest，不能在本会话中重新开启模型建议；"
                "如需模型辅助，请关闭窗口后去掉该参数重新启动。"
            )
        with self._lock:
            self.auto_suggest = enabled
            if not enabled:
                # Do not keep a stale suggestion that could be mistaken for a
                # blind-mode view after re-enabling advice.
                self.advice.clear()
        return {
            "ok": True,
            "auto_suggest": self.auto_suggest,
            "blind_mode": not self.auto_suggest,
        }

    def suggest(self, body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.auto_suggest:
            raise AdviceDisabled("已关闭自动建议（盲标模式）；不会调用 Ollama。")
        post_id = body.get("post_id")
        if not isinstance(post_id, str) or post_id not in self.store.prepared.by_id:
            raise NotFoundError("post_id 不在当前批次")
        post = self.store.prepared.by_id[post_id]
        collection = display_post(post, self.store.spec.media_root, 0)["collection_complete"]
        with self._lock:
            self.advice[post_id] = {"status": "loading"}
        try:
            result = self.bridge.suggest(post, collection_complete=collection)
        except AdviceDisabled:
            with self._lock:
                self.advice[post_id] = {"status": "error", "error": "已关闭自动建议", "elapsed_ms": 0}
            raise
        except AdviceError as exc:
            with self._lock:
                self.advice[post_id] = {
                    "status": "error",
                    "error": str(exc),
                    "elapsed_ms": exc.elapsed_ms,
                }
            raise
        except Exception as exc:  # noqa: BLE001 - visible failure, never a fallback
            message = f"{type(exc).__name__}: {' '.join(str(exc).split())[:800]}"
            with self._lock:
                self.advice[post_id] = {"status": "error", "error": message, "elapsed_ms": 0}
            raise AdviceError(message) from None
        payload = result.to_dict()
        with self._lock:
            self.advice[post_id] = {"status": "ok", "advice": payload}
        return {"ok": True, "advice": payload}

    def export_records(self) -> Tuple[list, Dict[str, Any]]:
        records = self.store.export_records()
        meta = {
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "dataset_id": self.store.spec.dataset_id,
            "batch_id": self.store.spec.batch_id,
            "annotator_id": self.store.spec.annotator_id,
            "guide_version": self.store.spec.guide_version,
            "manifest_role": self.store.spec.manifest_role,
            "formal_gold_allowed": self.store.prepared.formal_gold_allowed,
            "count": len(records),
            "annotation_method_notice": (
                "annotation_method=human_assisted 的记录表示标注者看过模型建议；"
                "现有 build_gold_dataset.py / calculate_agreement.py 会把它们排除"
                "（non_human_method），不能当作独立盲标或正式 Gold。"
            ),
        }
        return records, meta

    def media(self, query: Dict[str, list]) -> Tuple[Path, str]:
        post_id = (query.get("post_id") or [""])[0]
        if not post_id or post_id not in self.store.prepared.by_id:
            raise NotFoundError("post_id 不在当前批次")
        raw_index = (query.get("i") or ["0"])[0]
        try:
            index = int(raw_index)
        except ValueError as exc:
            raise NotFoundError("媒体序号必须是整数") from exc
        post = self.store.prepared.by_id[post_id]
        entry = next((item for item in media_view(post, self.store.spec.media_root) if item["index"] == index), None)
        if entry is None:
            raise NotFoundError("媒体序号不存在")
        if entry["status"] == "outside":
            raise PermissionError(entry.get("reason") or "媒体路径越界")
        if entry["status"] != "ok":
            raise NotFoundError(entry.get("label") or "媒体缺失")
        try:
            path = resolve_media_path(self.store.spec.media_root, (post.get("media") or [])[index].get("ref"))
        except (ValueError, FileNotFoundError, IndexError) as exc:
            raise PermissionError(str(exc)) from exc
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return path, mime


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, handler_class, app: WorkbenchApp):
        self.app = app
        super().__init__(address, handler_class)


def make_handler(app: WorkbenchApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RecessiveAnnotationWorkbench/0.1"
        protocol_version = "HTTP/1.1"

        # ---- low-level helpers -----------------------------------
        def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
            # Keep the console readable; errors are sent to the browser.
            return

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").strip()
            if not host:
                return False
            try:
                name = (urlparse("//" + host).hostname or "").lower()
            except ValueError:
                return False
            return name in {"127.0.0.1", "localhost", "::1"}

        def _token_ok(self, query: Dict[str, list]) -> bool:
            supplied = (query.get("token") or [""])[0] or self.headers.get("X-Workbench-Token") or ""
            return secrets.compare_digest(str(supplied), app.token)

        def _send(self, status: int, body: bytes, content_type: str, extra: Optional[Dict[str, str]] = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; media-src 'self'; "
                "style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
            )
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload: Any, extra: Optional[Dict[str, str]] = None):
            body = json.dumps(payload, ensure_ascii=False, indent=None).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8", extra)

        def _error(self, status: int, message: str, *, code: Optional[str] = None, **extra):
            payload = {"error": message}
            if code:
                payload["code"] = code
            payload.update(extra)
            self._json(status, payload)

        def _query(self) -> Dict[str, list]:
            return parse_qs(urlparse(self.path).query, keep_blank_values=True)

        def _read_json(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError as exc:
                raise ValidationError("Content-Length 无效") from exc
            if length <= 0 or length > MAX_BODY:
                raise ValidationError("请求体为空或过大")
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError("请求体必须是 UTF-8 JSON") from exc
            if not isinstance(body, dict):
                raise ValidationError("请求体必须是 JSON 对象")
            return body

        # ---- HTTP verbs ------------------------------------------
        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                self._error(HTTPStatus.FORBIDDEN, "Host 必须是 127.0.0.1/localhost")
                return
            parsed = urlparse(self.path)
            query = self._query()
            path = parsed.path
            if path == "/favicon.ico":
                self._send(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
                return
            if path.startswith("/api/") or path == "/media":
                if not self._token_ok(query):
                    self._error(HTTPStatus.FORBIDDEN, "缺少或错误的本地访问 token；请从启动 URL 打开")
                    return
            try:
                if path == "/api/state":
                    self._json(200, app.state_payload())
                elif path == "/api/index":
                    self._json(200, app.index_payload())
                elif path == "/api/post":
                    index = int((query.get("index") or ["0"])[0])
                    self._json(200, app.post_payload(index))
                elif path == "/api/export":
                    fmt = (query.get("format") or ["json"])[0].lower()
                    records, meta = app.export_records()
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = f"workbench_{app.store.spec.dataset_id}_{app.store.spec.batch_id}_{app.store.spec.annotator_id}_{stamp}"
                    if fmt == "jsonl":
                        body = "".join(
                            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                            for record in records
                        ).encode("utf-8")
                        self._send(
                            200, body, "application/x-ndjson; charset=utf-8",
                            {"Content-Disposition": f'attachment; filename="{stem}.jsonl"'},
                        )
                    elif fmt == "json":
                        payload = dict(meta, annotations=records)
                        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
                        self._send(
                            200, body, "application/json; charset=utf-8",
                            {"Content-Disposition": f'attachment; filename="{stem}.json"'},
                        )
                    else:
                        self._error(HTTPStatus.BAD_REQUEST, "format 必须是 json 或 jsonl")
                elif path == "/media":
                    media_path, mime = app.media(query)
                    data = media_path.read_bytes()
                    self._send(200, data, mime, {"Content-Disposition": "inline"})
                else:
                    self._serve_static(path)
            except NotFoundError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            except PermissionError as exc:
                self._error(HTTPStatus.FORBIDDEN, str(exc), code="media_outside")
            except (ValueError, WorkbenchError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # noqa: BLE001
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"内部错误：{type(exc).__name__}: {exc}")

        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                self._error(HTTPStatus.FORBIDDEN, "Host 必须是 127.0.0.1/localhost")
                return
            parsed = urlparse(self.path)
            query = self._query()
            if not self._token_ok(query):
                self._error(HTTPStatus.FORBIDDEN, "缺少或错误的本地访问 token；请从启动 URL 打开")
                return
            try:
                body = self._read_json()
                if parsed.path == "/api/annotation":
                    self._json(200, app.save_annotation(body))
                elif parsed.path == "/api/settings":
                    self._json(200, app.set_auto_suggest(body))
                elif parsed.path == "/api/suggest":
                    self._json(200, app.suggest(body))
                else:
                    self._error(HTTPStatus.NOT_FOUND, "未知接口")
            except AdviceDisabled as exc:
                self._error(HTTPStatus.FORBIDDEN, str(exc), code="blind_mode")
            except AdviceError as exc:
                self._error(
                    HTTPStatus.BAD_GATEWAY, str(exc), code="ollama_error",
                    elapsed_ms=exc.elapsed_ms,
                )
            except ConflictError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc), code="advice_conflict")
            except NotFoundError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            except ValidationError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except WorkbenchError as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:  # noqa: BLE001
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"内部错误：{type(exc).__name__}: {exc}")

        def do_HEAD(self):  # noqa: N802
            self.do_GET()

        # ---- static files ---------------------------------------
        def _serve_static(self, path: str) -> None:
            if path in {"", "/"}:
                relative = "index.html"
            else:
                relative = path.lstrip("/")
            candidate = (STATIC_DIR / relative).resolve()
            try:
                candidate.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._error(HTTPStatus.FORBIDDEN, "静态资源路径越界")
                return
            if not candidate.is_file():
                self._error(HTTPStatus.NOT_FOUND, "页面资源不存在")
                return
            mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            data = candidate.read_bytes()
            self._send(200, data, mime)

    return Handler


def create_server(app: WorkbenchApp, host: str = "127.0.0.1", port: int = 8765) -> WorkbenchHTTPServer:
    if host != "127.0.0.1":
        raise WorkbenchError("工作台只允许绑定 127.0.0.1")
    return WorkbenchHTTPServer((host, port), make_handler(app), app)


def run_server(app: WorkbenchApp, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_server(app, host=host, port=port)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/?token={quote(app.token, safe='')}"
    _print_url(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止工作台…")
    finally:
        server.server_close()
        app.store.close()

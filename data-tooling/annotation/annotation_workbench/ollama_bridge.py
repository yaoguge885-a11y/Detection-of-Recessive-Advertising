"""Thin bridge between the workbench and the existing ``auto_judge`` module.

Only a single post is sent per request.  The bridge never keeps conversation
history, never calls keyword fallback, and never writes a suggestion to disk.
Any failure is surfaced to the browser as an explicit error.
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# ``data-tooling/annotation`` is not a Python package path, so make the sibling
# module importable both when running the entry point and when running pytest.
_ANNOTATION_DIR = Path(__file__).resolve().parent.parent
if str(_ANNOTATION_DIR) not in sys.path:
    sys.path.insert(0, str(_ANNOTATION_DIR))

import auto_judge  # noqa: E402  (path set up above)

from .store import DEFAULT_GUIDE_VERSION, WorkbenchError, sha256_text  # noqa: E402


class AdviceDisabled(WorkbenchError):
    """Raised when blind mode has explicitly disabled model suggestions."""


class AdviceError(WorkbenchError):
    """A visible model-suggestion failure; never converted into a label."""

    def __init__(self, message: str, *, elapsed_ms: int = 0):
        super().__init__(message)
        self.elapsed_ms = elapsed_ms


@dataclass
class AdviceResult:
    label: str
    confidence: float
    evidence_codes: list
    evidence: list
    reasoning: str
    uncertain_reason: Optional[str]
    information_gaps: list
    model: str
    latency_ms: int
    guide_version: str
    guide_sha256: str
    collection_complete: Optional[str] = None
    media_evidence_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _is_loopback_host(host: Optional[str]) -> bool:
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in {"localhost", "::1"}:
        return True
    if host.startswith("127."):
        return True
    return False


def validate_ollama_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WorkbenchError("Ollama URL 必须使用 http:// 或 https://")
    if not _is_loopback_host(parsed.hostname):
        raise WorkbenchError(
            f"Ollama URL 必须指向本机回环地址（127.0.0.1/localhost/::1），收到 {parsed.hostname!r}；"
            "为避免把真实帖文发送到外部服务，已拒绝。"
        )
    return url.rstrip("/")


def _guide_version(text: str) -> str:
    match = re.search(r"(?:版本|version|guide_version)\s*[:：]?\s*v?(\d+(?:\.\d+)*)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"v(\d+(?:\.\d+)*)", text[:2000])
    return match.group(1) if match else DEFAULT_GUIDE_VERSION


def _safe_error(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    if len(text) > 900:
        text = text[:900] + "…"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


class OllamaBridge:
    def __init__(
        self,
        *,
        model: str = "qwen3.5:9b",
        url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        guide_path: Path,
        num_predict: int = 1536,
        comment_limit: int = 30,
        enabled: bool = True,
    ):
        self.model = model
        self.url = validate_ollama_url(url)
        self.timeout = float(timeout)
        self.enabled = bool(enabled)
        self.num_predict = int(num_predict)
        self.comment_limit = int(comment_limit)
        raw = guide_path.read_bytes()
        self.guide_text = raw.decode("utf-8-sig")
        self.guide_sha256 = sha256_text(self.guide_text)
        self.guide_version = _guide_version(self.guide_text)

    def suggest(self, post: Dict[str, Any], *, collection_complete: Optional[str] = None) -> AdviceResult:
        if not self.enabled:
            raise AdviceDisabled("已关闭自动建议（盲标模式）；本工作台不会调用 Ollama。")
        started = time.monotonic()
        collection_value: Optional[bool]
        if collection_complete == "complete":
            collection_value = True
        elif collection_complete == "incomplete":
            collection_value = False
        else:
            collection_value = None
        image_analyses = post.get("image_analyses")
        if not isinstance(image_analyses, dict):
            image_analyses = None
        try:
            suggestion = auto_judge.run_ollama_judge(
                post,
                image_analyses=image_analyses,
                model=self.model,
                url=self.url,
                timeout=self.timeout,
                guide_text=self.guide_text,
                guide_version=self.guide_version,
                guide_sha256=self.guide_sha256,
                collection_complete=collection_value,
                num_predict=self.num_predict,
                thinking=False,
                comment_limit=self.comment_limit,
                keep_alive="30m",
            )
        except Exception as exc:  # noqa: BLE001 - turned into a visible error
            elapsed = int((time.monotonic() - started) * 1000)
            raise AdviceError(_safe_error(exc), elapsed_ms=elapsed) from None
        elapsed = int((time.monotonic() - started) * 1000)
        if not isinstance(suggestion, dict) or not suggestion.get("label"):
            raise AdviceError("Ollama 返回了空结果或缺少 label", elapsed_ms=elapsed)
        label = str(suggestion.get("label") or "")
        if label not in {"明广", "暗广", "非广", "uncertain", "out_of_scope"}:
            raise AdviceError(f"Ollama 返回了不支持的标签：{label!r}", elapsed_ms=elapsed)
        try:
            confidence = float(suggestion.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        evidence = suggestion.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        codes = suggestion.get("evidence_codes") or []
        if isinstance(codes, str):
            codes = [codes]
        gaps = suggestion.get("information_gaps") or []
        if isinstance(gaps, str):
            gaps = [gaps]
        return AdviceResult(
            label=label,
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            evidence_codes=[str(item) for item in codes],
            evidence=[str(item) for item in evidence],
            reasoning=str(suggestion.get("reasoning") or ""),
            uncertain_reason=(
                str(suggestion.get("uncertain_reason")) if suggestion.get("uncertain_reason") else None
            ),
            information_gaps=[str(item) for item in gaps],
            model=str(suggestion.get("_model") or self.model),
            latency_ms=elapsed,
            guide_version=self.guide_version,
            guide_sha256=self.guide_sha256,
            collection_complete=(
                str(suggestion.get("_collection_complete"))
                if suggestion.get("_collection_complete") is not None else None
            ),
            media_evidence_status=(
                str(suggestion.get("_media_evidence_status"))
                if suggestion.get("_media_evidence_status") is not None else None
            ),
        )

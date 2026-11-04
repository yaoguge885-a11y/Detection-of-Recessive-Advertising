"""Offline suggestion source backed by a pre-computed ``suggest_*.jsonl`` file.

Batch pre-annotation (``batch_pre_annotate.py``) can take hours on a local
model. This source lets the workbench show those suggestions without calling
Ollama at review time, so a human reviews at their own pace instead of waiting
for one inference per item.

The interface matches :class:`OllamaBridge`: ``model``/``url``/``enabled``
attributes plus ``suggest(post, collection_complete=...)`` returning
``AdviceResult``. Suggestions are never invented: a post without a
pre-computed entry raises :class:`AdviceError`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .ollama_bridge import AdviceError, AdviceResult, _guide_version
from .store import sha256_text

VALID_LABELS = {"明广", "暗广", "非广", "uncertain", "out_of_scope"}


class FileSuggestionSource:
    def __init__(
        self,
        *,
        suggestion_path,
        guide_path,
        model: str = "",
    ):
        path = Path(suggestion_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"建议文件不存在：{path}")
        self.path = path
        self.url = ""
        self.enabled = True
        guide_text = Path(guide_path).read_bytes().decode("utf-8-sig")
        self.guide_text = guide_text
        self.guide_sha256 = sha256_text(guide_text)
        self.guide_version = _guide_version(guide_text)

        by_post: Dict[str, Dict[str, Any]] = {}
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                post_id = record.get("post_id")
                suggestion = record.get("suggestion")
                if isinstance(post_id, str) and post_id and isinstance(suggestion, dict):
                    by_post[post_id] = record
        if not by_post:
            raise ValueError(f"建议文件没有可用记录：{path}")
        self._by_post = by_post

        if model:
            self.model = model
        else:
            models = sorted(
                {
                    str((record.get("suggestion") or {}).get("_model") or "")
                    for record in by_post.values()
                }
                - {""}
            )
            self.model = models[0] if models else "precomputed_suggestion"

    @property
    def covered_post_ids(self):
        return set(self._by_post)

    def suggest(
        self, post: Dict[str, Any], *, collection_complete: Optional[str] = None
    ) -> AdviceResult:
        post_id = post.get("post_id")
        record = self._by_post.get(post_id) if isinstance(post_id, str) else None
        if record is None:
            raise AdviceError(
                "预计算建议中没有该 post_id；请先运行批量预标注，或对该条改用人工判断。"
            )
        suggestion = record.get("suggestion") or {}
        label = str(suggestion.get("label") or "")
        if label not in VALID_LABELS:
            raise AdviceError(f"预计算建议的标签不受支持：{label!r}")
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
        uncertain_reason = suggestion.get("uncertain_reason")
        return AdviceResult(
            label=label,
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            evidence_codes=[str(item) for item in codes],
            evidence=[str(item) for item in evidence],
            reasoning=str(suggestion.get("reasoning") or ""),
            uncertain_reason=str(uncertain_reason) if uncertain_reason else None,
            information_gaps=[str(item) for item in gaps],
            model=str(suggestion.get("_model") or self.model),
            latency_ms=0,
            guide_version=str(record.get("guide_version") or self.guide_version),
            guide_sha256=self.guide_sha256,
            collection_complete=collection_complete,
            media_evidence_status=(str(suggestion.get("_media_evidence_status") or "") or None),
        )

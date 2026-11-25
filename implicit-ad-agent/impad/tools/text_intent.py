"""Commercial intent with an optional local trained model and rule fallback."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from pydantic import Field

from ..config import settings
from .contracts import StrictToolInput, ToolEvidence, ToolResult
from .disclosure import disclosure_evidence
from .keywords import (SOFT_AD_SIGNALS, ad_pressure, compute_keyword_weights,
                       keyword_hits)
from .text_classifier import predict_commercial_intent


class TextIntentInput(StrictToolInput):
    text: str = Field(min_length=1)
    comments: list[str] = Field(default_factory=list)
    language: str = "zh"


class TextIntentResult(ToolResult):
    tool_name: Literal["analyze_text_intent"] = "analyze_text_intent"


def _spans(text: str, words: list[str], kind: str) -> list[ToolEvidence]:
    evidence = []
    for word in words:
        start = text.find(word)
        if start >= 0:
            evidence.append(ToolEvidence(kind=kind, source="post.text", quote=word,
                                         span=(start, start + len(word))))
    return evidence


def _analyze_text_intent_core(inp: TextIntentInput) -> TextIntentResult:
    weights = compute_keyword_weights(inp.text)
    hits = keyword_hits(inp.text)
    disclosure = disclosure_evidence(inp.text, source="post.text")
    explicit = [
        item.quote
        for item in disclosure
        if item.kind == "explicit_ad_marker" and item.quote
    ]
    soft = [word for word in SOFT_AD_SIGNALS if word in inp.text]
    pressure = ad_pressure(weights)
    score = min(1.0, round(max(pressure, 0.75 if explicit else 0,
                               0.45 + 0.08 * len(soft) if soft else 0), 2))
    patterns = [name for name, values in hits.items() if values and name != "natural_expression"]
    evidence = disclosure
    evidence += _spans(inp.text, soft, "soft_ad_signal")
    for name, values in hits.items():
        evidence += _spans(inp.text, values, f"keyword:{name}")
    # Deduplicate overlapping sources while preserving deterministic order.
    unique = list({(e.kind, e.quote, e.span): e for e in evidence}.values())
    if not unique:
        unique = [ToolEvidence(kind="absence", source="post.text", quote=inp.text[:80], score=0)]
    rule_score = score
    classifier_score = None
    status = "degraded"
    model_info = "rule_v2"
    warnings = ["LLM intent model not invoked; deterministic rule_v2 result."]
    if settings.text_intent_model_path:
        try:
            candidate_score = predict_commercial_intent(
                inp.text, settings.text_intent_model_path,
                positive_label_id=int(settings.text_intent_positive_label_id),
            )
            if not math.isfinite(candidate_score) or not 0 <= candidate_score <= 1:
                raise ValueError("Invalid classifier probability")
            classifier_score = candidate_score
            score = max(classifier_score, 0.75 if explicit else 0.0)
            status = "ok"
            model_info = "local_sequence_classifier:" + Path(settings.text_intent_model_path).name
            warnings = []
            unique.append(ToolEvidence(
                kind="commercial_intent_prediction", source="post.text",
                score=classifier_score,
            ))
        except Exception as exc:
            warnings.append(
                f"Local intent classifier unavailable ({type(exc).__name__}); using rule_v2."
            )
    return TextIntentResult(
        status=status, score=score, evidence=unique,
        warnings=warnings, model_info=model_info,
        payload={"commercial_intent_score": score, "persuasion_patterns": patterns,
                 "rule_score": rule_score, "classifier_score": classifier_score,
                 "keyword_weights": weights,
                 "matched_spans": [e.model_dump() for e in unique if e.span],
                 "summary": "检测到商业导购信号" if score >= 0.5 else "未检测到显著商业导购信号"},
    )


@tool(args_schema=TextIntentInput)
def analyze_text_intent(text: str, comments: list[str] | None = None,
                        language: str = "zh") -> dict:
    """分析帖子商业意图与劝服话术，返回分数及可回指原文的证据。"""
    return _analyze_text_intent_core(
        TextIntentInput(text=text, comments=comments or [], language=language)
    ).model_dump(mode="json")


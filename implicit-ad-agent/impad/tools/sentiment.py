"""Deterministic sentiment, anxiety and urgency curve tool."""
from __future__ import annotations

from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .contracts import ToolEvidence, ToolResult
from .keywords import URGENCY_WORDS

POSITIVE = ("开心", "喜欢", "满意", "好用", "惊喜", "幸福", "赞")
NEGATIVE = ("难过", "失望", "生气", "糟糕", "讨厌", "焦虑", "害怕")
ANXIETY = ("焦虑", "害怕", "后悔", "错过", "容貌", "衰老", "健康", "脱发")


class HistoryText(BaseModel):
    post_id: str
    text: str
    published_at: str | None = None


class SentimentCurveInput(BaseModel):
    text: str = Field(min_length=1)
    history: list[HistoryText] = Field(default_factory=list)


class SentimentCurveResult(ToolResult):
    tool_name: Literal["sentiment_curve"] = "sentiment_curve"


def _point(text: str) -> dict:
    pos = sum(word in text for word in POSITIVE)
    neg = sum(word in text for word in NEGATIVE)
    anxiety = min(1.0, sum(word in text for word in ANXIETY) / 3)
    urgency = min(1.0, sum(word in text for word in URGENCY_WORDS) / 3)
    label = "positive" if pos > neg else "negative" if neg > pos else "neutral"
    return {"sentiment": label, "positive_score": round(pos / max(pos + neg, 1), 2),
            "negative_score": round(neg / max(pos + neg, 1), 2),
            "anxiety_score": round(anxiety, 2), "urgency_score": round(urgency, 2)}


def _sentiment_curve_core(inp: SentimentCurveInput) -> SentimentCurveResult:
    ordered = sorted(inp.history, key=lambda item: item.published_at or "")
    items = [(item.post_id, item.text, item.published_at) for item in ordered]
    items.append(("current", inp.text, None))
    points = [{"post_id": post_id, "published_at": when, **_point(text)}
              for post_id, text, when in items]
    current = points[-1]
    intensity = round(max(current["anxiety_score"], current["urgency_score"]), 2)
    changes = []
    for previous, point in zip(points, points[1:]):
        before = max(previous["anxiety_score"], previous["urgency_score"])
        after = max(point["anxiety_score"], point["urgency_score"])
        if abs(after - before) >= 0.5:
            changes.append({"post_id": point["post_id"], "delta": round(after - before, 2)})
    matched = [word for word in (*ANXIETY, *URGENCY_WORDS) if word in inp.text]
    evidence = [ToolEvidence(kind="emotion_signal", source="post.text", quote=word)
                for word in matched]
    if not evidence:
        evidence = [ToolEvidence(kind="current_sentiment", source="post.text",
                                 quote=inp.text[:80], score=intensity)]
    warnings = ["Rule-based sentiment model used; replaceable through the stable contract."]
    if len(inp.history) < 3:
        warnings.append("Fewer than 3 history posts; curve change evidence is limited.")
        changes = []
    return SentimentCurveResult(
        status="degraded", score=intensity, evidence=evidence, warnings=warnings,
        model_info="rule_v1",
        payload={"current_sentiment": current["sentiment"],
                 "current_sentiment_scores": {"positive": current["positive_score"],
                                                "negative": current["negative_score"]},
                 "anxiety_score": current["anxiety_score"],
                 "urgency_score": current["urgency_score"],
                 "curve_points": points, "change_points": changes},
    )


@tool(args_schema=SentimentCurveInput)
def sentiment_curve(text: str, history: list[dict] | None = None) -> dict:
    """分析当前帖的焦虑/紧迫情绪，并在历史充分时返回情绪突变曲线。"""
    return _sentiment_curve_core(
        SentimentCurveInput(text=text, history=history or [])
    ).model_dump(mode="json")


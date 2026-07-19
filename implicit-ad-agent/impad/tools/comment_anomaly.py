"""Explainable rule-based comment anomaly tool."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .contracts import ToolEvidence, ToolResult

PRAISE = ("太好用了", "已下单", "求链接", "在哪里买", "必须买", "效果真好", "推荐")


class CommentItem(BaseModel):
    comment_id: str
    text: str
    created_at: str | None = None
    author_id: str | None = None
    like_count: int = 0
    is_pinned: bool = False


class CommentAnomalyInput(BaseModel):
    comments: list[CommentItem] = Field(default_factory=list)


class CommentAnomalyResult(ToolResult):
    tool_name: Literal["comment_anomaly"] = "comment_anomaly"


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower())


def _comment_anomaly_core(inp: CommentAnomalyInput) -> CommentAnomalyResult:
    if len(inp.comments) < 5:
        return CommentAnomalyResult(
            status="skipped", score=None,
            warnings=["At least 5 comments are required; 0 is not used as normal evidence."],
            model_info="rule_v1", payload={"anomaly_score": None, "signals": []})
    normalized = [_normalize(item.text) for item in inp.comments]
    counts = Counter(normalized)
    duplicate_ids = [item.comment_id for item, text in zip(inp.comments, normalized)
                     if text and counts[text] > 1]
    duplicate_ratio = len(duplicate_ids) / len(inp.comments)
    praise_ids = [item.comment_id for item in inp.comments if any(word in item.text for word in PRAISE)]
    praise_score = len(praise_ids) / len(inp.comments)
    burst_score = None
    timed = []
    for item in inp.comments:
        if item.created_at:
            try:
                timed.append((item.comment_id, datetime.fromisoformat(item.created_at.replace("Z", "+00:00"))))
            except ValueError:
                pass
    burst_ids: list[str] = []
    if len(timed) >= 3:
        timed.sort(key=lambda value: value[1])
        span = (timed[-1][1] - timed[0][1]).total_seconds()
        burst_score = 1.0 if span <= 300 else 0.5 if span <= 1800 else 0.0
        if burst_score:
            burst_ids = [item_id for item_id, _ in timed]
    components = [duplicate_ratio, praise_score]
    if burst_score is not None:
        components.append(burst_score)
    score = round(sum(components) / len(components), 2)
    suspicious = list(dict.fromkeys(duplicate_ids + praise_ids + burst_ids))
    evidence = [ToolEvidence(kind="comment_anomaly", source="post.comments",
                             quote="重复、模板化赞美或短时突发评论", score=score,
                             comment_ids=suspicious)]
    signals = []
    if duplicate_ids:
        signals.append("duplicate_comments")
    if praise_ids:
        signals.append("praise_templates")
    if burst_ids:
        signals.append("short_time_burst")
    warnings = [] if burst_score is not None else ["Timestamps insufficient; burst feature skipped."]
    return CommentAnomalyResult(
        status="ok", score=score, evidence=evidence, warnings=warnings, model_info="rule_v1",
        payload={"anomaly_score": score, "duplicate_ratio": round(duplicate_ratio, 2),
                 "burst_score": burst_score, "praise_template_score": round(praise_score, 2),
                 "suspicious_comment_ids": suspicious, "signals": signals})


@tool(args_schema=CommentAnomalyInput)
def comment_anomaly(comments: list[dict]) -> dict:
    """检测评论复制、模板化赞美和短时突发，返回可追溯评论 ID。"""
    return _comment_anomaly_core(CommentAnomalyInput(comments=comments)).model_dump(mode="json")


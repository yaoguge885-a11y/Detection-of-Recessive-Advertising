"""Topic drift tool with a local character n-gram fallback."""
from __future__ import annotations

import math
from collections import Counter
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .contracts import ToolEvidence, ToolResult


class TopicPost(BaseModel):
    post_id: str
    text: str
    published_at: str | None = None


class TopicDriftInput(BaseModel):
    post_id: str
    text: str = Field(min_length=1)
    published_at: str | None = None
    history: list[TopicPost] = Field(default_factory=list)
    window_size: int = Field(default=20, ge=3, le=200)


class TopicDriftResult(ToolResult):
    tool_name: Literal["topic_drift"] = "topic_drift"


def _ngrams(text: str) -> Counter[str]:
    cleaned = "".join(text.lower().split())
    return Counter(cleaned[i:i + 2] for i in range(max(0, len(cleaned) - 1)))


def _similarity(left: str, right: str) -> float:
    a, b = _ngrams(left), _ngrams(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    norm = math.sqrt(sum(v * v for v in a.values()) * sum(v * v for v in b.values()))
    return dot / norm if norm else 0.0


def _topic_drift_core(inp: TopicDriftInput) -> TopicDriftResult:
    history = [item for item in inp.history
               if not inp.published_at or not item.published_at or item.published_at < inp.published_at]
    history = history[-inp.window_size:]
    if len(history) < 3:
        return TopicDriftResult(
            status="skipped", score=None,
            warnings=["At least 3 prior history posts are required; 0 is not used as no-drift evidence."],
            model_info="char_bigram_rule_v1",
            payload={"drift_score": None, "current_topic": inp.text[:40],
                     "history_profile": "", "nearest_posts": [],
                     "distance_details": {"valid_history_count": len(history)}},
        )
    similarities = [(item, _similarity(inp.text, item.text)) for item in history]
    similarities.sort(key=lambda pair: pair[1], reverse=True)
    nearest = similarities[:3]
    mean_similarity = sum(score for _, score in similarities) / len(similarities)
    nearest_similarity = nearest[0][1]
    drift = round(1 - (0.6 * mean_similarity + 0.4 * nearest_similarity), 2)
    evidence = [ToolEvidence(kind="nearest_history", source="blogger.history",
                             quote=item.text[:80], score=round(score, 2),
                             related_post_id=item.post_id)
                for item, score in nearest]
    return TopicDriftResult(
        status="degraded", score=drift, evidence=evidence,
        warnings=["Local character-bigram similarity used; BGE embedding is the planned primary model."],
        model_info="char_bigram_rule_v1",
        payload={"drift_score": drift, "current_topic": inp.text[:40],
                 "history_profile": " / ".join(item.text[:24] for item in history[:5]),
                 "nearest_posts": [{"post_id": item.post_id, "similarity": round(score, 2)}
                                   for item, score in nearest],
                 "distance_details": {"mean_similarity": round(mean_similarity, 2),
                                      "nearest_similarity": round(nearest_similarity, 2),
                                      "window_size": len(history), "future_posts_filtered": len(inp.history) - len(history)}},
    )


@tool(args_schema=TopicDriftInput)
def topic_drift(post_id: str, text: str, history: list[dict] | None = None,
                published_at: str | None = None, window_size: int = 20) -> dict:
    """比较当前帖与同博主先前发文，返回主题漂移分和最近历史证据。"""
    return _topic_drift_core(TopicDriftInput(
        post_id=post_id, text=text, history=history or [], published_at=published_at,
        window_size=window_size)).model_dump(mode="json")


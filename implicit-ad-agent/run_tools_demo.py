"""Zero-key P2 demo: invoke every ready L-owned tool independently."""
from __future__ import annotations

import json
import sys

from impad.tools.comment_anomaly import comment_anomaly
from impad.tools.sentiment import sentiment_curve
from impad.tools.text_intent import analyze_text_intent
from impad.tools.topic_drift import topic_drift

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    history = [
        {"post_id": "h1", "text": "今天学习 Python 编程", "published_at": "2026-07-01"},
        {"post_id": "h2", "text": "分享代码练习心得", "published_at": "2026-07-02"},
        {"post_id": "h3", "text": "整理 Python 学习笔记", "published_at": "2026-07-03"},
    ]
    text = "亲测这款面霜太好用，限时优惠，链接在评论区"
    comments = [
        {"comment_id": str(i), "text": "太好用了，已下单", "created_at": f"2026-07-04T10:0{i}:00"}
        for i in range(5)
    ]
    outputs = {
        "analyze_text_intent": analyze_text_intent.invoke({"text": text}),
        "sentiment_curve": sentiment_curve.invoke({"text": text, "history": history}),
        "topic_drift": topic_drift.invoke({
            "post_id": "current", "text": text, "published_at": "2026-07-04", "history": history}),
        "comment_anomaly": comment_anomaly.invoke({"comments": comments}),
    }
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


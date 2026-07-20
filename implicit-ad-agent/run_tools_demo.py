"""Zero-key P2 demo: invoke all seven tools independently."""
from __future__ import annotations

import json
import sys

from impad.tools.comment_anomaly import comment_anomaly
from impad.tools.detect_logo_product import detect_logo_product
from impad.tools.image_text_consistency import image_text_consistency
from impad.tools.ocr_extract import ocr_extract
from impad.tools.sentiment import sentiment_curve
from impad.tools.text_intent import analyze_text_intent
from impad.tools.topic_drift import topic_drift
from impad.tools.vision_context import VisionContext

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
    # Production callers build this context once from a real local image_path.
    vision_context = VisionContext.model_validate({
        "image_id": "sha256:demo",
        "image_name": "demo-product.jpg",
        "objects": [{"class_name": "bottle", "confidence": 0.91,
                     "bbox": [10, 20, 180, 300], "center": [95, 160]}],
        "texts": [{"text": "面霜限时优惠 ￥99", "confidence": 0.93,
                   "bbox": [20, 30, 160, 70]}],
        "focus": {"focus_point": [95, 160], "confidence": 0.91,
                  "method": "weighted_center", "num_objects": 1},
        "model_version": "synthetic-demo-v1",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    }).model_dump(mode="json")
    outputs = {
        "analyze_text_intent": analyze_text_intent.invoke({"text": text}),
        "sentiment_curve": sentiment_curve.invoke({"text": text, "history": history}),
        "topic_drift": topic_drift.invoke({
            "post_id": "current", "text": text, "published_at": "2026-07-04", "history": history}),
        "comment_anomaly": comment_anomaly.invoke({"comments": comments}),
        "ocr_extract": ocr_extract.invoke({
            "image_path": "demo-product.jpg", "vision_context": vision_context,
            "detect_qr": False}),
        "detect_logo_product": detect_logo_product.invoke({
            "image_path": "demo-product.jpg", "vision_context": vision_context}),
        "image_text_consistency": image_text_consistency.invoke({
            "text": text, "image_path": "demo-product.jpg",
            "vision_context": vision_context}),
    }
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


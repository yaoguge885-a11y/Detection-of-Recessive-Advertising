"""Zero-key P2 demo: read one de-identified post and invoke all seven tools."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from impad.tools.comment_anomaly import comment_anomaly
from impad.tools.detect_logo_product import detect_logo_product
from impad.tools.image_text_consistency import image_text_consistency
from impad.tools.ocr_extract import ocr_extract
from impad.tools.sentiment import sentiment_curve
from impad.tools.text_intent import analyze_text_intent
from impad.tools.topic_drift import topic_drift
from impad.tools.vision_context import VisionContext, build_vision_context

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SAMPLE = PROJECT_ROOT / "samples" / "tool_demo_post.json"


def _synthetic_context(image_name: str) -> VisionContext:
    """Stable fixture for the default zero-key, zero-model demo."""
    return VisionContext.model_validate({
        "image_id": "sha256:demo",
        "image_name": Path(image_name).name,
        "objects": [{"class_name": "bottle", "confidence": 0.91,
                     "bbox": [10, 20, 180, 300], "center": [95, 160]}],
        "texts": [{"text": "面霜限时优惠 ￥99", "confidence": 0.93,
                   "bbox": [20, 30, 160, 70]}],
        "focus": {"focus_point": [95, 160], "confidence": 0.91,
                  "method": "weighted_center", "num_objects": 1},
        "model_version": "synthetic-demo-v1",
        "capabilities": {"object_detection": True, "ocr": True,
                         "focus": True, "logo_detection": "none"},
    })


def run_tools_demo(
    sample_path: str | Path = DEFAULT_SAMPLE,
    *,
    image_path: str | None = None,
) -> dict:
    """Return all tool outputs for a de-identified sample post.

    Without ``image_path`` the demo injects a deterministic visual fixture.  A
    real local path opts into one installed YOLO/EasyOCR pass shared by all
    three visual tools.
    """
    sample_file = Path(sample_path)
    post = json.loads(sample_file.read_text(encoding="utf-8"))
    text = post["text"]
    history = post.get("blogger_history_refs", [])
    comments = post.get("comments", [])

    if image_path:
        visual_path = str(Path(image_path).resolve())
        context = build_vision_context(visual_path)
        visual_source = f"real:{Path(visual_path).name}"
    else:
        media = post.get("media", [])
        visual_path = media[0]["uri"] if media else "demo-product.jpg"
        context = _synthetic_context(visual_path)
        visual_source = "synthetic_fixture"
    serialized_context = context.model_dump(mode="json")

    outputs = {
        "analyze_text_intent": analyze_text_intent.invoke({"text": text}),
        "sentiment_curve": sentiment_curve.invoke({"text": text, "history": history}),
        "topic_drift": topic_drift.invoke({
            "post_id": post["post_id"], "text": text,
            "published_at": post.get("published_at"), "history": history,
        }),
        "comment_anomaly": comment_anomaly.invoke({"comments": comments}),
        "ocr_extract": ocr_extract.invoke({
            "image_path": visual_path, "vision_context": serialized_context,
            "detect_qr": False,
        }),
        "detect_logo_product": detect_logo_product.invoke({
            "image_path": visual_path, "vision_context": serialized_context,
        }),
        "image_text_consistency": image_text_consistency.invoke({
            "text": text, "image_path": visual_path,
            "vision_context": serialized_context,
        }),
    }
    return {
        "post_id": post["post_id"],
        "visual_source": visual_source,
        "tools": outputs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE),
                        help="de-identified JSON post; defaults to the fixed sample")
    parser.add_argument("--image", help="optional real local image for YOLO/EasyOCR")
    args = parser.parse_args()
    result = run_tools_demo(args.sample, image_path=args.image)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Deterministic image/text consistency fallback using a shared VisionContext."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, field_validator

from .contracts import ToolEvidence, ToolResult
from .vision_context import (
    VisionContext,
    VisionDependencyError,
    resolve_vision_context,
    validate_local_image_path,
)


_OBJECT_TERMS = {
    "person": ("人", "人物", "自拍", "朋友", "男生", "女生"),
    "bottle": ("瓶", "饮料", "水", "酒", "香水", "精华", "乳液"),
    "cup": ("杯", "咖啡", "茶", "饮料"),
    "handbag": ("包", "手袋", "包包"),
    "backpack": ("背包", "书包"),
    "cell phone": ("手机", "电话", "数码"),
    "laptop": ("电脑", "笔记本", "办公"),
    "book": ("书", "阅读", "学习"),
    "clock": ("钟", "表", "时间"),
    "vase": ("花瓶", "鲜花", "花"),
    "wine glass": ("酒杯", "红酒", "酒"),
    "tie": ("领带", "西装"),
    "suitcase": ("行李箱", "旅行", "出差"),
    "dog": ("狗", "小狗", "宠物"),
    "cat": ("猫", "小猫", "宠物"),
    "car": ("车", "汽车", "自驾"),
    "bicycle": ("自行车", "骑行", "单车"),
    "chair": ("椅", "座椅", "家居"),
    "couch": ("沙发", "客厅", "家居"),
    "tv": ("电视", "屏幕"),
}


class ImageTextConsistencyInput(BaseModel):
    text: str
    image_path: str
    vision_context: VisionContext | None = None

    @field_validator("image_path")
    @classmethod
    def local_path_only(cls, value: str) -> str:
        return validate_local_image_path(value)


class ImageTextConsistencyResult(ToolResult):
    tool_name: Literal["image_text_consistency"] = "image_text_consistency"


def _ngrams(text: str) -> Counter[str]:
    cleaned = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", text.lower())
    if not cleaned:
        return Counter()
    if len(cleaned) == 1:
        return Counter([cleaned])
    return Counter(cleaned[index:index + 2] for index in range(len(cleaned) - 1))


def _cosine(left: str, right: str) -> float:
    a, b = _ngrams(left), _ngrams(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    denominator = math.sqrt(sum(value * value for value in a.values()) *
                            sum(value * value for value in b.values()))
    return dot / denominator if denominator else 0.0


def _matched_objects(text: str, context: VisionContext) -> list:
    lowered = text.lower()
    matched = []
    for item in context.objects:
        terms = _OBJECT_TERMS.get(item.class_name, ())
        if item.class_name.lower() in lowered or any(term in text for term in terms):
            matched.append(item)
    return matched


def _empty_result(status: str, warning: str) -> ImageTextConsistencyResult:
    return ImageTextConsistencyResult(
        status=status, score=None, warnings=[warning],
        payload={
            "consistency_score": None,
            "relation": "insufficient",
            "reason": warning,
            "aligned_evidence": [],
            "conflicting_evidence": [],
            "vision_context": None,
        },
    )


def _image_text_consistency_core(
    inp: ImageTextConsistencyInput,
) -> ImageTextConsistencyResult:
    if not inp.text.strip():
        return _empty_result("skipped", "Post text is empty; consistency cannot be assessed.")
    if not inp.image_path:
        return _empty_result("skipped", "A local image_path is required.")
    try:
        context, reused = resolve_vision_context(inp.image_path, inp.vision_context)
    except FileNotFoundError:
        return _empty_result("error", "The local image file does not exist.")
    except VisionDependencyError:
        return _empty_result("skipped", "Local YOLO/OCR dependencies are unavailable.")
    except Exception as exc:
        return _empty_result("error", f"Visual analysis failed safely ({type(exc).__name__}).")

    ocr_text = " ".join(block.text for block in context.texts if block.text.strip())
    matched = _matched_objects(inp.text, context)
    has_ocr = bool(ocr_text)
    has_objects = bool(context.objects)
    if not has_ocr and not has_objects:
        result = _empty_result(
            "skipped", "The image contains no usable OCR text or detected objects."
        )
        result.model_info = context.model_version
        result.payload["context_reused"] = reused
        result.payload["vision_context"] = context.model_dump(mode="json")
        return result

    ocr_similarity = _cosine(inp.text, ocr_text) if has_ocr else None
    object_overlap = len(matched) / len(context.objects) if has_objects else None
    aligned: list[ToolEvidence] = []
    conflicting: list[ToolEvidence] = []

    if has_ocr and ocr_similarity is not None:
        first_bbox = context.texts[0].bbox if context.texts else None
        pointer = ToolEvidence(
            kind="ocr_semantic_overlap", source="post.text<->image.ocr",
            quote=ocr_text[:120], score=round(ocr_similarity, 3), bbox=first_bbox,
        )
        if ocr_similarity >= 0.18:
            aligned.append(pointer)
        elif len(_ngrams(inp.text)) >= 3 and len(_ngrams(ocr_text)) >= 3:
            conflicting.append(pointer)
    aligned.extend(
        ToolEvidence(kind="object_text_alignment", source="post.text<->image.yolo",
                     quote=item.class_name, score=item.confidence, bbox=item.bbox)
        for item in matched
    )

    if has_ocr and has_objects:
        score = round(0.7 * (ocr_similarity or 0.0) +
                      0.3 * (object_overlap or 0.0), 3)
    elif has_ocr:
        score = round(ocr_similarity or 0.0, 3)
    elif matched:
        score = round(0.5 + 0.5 * (object_overlap or 0.0), 3)
    else:
        result = _empty_result(
            "skipped", "Detected objects cannot be mapped to claims in the post text."
        )
        result.model_info = f"{context.model_version}+char_bigram_object_rule_v1"
        result.payload["context_reused"] = reused
        result.payload["vision_context"] = context.model_dump(mode="json")
        return result

    if score >= 0.5 or (ocr_similarity is not None and ocr_similarity >= 0.45):
        relation = "aligned"
        reason = "Post text overlaps with visible OCR text or detected image objects."
    elif matched:
        relation = "complementary"
        reason = "The image contains objects related to the post, while adding different details."
    elif conflicting:
        relation = "conflicting"
        reason = "Visible OCR text has little semantic overlap with the post text."
    else:
        relation = "insufficient"
        reason = "Visual evidence is too weak to determine a semantic relation."

    evidence = aligned + conflicting
    if not evidence:
        evidence = [ToolEvidence(kind="insufficient", source="image.visual",
                                 quote=reason, score=score)]
    return ImageTextConsistencyResult(
        status="degraded", score=score, evidence=evidence,
        warnings=[
            "Deterministic OCR/object fallback used; this is not full-image VLM understanding.",
            "Consistency is an evidence feature, not an advertising probability.",
        ],
        model_info=f"{context.model_version}+char_bigram_object_rule_v1",
        payload={
            "consistency_score": score,
            "relation": relation,
            "reason": reason,
            "aligned_evidence": [item.model_dump(mode="json") for item in aligned],
            "conflicting_evidence": [item.model_dump(mode="json") for item in conflicting],
            "components": {
                "ocr_similarity": round(ocr_similarity, 3) if ocr_similarity is not None else None,
                "object_overlap": round(object_overlap, 3) if object_overlap is not None else None,
            },
            "context_reused": reused,
            "vision_context": context.model_dump(mode="json"),
        },
    )


@tool(args_schema=ImageTextConsistencyInput)
def image_text_consistency(
    text: str,
    image_path: str,
    vision_context: dict | None = None,
) -> dict:
    """Compare post text with one local image; return semantic relation, not an ad verdict."""
    return _image_text_consistency_core(ImageTextConsistencyInput(
        text=text, image_path=image_path, vision_context=vision_context,
    )).model_dump(mode="json")

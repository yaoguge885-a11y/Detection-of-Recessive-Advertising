"""Commercial-object and brand-candidate tool over a shared VisionContext."""
from __future__ import annotations

import re
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from .contracts import ToolEvidence, ToolResult
from .vision import commercial_objects
from .vision_context import (
    VisionContext,
    VisionDependencyError,
    resolve_vision_context,
    validate_local_image_path,
)


_SALES_ONLY = re.compile(
    r"(?:[¥￥$]\s*\d|\d+(?:\.\d+)?(?:元|折)|限时|秒杀|抢购|优惠|领券|包邮|扫码|下单|已售|销量)"
)


class DetectLogoProductInput(BaseModel):
    image_path: str
    vision_context: VisionContext | None = None
    min_confidence: float = Field(default=0.25, ge=0, le=1)

    @field_validator("image_path")
    @classmethod
    def local_path_only(cls, value: str) -> str:
        return validate_local_image_path(value)


class DetectLogoProductResult(ToolResult):
    tool_name: Literal["detect_logo_product"] = "detect_logo_product"


def _brand_candidates(context: VisionContext) -> list[dict]:
    """Return conservative OCR candidates, never asserted as verified brands."""
    candidates: list[dict] = []
    seen: set[str] = set()
    for block in context.texts:
        text = block.text.strip()
        compact = re.sub(r"\s+", "", text)
        if not (2 <= len(compact) <= 30):
            continue
        if compact in seen or _SALES_ONLY.search(compact):
            continue
        if not re.search(r"[A-Za-z\u4e00-\u9fff]", compact):
            continue
        if len(compact) > 16 and not re.fullmatch(r"[A-Za-z0-9&._-]+", compact):
            continue
        seen.add(compact)
        candidates.append({
            "name": text,
            "confidence": block.confidence,
            "bbox": block.bbox,
            "source": "ocr_text_candidate",
        })
    return candidates


def _empty_result(status: str, warning: str) -> DetectLogoProductResult:
    return DetectLogoProductResult(
        status=status, score=None, warnings=[warning],
        payload={
            "objects": [], "commercial_objects": [], "brand_candidates": [],
            "logo_candidates": [],
            "capabilities": {"object_detection": "unavailable",
                             "brand_candidates": "unavailable",
                             "logo_detection": "none"},
            "vision_context": None,
        },
    )


def _detect_logo_product_core(inp: DetectLogoProductInput) -> DetectLogoProductResult:
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

    objects = [
        item.model_dump(mode="json")
        for item in context.objects
        if item.confidence >= inp.min_confidence
    ]
    commercial_names = set(commercial_objects(objects))
    commercial = [item for item in objects if item["class_name"] in commercial_names]
    brands = _brand_candidates(context) if context.capabilities.get("ocr", False) else []

    evidence = [
        ToolEvidence(kind="commercial_object", source="image.yolo",
                     quote=item["class_name"], score=item["confidence"],
                     bbox=item["bbox"])
        for item in commercial
    ]
    evidence.extend(
        ToolEvidence(kind="brand_candidate", source="image.ocr",
                     quote=item["name"], score=item["confidence"],
                     bbox=item["bbox"])
        for item in brands
    )
    if not evidence:
        evidence = [ToolEvidence(kind="absence", source="image.visual",
                                 quote="No commercial object or OCR brand candidate.", score=0)]

    strongest_object = max((item["confidence"] for item in commercial), default=0.0)
    strongest_brand = max((item["confidence"] * 0.7 for item in brands), default=0.0)
    score = round(max(strongest_object, strongest_brand), 3)
    warnings = [
        "No dedicated logo model is configured; logo_candidates is intentionally empty."
    ]
    if not context.capabilities.get("ocr", False):
        warnings.append("OCR is unavailable, so brand candidates could not be extracted.")
    return DetectLogoProductResult(
        status="ok", score=score, evidence=evidence, warnings=warnings,
        model_info=context.model_version,
        payload={
            "objects": objects,
            "commercial_objects": commercial,
            "brand_candidates": brands,
            "logo_candidates": [],
            "capabilities": {
                "object_detection": "yolo_coco",
                "brand_candidates": "ocr_heuristic" if context.capabilities.get("ocr", False)
                else "unavailable",
                "logo_detection": "none",
            },
            "context_reused": reused,
            "vision_context": context.model_dump(mode="json"),
        },
    )


@tool(args_schema=DetectLogoProductInput)
def detect_logo_product(
    image_path: str,
    vision_context: dict | None = None,
    min_confidence: float = 0.25,
) -> dict:
    """Detect COCO product objects and OCR brand candidates in a local image."""
    return _detect_logo_product_core(DetectLogoProductInput(
        image_path=image_path,
        vision_context=vision_context,
        min_confidence=min_confidence,
    )).model_dump(mode="json")

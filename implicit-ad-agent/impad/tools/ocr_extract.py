"""OCR extraction tool built on the shared :class:`VisionContext`."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from .contracts import ToolEvidence, ToolResult
from .vision_context import (
    VisionContext,
    VisionDependencyError,
    resolve_vision_context,
    validate_local_image_path,
)


_SALES_PATTERNS = {
    "price": re.compile(r"(?:[¥￥$]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*元)"),
    "discount": re.compile(r"(?:\d(?:\.\d)?折|满\s*\d+\s*减\s*\d+|立减\s*\d+|优惠券|领券)"),
    "sales_volume": re.compile(r"(?:已售|销量|月销)\s*\d+[万wW]?|\d+\s*人付款"),
    "promotion": re.compile(r"(?:限时|秒杀|抢购|包邮|赠品|下单|扫码)"),
}


class OCRExtractInput(BaseModel):
    image_path: str
    vision_context: VisionContext | None = None
    min_confidence: float = Field(default=0.3, ge=0, le=1)
    detect_qr: bool = True

    @field_validator("image_path")
    @classmethod
    def local_path_only(cls, value: str) -> str:
        return validate_local_image_path(value)


class OCRExtractResult(ToolResult):
    tool_name: Literal["ocr_extract"] = "ocr_extract"


def _bbox_from_points(points) -> list[int] | None:
    if points is None:
        return None
    try:
        flat = points.reshape(-1, 2)
        xs = [int(point[0]) for point in flat]
        ys = [int(point[1]) for point in flat]
        return [min(xs), min(ys), max(xs), max(ys)]
    except Exception:
        return None


def _detect_qr_codes(image_path: str) -> tuple[list[dict], list[str]]:
    """Decode local QR codes without ever fetching a remote resource."""
    path = Path(image_path)
    if not path.is_file():
        return [], ["QR detection skipped because the local image is unavailable."]
    try:
        import cv2

        image = cv2.imread(str(path))
        if image is None:
            return [], ["QR detection could not read the local image."]
        detector = cv2.QRCodeDetector()
        if hasattr(detector, "detectAndDecodeMulti"):
            ok, decoded, points, _ = detector.detectAndDecodeMulti(image)
            if ok and points is not None:
                return [
                    {
                        "detected": True,
                        "content": value or None,
                        "bbox": _bbox_from_points(point),
                    }
                    for value, point in zip(decoded, points)
                ], []
        value, points, _ = detector.detectAndDecode(image)
        if points is not None:
            return [{"detected": True, "content": value or None,
                     "bbox": _bbox_from_points(points)}], []
        return [], []
    except Exception as exc:
        return [], [f"QR detection unavailable ({type(exc).__name__})."]


def _sales_signals(blocks: list[dict]) -> list[dict]:
    signals: list[dict] = []
    seen: set[tuple[str, str, tuple[int, ...]]] = set()
    for block in blocks:
        text = block["text"]
        bbox = block["bbox"]
        for signal_type, pattern in _SALES_PATTERNS.items():
            for match in pattern.finditer(text):
                key = (signal_type, match.group(0), tuple(bbox))
                if key in seen:
                    continue
                seen.add(key)
                signals.append({
                    "type": signal_type,
                    "value": match.group(0),
                    "source_text": text,
                    "bbox": bbox,
                })
    return signals


def _ocr_extract_core(inp: OCRExtractInput) -> OCRExtractResult:
    if not inp.image_path:
        return OCRExtractResult(
            status="skipped", score=None,
            warnings=["A local image_path is required."],
            payload={"full_text": "", "text_blocks": [], "qr_codes": [],
                     "sales_signals": [], "vision_context": None},
        )
    try:
        context, reused = resolve_vision_context(inp.image_path, inp.vision_context)
    except FileNotFoundError:
        return OCRExtractResult(
            status="error", score=None,
            warnings=["The local image file does not exist."],
            payload={"full_text": "", "text_blocks": [], "qr_codes": [],
                     "sales_signals": [], "vision_context": None},
        )
    except VisionDependencyError:
        return OCRExtractResult(
            status="skipped", score=None,
            warnings=["Local YOLO/OCR dependencies are unavailable."],
            payload={"full_text": "", "text_blocks": [], "qr_codes": [],
                     "sales_signals": [], "vision_context": None},
        )
    except Exception as exc:
        return OCRExtractResult(
            status="error", score=None,
            warnings=[f"Visual analysis failed safely ({type(exc).__name__})."],
            payload={"full_text": "", "text_blocks": [], "qr_codes": [],
                     "sales_signals": [], "vision_context": None},
        )

    blocks = [
        block.model_dump(mode="json")
        for block in context.texts
        if block.text.strip() and block.confidence >= inp.min_confidence
    ]
    blocks.sort(key=lambda block: (block["bbox"][1], block["bbox"][0]))
    full_text = " ".join(block["text"] for block in blocks)
    evidence = [
        ToolEvidence(kind="ocr_text", source="image.ocr", quote=block["text"],
                     score=block["confidence"], bbox=block["bbox"])
        for block in blocks
    ]
    if not evidence:
        evidence = [ToolEvidence(kind="absence", source="image.ocr",
                                 quote="No text above the confidence threshold.", score=0)]
    qr_codes, qr_warnings = _detect_qr_codes(inp.image_path) if inp.detect_qr else ([], [])
    sales_signals = _sales_signals(blocks)
    ocr_available = bool(context.capabilities.get("ocr", False))
    status = "ok" if ocr_available else "degraded"
    warnings = qr_warnings
    if not ocr_available:
        warnings.append("EasyOCR was unavailable; any injected OCR findings may be incomplete.")
    score = round(sum(block["confidence"] for block in blocks) / len(blocks), 3) if blocks else 0.0
    return OCRExtractResult(
        status=status, score=score, evidence=evidence, warnings=warnings,
        model_info=context.model_version,
        payload={
            "full_text": full_text,
            "text_blocks": blocks,
            "qr_codes": qr_codes,
            "sales_signals": sales_signals,
            "context_reused": reused,
            "vision_context": context.model_dump(mode="json"),
        },
    )


@tool(args_schema=OCRExtractInput)
def ocr_extract(
    image_path: str,
    vision_context: dict | None = None,
    min_confidence: float = 0.3,
    detect_qr: bool = True,
) -> dict:
    """Extract local-image OCR blocks, QR codes and sales signals with bbox evidence."""
    return _ocr_extract_core(OCRExtractInput(
        image_path=image_path,
        vision_context=vision_context,
        min_confidence=min_confidence,
        detect_qr=detect_qr,
    )).model_dump(mode="json")

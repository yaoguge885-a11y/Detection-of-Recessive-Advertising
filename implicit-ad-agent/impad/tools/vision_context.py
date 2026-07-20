"""Reusable structured findings for P2 visual tools.

The context is deliberately independent from the P1 post schema. It captures
one YOLO/OCR pass so several tools can consume the same visual findings without
running the heavy models repeatedly.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import vision


_REMOTE_SOURCE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
_CONTEXT_CACHE: dict[tuple[str, str], "VisionContext"] = {}


class VisionDependencyError(RuntimeError):
    """Raised when the optional local vision stack is not installed."""


class VisionObject(BaseModel):
    class_name: str
    confidence: float = Field(ge=0, le=1)
    bbox: list[int] = Field(min_length=4, max_length=4)
    class_id: int | None = None
    center: list[int] | None = Field(default=None, min_length=2, max_length=2)


class VisionTextBlock(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)
    bbox: list[int] = Field(min_length=4, max_length=4)


class VisionFocus(BaseModel):
    focus_point: list[int] | None = Field(default=None, min_length=2, max_length=2)
    confidence: float = Field(default=0.0, ge=0, le=1)
    method: str = "unknown"
    num_objects: int = Field(default=0, ge=0)


class VisionContext(BaseModel):
    """Serializable result of one local image analysis pass."""

    image_id: str
    image_name: str
    objects: list[VisionObject] = Field(default_factory=list)
    texts: list[VisionTextBlock] = Field(default_factory=list)
    focus: VisionFocus = Field(default_factory=VisionFocus)
    model_version: str
    capabilities: dict[str, str | bool] = Field(default_factory=dict)


def validate_local_image_path(image_path: str) -> str:
    """Reject remote/data URLs while preserving valid Windows drive paths."""
    value = image_path.strip()
    if _REMOTE_SOURCE.match(value) or value.lower().startswith("data:"):
        raise ValueError("image_path must be a local filesystem path")
    return value


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _pipeline_version(model_size: str, enable_ocr: bool) -> str:
    ocr = "easyocr" if enable_ocr else "no-ocr"
    return f"vision-context-v1:yolo11{model_size}+{ocr}"


def _object_from_raw(item: dict[str, Any]) -> VisionObject:
    bbox = [int(value) for value in item.get("bbox", [0, 0, 0, 0])]
    center = item.get("center")
    if center is None and len(bbox) == 4:
        center = [(bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2]
    return VisionObject(
        class_name=str(item.get("class_name", "unknown")),
        confidence=float(item.get("confidence", 0.0)),
        bbox=bbox,
        class_id=item.get("class_id"),
        center=center,
    )


def _text_from_raw(item: dict[str, Any]) -> VisionTextBlock:
    return VisionTextBlock(
        text=str(item.get("text", "")),
        confidence=float(item.get("confidence", 0.0)),
        bbox=[int(value) for value in item.get("bbox", [0, 0, 0, 0])],
    )


def _focus_from_raw(item: dict[str, Any] | None) -> VisionFocus:
    item = item or {}
    return VisionFocus(
        focus_point=item.get("focus_point"),
        confidence=float(item.get("confidence", 0.0)),
        method=str(item.get("method", "unknown")),
        num_objects=int(item.get("num_objects", 0)),
    )


def build_vision_context(
    image_path: str,
    *,
    model_size: str = "nano",
    enable_ocr: bool = True,
    use_cache: bool = True,
) -> VisionContext:
    """Analyze one local image and cache the serializable raw findings."""
    value = validate_local_image_path(image_path)
    path = Path(value)
    if not value or not path.is_file():
        raise FileNotFoundError(path.name or "image")
    if not vision.vision_available():
        raise VisionDependencyError("local vision dependencies are unavailable")

    image_id = _file_digest(path)
    pipeline_version = _pipeline_version(model_size, enable_ocr)
    cache_key = (image_id, pipeline_version)
    if use_cache and cache_key in _CONTEXT_CACHE:
        return _CONTEXT_CACHE[cache_key]

    raw = vision.analyze_image(str(path), model_size=model_size, enable_ocr=enable_ocr)
    ocr_available = bool(raw.get("ocr_available", enable_ocr))
    model_version = str(raw.get("model_version") or raw.get("model") or pipeline_version)
    context = VisionContext(
        image_id=image_id,
        image_name=path.name,
        objects=[_object_from_raw(item) for item in raw.get("objects", [])],
        texts=[_text_from_raw(item) for item in raw.get("texts", [])],
        focus=_focus_from_raw(raw.get("focus")),
        model_version=model_version,
        capabilities={
            "object_detection": True,
            "ocr": ocr_available,
            "focus": True,
            "logo_detection": "none",
        },
    )
    if use_cache:
        _CONTEXT_CACHE[cache_key] = context
    return context


def resolve_vision_context(
    image_path: str,
    context: VisionContext | None,
    *,
    model_size: str = "nano",
    enable_ocr: bool = True,
) -> tuple[VisionContext, bool]:
    """Return an injected context or build one; bool indicates context reuse."""
    if context is not None:
        value = validate_local_image_path(image_path)
        if value and Path(value).name != context.image_name:
            raise ValueError("vision_context does not belong to image_path")
        return context, True
    return build_vision_context(
        image_path, model_size=model_size, enable_ocr=enable_ocr
    ), False


def clear_vision_context_cache() -> None:
    """Clear result cache (primarily for deterministic tests)."""
    _CONTEXT_CACHE.clear()

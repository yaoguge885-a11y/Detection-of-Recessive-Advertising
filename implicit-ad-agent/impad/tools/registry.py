"""Metadata-rich registry for the stable P2 analysis tools."""
from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from .comment_anomaly import comment_anomaly
from .detect_logo_product import detect_logo_product
from .image_text_consistency import image_text_consistency
from .ocr_extract import ocr_extract
from .sentiment import sentiment_curve
from .text_intent import analyze_text_intent
from .topic_drift import topic_drift


ToolModality = Literal["text", "image", "comments", "history"]


class ToolSpec(BaseModel):
    """Runtime and protocol metadata for one registered analysis tool."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    description: str
    tool: BaseTool = Field(exclude=True, repr=False)
    input_schema: dict[str, Any]
    required_modalities: frozenset[ToolModality]
    minimum_samples: dict[str, int]
    default_timeout_seconds: float = Field(gt=0)
    allow_parallel: bool
    function_calling: dict[str, Any]
    mcp_name: str
    ready: bool
    version: str = "1.0"


def _spec(
    registered_tool: BaseTool,
    *,
    required_modalities: set[ToolModality],
    minimum_samples: dict[str, int],
    default_timeout_seconds: float,
    allow_parallel: bool = True,
) -> ToolSpec:
    input_schema = registered_tool.args_schema.model_json_schema()
    input_schema["additionalProperties"] = False
    return ToolSpec(
        name=registered_tool.name,
        description=registered_tool.description,
        tool=registered_tool,
        input_schema=input_schema,
        required_modalities=frozenset(required_modalities),
        minimum_samples=minimum_samples,
        default_timeout_seconds=default_timeout_seconds,
        allow_parallel=allow_parallel,
        function_calling={
            "type": "function",
            "function": {
                "name": registered_tool.name,
                "description": registered_tool.description,
                "parameters": input_schema,
            },
        },
        mcp_name=f"detection.{registered_tool.name}",
        ready=True,
    )


TOOL_SPECS_V1 = [
    _spec(
        analyze_text_intent,
        required_modalities={"text"},
        minimum_samples={"text": 1},
        default_timeout_seconds=10,
    ),
    _spec(
        sentiment_curve,
        required_modalities={"text"},
        minimum_samples={"text": 1},
        default_timeout_seconds=10,
    ),
    _spec(
        ocr_extract,
        required_modalities={"image"},
        minimum_samples={"image": 1},
        default_timeout_seconds=120,
    ),
    _spec(
        image_text_consistency,
        required_modalities={"text", "image"},
        minimum_samples={"text": 1, "image": 1},
        default_timeout_seconds=120,
    ),
    _spec(
        detect_logo_product,
        required_modalities={"image"},
        minimum_samples={"image": 1},
        default_timeout_seconds=120,
    ),
    _spec(
        topic_drift,
        required_modalities={"text", "history"},
        minimum_samples={"text": 1, "history": 3},
        default_timeout_seconds=30,
    ),
    _spec(
        comment_anomaly,
        required_modalities={"comments"},
        minimum_samples={"comments": 5},
        default_timeout_seconds=10,
    ),
]

TOOL_SPEC_BY_NAME = {spec.name: spec for spec in TOOL_SPECS_V1}

# Backward-compatible exports used by existing tests, demos, and agents.
TOOLS_V1 = [spec.tool for spec in TOOL_SPECS_V1]
TOOL_READINESS = {spec.name: spec.ready for spec in TOOL_SPECS_V1}

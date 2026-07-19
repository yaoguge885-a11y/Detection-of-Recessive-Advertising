"""Shared P2 contracts for independently callable analysis tools."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolStatus = Literal["ok", "degraded", "skipped", "error"]


class ToolEvidence(BaseModel):
    """A machine-readable pointer back to the input that supports a result."""

    kind: str
    source: str
    quote: str | None = None
    span: tuple[int, int] | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    bbox: list[int] | None = None
    related_post_id: str | None = None
    comment_ids: list[str] = Field(default_factory=list)


class ToolResult(BaseModel):
    """Common envelope used by every P2 tool result."""

    tool_name: str
    tool_version: str = "1.0"
    status: ToolStatus
    score: float | None = Field(default=None, ge=0, le=1)
    evidence: list[ToolEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    model_info: str | None = None


"""Shared P2 contracts for independently callable analysis tools."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ToolStatus = Literal["ok", "degraded", "skipped", "error"]
ToolLimitationKind = Literal["capture", "evidence"]


class StrictToolInput(BaseModel):
    """Reject fields outside a tool's declared argument contract."""

    model_config = ConfigDict(extra="forbid")


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


class ToolLimitation(BaseModel):
    """A structured reason why capture or evidence is incomplete."""

    kind: ToolLimitationKind
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source: str | None = None


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
    call_id: str | None = None
    run_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    retryable: bool | None = None
    input_fingerprint: str | None = None
    limitations: list[ToolLimitation] = Field(default_factory=list)


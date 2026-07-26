"""Run-level audit metadata and structured degradation information."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RunIssue(BaseModel):
    """One error or degradation recorded during a run."""

    kind: Literal["error", "degradation"]
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    retryable: bool | None = None


class RunMetadata(BaseModel):
    """Auditable versions, timing, traces, and issues for one analysis."""

    run_id: str = Field(min_length=1)
    status: Literal["pending", "running", "completed", "degraded", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    tool_versions: dict[str, str] = Field(default_factory=dict)
    model_versions: dict[str, str] = Field(default_factory=dict)
    issues: list[RunIssue] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    runtime_mode: Literal["local", "mcp", "a2a", "hybrid"] = "local"
    planner_version: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    token_usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float | None = Field(default=None, ge=0)
    retry_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)

    @field_validator("token_usage")
    @classmethod
    def token_counts_are_non_negative(cls, value: dict[str, int]):
        if any(count < 0 for count in value.values()):
            raise ValueError("token_usage counts must be non-negative")
        return value

"""Normalized evidence contracts for downstream adequacy and judgment."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..tools.contracts import ToolLimitation, ToolResult


EvidencePolarity = Literal["supports", "contradicts", "neutral"]
EvidenceStatus = Literal["observed", "degraded", "conflicted"]
EvidenceSourceType = Literal[
    "text",
    "image",
    "comment",
    "disclosure",
    "history",
    "metadata",
]
CoverageStatus = Literal[
    "covered",
    "partial",
    "missing",
    "unsupported",
    "not_applicable",
]


class EvidenceItem(BaseModel):
    """One positive observation with a traceable source."""

    evidence_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    source: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    call_id: str | None = None
    quote: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    span: tuple[int, int] | None = None
    bbox: list[int] | None = None
    related_post_id: str | None = None
    comment_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    polarity: EvidencePolarity = "neutral"
    strength: float | None = Field(default=None, ge=0, le=1)
    source_type: EvidenceSourceType | None = None
    source_ref: str | None = None
    producer: str | None = None
    producer_version: str | None = None
    status: EvidenceStatus = "observed"
    limitations: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None

    @model_validator(mode="after")
    def fill_legacy_provenance_defaults(self):
        if self.strength is None:
            self.strength = self.score
        if self.source_ref is None:
            self.source_ref = self.source
        if self.producer is None:
            self.producer = f"tool:{self.tool_name}"
        if self.producer_version is None:
            self.producer_version = self.tool_version
        if self.source_type is None:
            lowered = self.source.lower()
            if "comment" in lowered:
                self.source_type = "comment"
            elif "history" in lowered or "related_post" in lowered:
                self.source_type = "history"
            elif "image" in lowered or "media" in lowered:
                self.source_type = "image"
            elif "text" in lowered:
                self.source_type = "text"
            else:
                self.source_type = "metadata"
        return self


class EvidenceModalityCoverage(BaseModel):
    """Coverage of one input modality and its supporting evidence."""

    modality: EvidenceSourceType
    status: CoverageStatus
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[ToolLimitation] = Field(default_factory=list)


class EvidenceConflict(BaseModel):
    """An explicit disagreement between two or more evidence items."""

    conflict_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=2)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_references_are_distinct(self):
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("conflict evidence_ids must be distinct")
        return self


class EvidenceBundle(BaseModel):
    """Evidence plus raw outcomes needed to reason about missing capability."""

    post_id: str = Field(min_length=1)
    items: list[EvidenceItem] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    limitations: list[ToolLimitation] = Field(default_factory=list)
    coverage: list[EvidenceModalityCoverage] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_references_are_valid(self):
        ids = [item.evidence_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique")
        known_ids = set(ids)
        referenced_ids = {
            evidence_id
            for coverage in self.coverage
            for evidence_id in coverage.evidence_ids
        }
        referenced_ids.update(
            evidence_id
            for conflict in self.conflicts
            for evidence_id in conflict.evidence_ids
        )
        unknown = sorted(referenced_ids - known_ids)
        if unknown:
            raise ValueError(
                f"unknown evidence_id references: {', '.join(unknown)}"
            )
        conflict_ids = [conflict.conflict_id for conflict in self.conflicts]
        if len(conflict_ids) != len(set(conflict_ids)):
            raise ValueError("conflict_id values must be unique")
        return self

"""Structured judgment and legal-reference contracts."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator


class CommercialIntent(BaseModel):
    """Evidence-backed commercial-intent assessment."""

    status: Literal["present", "absent", "uncertain"]
    score: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class DisclosureEvidence(BaseModel):
    """Whether advertising intent was disclosed in captured content."""

    status: Literal["disclosed", "not_disclosed", "unknown"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class LawEvidence(BaseModel):
    """One retrievable law or platform-rule citation."""

    source_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("source_id", "reference_id"),
    )
    document_title: str = Field(
        min_length=1,
        validation_alias=AliasChoices("document_title", "title"),
    )
    source_path_or_url: str = Field(
        min_length=1,
        validation_alias=AliasChoices("source_path_or_url", "source_url"),
    )
    article_id: str | None = None
    document_version: str | None = None
    jurisdiction: str | None = None
    effective_date: date | None = None
    quote: str | None = None
    retrieval_score: float | None = Field(default=None, ge=0, le=1)
    rerank_score: float | None = Field(default=None, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)

    @property
    def reference_id(self) -> str:
        return self.source_id

    @property
    def title(self) -> str:
        return self.document_title

    @property
    def source_url(self) -> str:
        return self.source_path_or_url


class CreatorShiftSummary(BaseModel):
    """Report-facing CreatorShift state; score is evidence, not probability."""

    status: Literal["sufficient", "insufficient", "unavailable"]
    history_count: int = Field(ge=0)
    required_history: int = Field(ge=1)
    feature_version: str = "keyword_weights_v1"
    runtime_version: str = "creator_shift_runtime_v1"
    pooling_method: Literal["mean", "max", "ema"] | None = None
    shift_score: float | None = Field(default=None, ge=0, le=1)
    history_post_ids: list[str] = Field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    top_features: list[str] = Field(default_factory=list)
    feature_deltas: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def numeric_result_requires_sufficient_history(self):
        if self.status == "sufficient":
            if self.shift_score is None or self.pooling_method is None:
                raise ValueError(
                    "sufficient CreatorShift requires score and pooling method"
                )
            if self.history_count < self.required_history:
                raise ValueError(
                    "sufficient CreatorShift requires enough history"
                )
            return self
        if self.shift_score is not None or self.pooling_method is not None:
            raise ValueError(
                "nonnumeric CreatorShift states cannot contain a score"
            )
        return self


class VerdictReport(BaseModel):
    """Final structured decision before presentation formatting."""

    post_id: str = Field(min_length=1)
    label: Literal["明广", "暗广", "非广", "需复核"]
    confidence: float = Field(ge=0, le=1)
    review_required: bool
    commercial_intent: CommercialIntent
    disclosure: DisclosureEvidence
    creator_shift: CreatorShiftSummary | None = None
    creator_shift_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    law_evidence: list[LawEvidence] = Field(default_factory=list)
    judgment_method: str = "deterministic_baseline_v1"

    @model_validator(mode="after")
    def label_matches_evidence_state(self):
        review_label = self.label == "需复核"
        if self.review_required != review_label:
            raise ValueError(
                "review_required must be true exactly when label is 需复核"
            )
        if review_label:
            return self

        intent = self.commercial_intent.status
        disclosure = self.disclosure.status
        if self.label == "明广" and not (
            intent == "present" and disclosure == "disclosed"
        ):
            raise ValueError(
                "明广 requires present commercial intent and disclosed status"
            )
        if self.label == "暗广" and not (
            intent == "present" and disclosure == "not_disclosed"
        ):
            raise ValueError(
                "暗广 requires present commercial intent and not_disclosed status"
            )
        if self.label == "非广" and intent != "absent":
            raise ValueError("非广 requires absent commercial intent")
        return self

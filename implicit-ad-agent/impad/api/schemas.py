"""P3 HTTP boundary; core contracts remain the source of truth."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..adapters.platforms import (
    URLImportCorrections,
    URLImportPreview,
)
from ..contracts import EvidenceBundle, RunMetadata, VerdictReport
from ..orchestration import RunEvent
from ..services import BATCH_MAX_ITEMS, BatchAnalysisError


class AnalyzeRequest(BaseModel):
    text: str
    post_id: str | None = None
    platform: str = "other"
    blogger: str = "未知"
    creator_id: str | None = None
    published_at: str | None = None
    image_url: str | None = None
    image_path: str | None = None
    comments: list[str | dict[str, Any]] = Field(default_factory=list)
    history: list[str | dict[str, Any]] = Field(default_factory=list)
    capture_complete: bool = False
    runtime_mode: Literal["local", "mcp"] = "local"

    def post_payload(self) -> dict[str, Any]:
        payload = self.model_dump(exclude={"runtime_mode"}, exclude_none=True)
        return payload


class AnalyzeResponse(BaseModel):
    verdict_report: VerdictReport
    evidence_bundle: EvidenceBundle
    run_metadata: RunMetadata
    run_events: list[RunEvent]
    readable_report: str


class BatchAnalyzeRequest(BaseModel):
    items: list[AnalyzeRequest] = Field(
        min_length=1,
        max_length=BATCH_MAX_ITEMS,
    )


class BatchAnalyzeItemResponse(BaseModel):
    index: int
    ok: bool
    result: AnalyzeResponse | None = None
    error: BatchAnalysisError | None = None


class BatchAnalyzeResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    items: list[BatchAnalyzeItemResponse]


class URLPreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class URLPreviewResponse(URLImportPreview):
    pass


class URLConfirmRequest(BaseModel):
    preview_id: str = Field(pattern=r"^preview_[0-9a-f]{32}$")
    corrections: URLImportCorrections = Field(
        default_factory=URLImportCorrections
    )
    runtime_mode: Literal["local", "mcp"] = "local"

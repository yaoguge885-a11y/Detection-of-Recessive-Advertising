"""Unified P3 analysis entry point for local and MCP execution."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    model_validator,
)

from ..agents.supervisor import normalize_post_record
from ..contracts import (
    EvidenceBundle,
    PostRecord,
    RunIssue,
    RunMetadata,
    VerdictReport,
)
from ..graph import graph
from ..orchestration import (
    LocalToolGateway,
    MCPToolGateway,
    RunEvent,
    ToolGateway,
)
from ..rag import LegalRetriever, build_default_legal_retriever
from .reporting import legal_query, render_readable_report
from .run_store import JsonRunStore, RunRecord, RunStore


RuntimeMode = Literal["local", "mcp"]
BATCH_MAX_ITEMS = 50


class AnalysisResult(BaseModel):
    post: PostRecord
    evidence_bundle: EvidenceBundle
    verdict_report: VerdictReport
    run_metadata: RunMetadata
    run_events: list[RunEvent]
    readable_report: str


class BatchAnalysisInput(BaseModel):
    post: dict | PostRecord
    runtime_mode: RuntimeMode = "local"


class BatchAnalysisError(BaseModel):
    code: Literal["invalid_input", "analysis_failed"]
    message: str


class BatchAnalysisItem(BaseModel):
    index: int = Field(ge=0)
    result: AnalysisResult | None = None
    error: BatchAnalysisError | None = None

    @model_validator(mode="after")
    def exactly_one_outcome(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("batch item requires exactly one outcome")
        return self


class BatchAnalysisResult(BaseModel):
    total: int = Field(ge=1, le=BATCH_MAX_ITEMS)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    items: list[BatchAnalysisItem]

    @model_validator(mode="after")
    def counts_match_items(self):
        succeeded = sum(item.result is not None for item in self.items)
        if (
            self.total != len(self.items)
            or self.succeeded != succeeded
            or self.failed != self.total - succeeded
        ):
            raise ValueError("batch counts must match item outcomes")
        return self


def _invalid_batch_input_error() -> BatchAnalysisError:
    return BatchAnalysisError(
        code="invalid_input",
        message="Input could not be normalized.",
    )


def _analysis_failed_batch_error() -> BatchAnalysisError:
    return BatchAnalysisError(
        code="analysis_failed",
        message="Analysis failed.",
    )


def _event(
    run_id: str,
    event_type: str,
    stage: str,
    *,
    timestamp: datetime | None = None,
    **data,
) -> RunEvent:
    return RunEvent(
        event_id=f"event_{uuid4().hex}",
        run_id=run_id,
        event_type=event_type,
        stage=stage,
        timestamp=timestamp or datetime.now(timezone.utc),
        data=data,
    )


class AnalysisService:
    """Run classification, then legal retrieval, rendering, and persistence."""

    def __init__(
        self,
        *,
        retriever: LegalRetriever | None = None,
        run_store: RunStore | None = None,
        local_gateway: ToolGateway | None = None,
        mcp_gateway: ToolGateway | None = None,
    ):
        self.retriever = retriever or build_default_legal_retriever()
        self.run_store = run_store or JsonRunStore(
            Path(__file__).resolve().parents[2] / ".impad_runtime" / "runs"
        )
        self.local_gateway = local_gateway or LocalToolGateway()
        self.mcp_gateway = mcp_gateway

    def analyze(
        self,
        post: dict | PostRecord,
        *,
        runtime_mode: RuntimeMode = "local",
    ) -> AnalysisResult:
        if runtime_mode == "mcp":
            gateway = self.mcp_gateway or MCPToolGateway()
        else:
            gateway = self.local_gateway
        state = graph.invoke({
            "post": post,
            "tool_gateway": gateway,
            "runtime_mode": runtime_mode,
        })
        normalized = state["post_record"]
        bundle = state["evidence_bundle"]
        verdict = state["verdict_report"]
        metadata = state["run_metadata"]
        events = [
            _event(
                metadata.run_id,
                "analysis_started",
                "analysis",
                timestamp=metadata.started_at,
                runtime_mode=runtime_mode,
            ),
            *state.get("run_events", []),
            _event(
                metadata.run_id,
                "judgment_completed",
                "judge",
                label=verdict.label,
                confidence=verdict.confidence,
            ),
        ]
        issues = list(metadata.issues)
        try:
            citations = self.retriever.retrieve(
                legal_query(normalized, verdict),
                top_k=3,
            )
        except Exception as exc:
            citations = []
            issues.append(RunIssue(
                kind="degradation",
                code="legal_retrieval_failed",
                message=f"Legal retrieval failed ({type(exc).__name__}).",
                stage="rag",
                retryable=True,
            ))
        verdict = verdict.model_copy(update={"law_evidence": citations})
        events.append(_event(
            metadata.run_id,
            "rag_completed",
            "rag",
            citation_count=len(citations),
            abstained=not citations,
        ))
        finished = datetime.now(timezone.utc)
        metadata = metadata.model_copy(update={
            "status": (
                "degraded"
                if issues or metadata.status == "degraded"
                else "completed"
            ),
            "issues": issues,
            "finished_at": finished,
            "duration_ms": max(
                0,
                round(
                    (finished - metadata.started_at).total_seconds() * 1000
                ),
            ),
            "model_versions": {
                **metadata.model_versions,
                "legal_corpus": "cn-official-v1-2026-07-27",
            },
        })
        readable = render_readable_report(
            normalized,
            bundle,
            verdict,
            metadata,
        )
        events.append(_event(
            metadata.run_id,
            "report_completed",
            "report",
            format="markdown",
        ))
        metadata = metadata.model_copy(update={
            "trace_ids": list(dict.fromkeys([
                *metadata.trace_ids,
                *(event.event_id for event in events),
            ]))
        })
        record = RunRecord(
            post=normalized,
            evidence_bundle=bundle,
            verdict_report=verdict,
            run_metadata=metadata,
            run_events=events,
            readable_report=readable,
        )
        self.run_store.put(record)
        persisted_event = _event(
            metadata.run_id,
            "run_persisted",
            "run_store",
        )
        events.append(persisted_event)
        metadata = metadata.model_copy(update={
            "trace_ids": [*metadata.trace_ids, persisted_event.event_id]
        })
        record = record.model_copy(update={
            "run_metadata": metadata,
            "run_events": events,
        })
        self.run_store.put(record)
        return AnalysisResult(
            post=record.post,
            evidence_bundle=record.evidence_bundle,
            verdict_report=record.verdict_report,
            run_metadata=record.run_metadata,
            run_events=record.run_events,
            readable_report=record.readable_report,
        )

    def analyze_batch(
        self,
        items: list[BatchAnalysisInput],
    ) -> BatchAnalysisResult:
        """Analyze a bounded batch while isolating per-item failures."""

        if not 1 <= len(items) <= BATCH_MAX_ITEMS:
            raise ValueError("batch size must be between 1 and 50")
        outcomes = []
        for index, item in enumerate(items):
            try:
                normalized = normalize_post_record(item.post)
            except (TypeError, ValueError, ValidationError):
                outcomes.append(BatchAnalysisItem(
                    index=index,
                    error=_invalid_batch_input_error(),
                ))
                continue
            try:
                result = self.analyze(
                    normalized,
                    runtime_mode=item.runtime_mode,
                )
                outcomes.append(BatchAnalysisItem(
                    index=index,
                    result=result,
                ))
            except Exception:
                outcomes.append(BatchAnalysisItem(
                    index=index,
                    error=_analysis_failed_batch_error(),
                ))
        succeeded = sum(item.result is not None for item in outcomes)
        return BatchAnalysisResult(
            total=len(outcomes),
            succeeded=succeeded,
            failed=len(outcomes) - succeeded,
            items=outcomes,
        )

    def get_run(self, run_id: str) -> RunRecord | None:
        return self.run_store.get(run_id)


@lru_cache(maxsize=1)
def get_default_analysis_service() -> AnalysisService:
    return AnalysisService()

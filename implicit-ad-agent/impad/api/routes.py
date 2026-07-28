"""FastAPI routes backed only by AnalysisService."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import AnalysisService, get_default_analysis_service
from .schemas import AnalyzeRequest, AnalyzeResponse


def create_api_router(
    service: AnalysisService | None = None,
) -> APIRouter:
    router = APIRouter()

    def active_service() -> AnalysisService:
        return service or get_default_analysis_service()

    @router.get("/capabilities")
    def capabilities():
        return {
            "runtime_modes": ["local", "mcp"],
            "labels": ["明广", "暗广", "非广", "需复核"],
            "detection_tools": 7,
            "legal_retrieval": "chroma_offline_official_corpus",
            "run_query": True,
        }

    @router.post("/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest):
        result = active_service().analyze(
            request.post_payload(),
            runtime_mode=request.runtime_mode,
        )
        return AnalyzeResponse(
            verdict_report=result.verdict_report,
            evidence_bundle=result.evidence_bundle,
            run_metadata=result.run_metadata,
            run_events=result.run_events,
            readable_report=result.readable_report,
        )

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        try:
            record = active_service().get_run(run_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid run_id")
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return record

    return router

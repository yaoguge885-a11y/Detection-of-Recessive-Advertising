"""FastAPI routes backed only by AnalysisService."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..adapters.platforms import (
    PlatformAdapterRegistry,
    URLImportError,
    URLImportService,
)
from ..services import (
    AnalysisResult,
    AnalysisService,
    BATCH_MAX_ITEMS,
    BatchAnalysisInput,
    get_default_analysis_service,
)
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeItemResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    URLConfirmRequest,
    URLPreviewRequest,
    URLPreviewResponse,
)


def _analyze_response(result: AnalysisResult) -> AnalyzeResponse:
    return AnalyzeResponse(
        verdict_report=result.verdict_report,
        evidence_bundle=result.evidence_bundle,
        run_metadata=result.run_metadata,
        run_events=result.run_events,
        readable_report=result.readable_report,
    )


def _raise_url_error(exc: URLImportError):
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def create_api_router(
    service: AnalysisService | None = None,
    url_import_service: URLImportService | None = None,
) -> APIRouter:
    router = APIRouter()
    resolved_url_service = url_import_service

    def active_service() -> AnalysisService:
        return service or get_default_analysis_service()

    def active_url_service() -> URLImportService:
        nonlocal resolved_url_service
        if resolved_url_service is None:
            resolved_url_service = URLImportService(
                analysis_service=active_service(),
                registry=PlatformAdapterRegistry(),
            )
        return resolved_url_service

    @router.get("/capabilities")
    def capabilities():
        url_service = active_url_service()
        return {
            "runtime_modes": ["local", "mcp"],
            "labels": ["明广", "暗广", "非广", "需复核"],
            "detection_tools": 7,
            "legal_retrieval": "chroma_offline_official_corpus",
            "run_query": True,
            "batch_analysis": {
                "enabled": True,
                "max_items": BATCH_MAX_ITEMS,
            },
            "url_import": {
                "enabled": True,
                "workflow": ["preview", "confirm"],
                "platforms": [
                    {
                        "platform": adapter.platform,
                        "adapter": adapter.name,
                        "version": adapter.version,
                        "hosts": list(adapter.supported_hosts),
                    }
                    for adapter in url_service.registry.adapters
                ],
            },
        }

    @router.post("/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest):
        result = active_service().analyze(
            request.post_payload(),
            runtime_mode=request.runtime_mode,
        )
        return _analyze_response(result)

    @router.post(
        "/analyze/batch",
        response_model=BatchAnalyzeResponse,
    )
    def analyze_batch(request: BatchAnalyzeRequest):
        batch = active_service().analyze_batch([
            BatchAnalysisInput(
                post=item.post_payload(),
                runtime_mode=item.runtime_mode,
            )
            for item in request.items
        ])
        return BatchAnalyzeResponse(
            total=batch.total,
            succeeded=batch.succeeded,
            failed=batch.failed,
            items=[
                BatchAnalyzeItemResponse(
                    index=item.index,
                    ok=item.result is not None,
                    result=(
                        _analyze_response(item.result)
                        if item.result is not None
                        else None
                    ),
                    error=item.error,
                )
                for item in batch.items
            ],
        )

    @router.post(
        "/import/url/preview",
        response_model=URLPreviewResponse,
    )
    def preview_url(request: URLPreviewRequest):
        try:
            return active_url_service().preview(request.url)
        except URLImportError as exc:
            _raise_url_error(exc)

    @router.post(
        "/import/url/confirm",
        response_model=AnalyzeResponse,
    )
    def confirm_url(request: URLConfirmRequest):
        try:
            result = active_url_service().confirm(
                request.preview_id,
                request.corrections,
                runtime_mode=request.runtime_mode,
            )
        except URLImportError as exc:
            _raise_url_error(exc)
        return _analyze_response(result)

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

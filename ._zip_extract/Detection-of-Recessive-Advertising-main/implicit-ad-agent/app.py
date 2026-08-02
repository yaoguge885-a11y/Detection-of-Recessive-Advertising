"""FastAPI application for the unified P3 analysis service."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from impad.adapters.platforms import URLImportService
from impad.api import AnalyzeRequest, create_api_router
from impad.services import AnalysisService, get_default_analysis_service
from impad.web import asset_directory


WORKBENCH_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def create_app(
    service: AnalysisService | None = None,
    *,
    url_import_service: URLImportService | None = None,
) -> FastAPI:
    application = FastAPI(
        title="隐性广告识别 API",
        version="0.3.0",
        description="证据型三分类、法规引用与可追溯运行记录。",
    )
    application.include_router(
        create_api_router(
            service,
            url_import_service=url_import_service,
        ),
        prefix="/api/v1",
        tags=["analysis"],
    )

    workbench_assets = asset_directory()
    application.mount(
        "/workbench/assets",
        StaticFiles(directory=workbench_assets),
        name="workbench-assets",
    )

    @application.get("/workbench", response_class=FileResponse)
    def workbench():
        return FileResponse(
            workbench_assets / "index.html",
            media_type="text/html; charset=utf-8",
            headers=WORKBENCH_HEADERS,
        )

    @application.get("/", response_class=HTMLResponse)
    def root():
        return (
            "<h1>隐性广告识别 API</h1>"
            "<p>使用 <a href='/docs'>/docs</a> 试用接口；"
            "正式入口为 <code>POST /api/v1/analyze</code>。</p>"
            '<p><a href="/workbench">打开开发者研究工作台</a></p>'
        )

    @application.get("/health")
    def health():
        return {"status": "ok", "api_version": "v1"}

    @application.post("/analyze")
    def compatibility_analyze(request: AnalyzeRequest):
        """Compatibility route for existing demos; uses the same service."""

        active = service or get_default_analysis_service()
        result = active.analyze(
            request.post_payload(),
            runtime_mode=request.runtime_mode,
        )
        return {
            "verdict": result.verdict_report.label,
            "confidence": result.verdict_report.confidence,
            "verdict_report": result.verdict_report,
            "evidence_bundle": result.evidence_bundle,
            "run_metadata": result.run_metadata,
            "report": result.readable_report,
        }

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=4000)

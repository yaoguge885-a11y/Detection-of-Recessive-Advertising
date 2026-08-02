"""Versioned FastAPI schemas and routes."""

from .routes import create_api_router
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

__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "BatchAnalyzeItemResponse",
    "BatchAnalyzeRequest",
    "BatchAnalyzeResponse",
    "URLConfirmRequest",
    "URLPreviewRequest",
    "URLPreviewResponse",
    "create_api_router",
]

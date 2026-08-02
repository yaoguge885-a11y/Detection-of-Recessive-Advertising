"""Safe, injectable platform URL adapter boundary."""

from .contracts import (
    PlatformAdapter,
    URLImportCorrections,
    URLImportError,
    URLImportPreview,
    ValidatedSourceURL,
)
from .registry import PlatformAdapterRegistry
from .url_import import InMemoryURLPreviewStore, URLImportService
from .url_safety import validate_public_https_url

__all__ = [
    "InMemoryURLPreviewStore",
    "PlatformAdapter",
    "PlatformAdapterRegistry",
    "URLImportCorrections",
    "URLImportError",
    "URLImportPreview",
    "URLImportService",
    "ValidatedSourceURL",
    "validate_public_https_url",
]

"""Safe, injectable platform URL adapter boundary."""

from .contracts import (
    PlatformAdapter,
    URLImportError,
    ValidatedSourceURL,
)
from .registry import PlatformAdapterRegistry
from .url_safety import validate_public_https_url

__all__ = [
    "PlatformAdapter",
    "PlatformAdapterRegistry",
    "URLImportError",
    "ValidatedSourceURL",
    "validate_public_https_url",
]

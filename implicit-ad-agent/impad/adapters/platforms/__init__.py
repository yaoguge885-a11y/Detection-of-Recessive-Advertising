"""Safe, injectable platform URL adapter boundary."""

from .contracts import (
    PlatformAdapter,
    URLImportCorrections,
    URLImportError,
    URLImportPreview,
    ValidatedSourceURL,
)
from .registry import PlatformAdapterRegistry
from .safe_fetch import (
    DisabledURLFetcher,
    DNSResolver,
    HTTPTransport,
    OneHopResponse,
    PinnedHTTPSHTTPTransport,
    ResolvedTarget,
    SafeFetchResult,
    SafeURLFetcher,
    SocketDNSResolver,
)
from .url_import import InMemoryURLPreviewStore, URLImportService
from .url_safety import validate_public_https_url

__all__ = [
    "InMemoryURLPreviewStore",
    "DisabledURLFetcher",
    "DNSResolver",
    "HTTPTransport",
    "OneHopResponse",
    "PinnedHTTPSHTTPTransport",
    "PlatformAdapter",
    "PlatformAdapterRegistry",
    "URLImportCorrections",
    "URLImportError",
    "URLImportPreview",
    "URLImportService",
    "ResolvedTarget",
    "SafeFetchResult",
    "SafeURLFetcher",
    "SocketDNSResolver",
    "ValidatedSourceURL",
    "validate_public_https_url",
]

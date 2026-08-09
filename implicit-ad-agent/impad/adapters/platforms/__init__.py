"""Safe, injectable platform URL adapter boundary."""

from .contracts import (
    PlatformAdapter,
    URLImportCorrections,
    URLImportError,
    URLImportPreview,
    ValidatedSourceURL,
)
from .registry import PlatformAdapterRegistry
from .media_safety import PlatformMediaPolicy
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
from .xiaohongshu import XiaohongshuAdapter, parse_xiaohongshu_state

__all__ = [
    "InMemoryURLPreviewStore",
    "DisabledURLFetcher",
    "DNSResolver",
    "HTTPTransport",
    "OneHopResponse",
    "PinnedHTTPSHTTPTransport",
    "PlatformAdapter",
    "PlatformMediaPolicy",
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
    "XiaohongshuAdapter",
    "parse_xiaohongshu_state",
    "validate_public_https_url",
]

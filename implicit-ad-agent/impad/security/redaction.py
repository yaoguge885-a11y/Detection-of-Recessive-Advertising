"""Recursive, idempotent redaction for outbound analysis artifacts."""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import unquote, urlsplit


REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset({
    "cookie",
    "cookies",
    "set_cookie",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "password",
    "secret",
    "session",
    "session_id",
})

_HEADER_RE = re.compile(
    r"\b(?P<name>cookie|set-cookie|authorization)\s*:\s*[^\r\n]*",
    re.IGNORECASE,
)
_AUTHORIZATION_VALUE_RE = re.compile(
    r"\b(?P<scheme>bearer|basic)\s+[^\s,;]+",
    re.IGNORECASE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?P<key>\b(?:token|access[_-]?token|refresh[_-]?token|api[_-]?key|"
    r"password|secret|session(?:[_-]?id)?))"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_HTTP_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_ENCODED_HTTP_URL_RE = re.compile(
    r"https?%3a%2f%2f[^\s<>\"']+",
    re.IGNORECASE,
)
_TRAILING_URL_PUNCTUATION = ".,;!?)]]}，。；！？）】》"


def _split_trailing_punctuation(candidate: str) -> tuple[str, str]:
    suffix = ""
    while candidate and candidate[-1] in _TRAILING_URL_PUNCTUATION:
        suffix = candidate[-1] + suffix
        candidate = candidate[:-1]
    return candidate, suffix


def _has_explicit_port(netloc: str) -> bool:
    authority = netloc.rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing = authority.find("]")
        return closing >= 0 and authority[closing + 1:].startswith(":")
    return ":" in authority


def _redact_url(candidate: str) -> str:
    url, trailing = _split_trailing_punctuation(candidate)
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        has_credentials = (
            parsed.username is not None or parsed.password is not None
        )
    except ValueError:
        return REDACTED + trailing
    has_sensitive_components = bool(
        has_credentials
        or _has_explicit_port(parsed.netloc)
        or parsed.query
        or parsed.fragment
    )
    if not has_sensitive_components:
        return url + trailing
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        return REDACTED + trailing
    normalized_host = hostname.lower()
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    safe = f"{parsed.scheme.lower()}://{normalized_host}{parsed.path}"
    return safe + trailing


def _redact_encoded_url(match: re.Match[str]) -> str:
    decoded_once = unquote(match.group(0))
    return _redact_url(decoded_once)


def redact_sensitive_text(text: str) -> str:
    """Remove credentials, tokens, and unsafe URL components from text."""

    safe = _ENCODED_HTTP_URL_RE.sub(_redact_encoded_url, text)
    safe = _HTTP_URL_RE.sub(lambda match: _redact_url(match.group(0)), safe)
    safe = _HEADER_RE.sub(
        lambda match: f"{match.group('name')}: {REDACTED}",
        safe,
    )
    safe = _AUTHORIZATION_VALUE_RE.sub(
        lambda match: f"{match.group('scheme')} {REDACTED}",
        safe,
    )
    safe = _ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group('key')}{match.group('separator')}{REDACTED}"
        ),
        safe,
    )
    return safe


def _normalized_key(key: object) -> str | None:
    if not isinstance(key, str):
        return None
    return key.casefold().replace("-", "_")


def redact_structure(value):
    """Recursively redact mappings and every free-text leaf."""

    if isinstance(value, Mapping):
        return {
            key: (
                REDACTED
                if _normalized_key(key) in SENSITIVE_KEYS
                else redact_structure(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value

"""Fail-closed URL validation before any platform adapter is called."""
from __future__ import annotations

import hashlib
from ipaddress import ip_address
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from .contracts import URLImportError, ValidatedSourceURL


_FORBIDDEN_HOSTS = {"localhost"}
_FORBIDDEN_SUFFIXES = (".localhost", ".local", ".internal")


def _normalized_hostname(hostname: str) -> str:
    try:
        return hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        raise URLImportError(
            "invalid_url",
            "URL hostname is invalid.",
        ) from exc


def _is_forbidden_destination(hostname: str) -> bool:
    if (
        hostname in _FORBIDDEN_HOSTS
        or hostname.endswith(_FORBIDDEN_SUFFIXES)
    ):
        return True
    try:
        address = ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global


def _authority(hostname: str) -> str:
    if ":" in hostname:
        return f"[{hostname}]"
    return hostname


def validate_public_https_url(url: str) -> ValidatedSourceURL:
    """Validate syntax and literal destination without resolving DNS."""

    raw = url.strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise URLImportError(
            "invalid_url",
            "URL is malformed.",
        ) from exc
    if parsed.scheme.lower() != "https":
        raise URLImportError(
            "unsafe_url_scheme",
            "URL must use HTTPS.",
        )
    if parsed.username is not None or parsed.password is not None:
        raise URLImportError(
            "unsafe_url_authority",
            "URL credentials are not allowed.",
        )
    if not parsed.hostname:
        raise URLImportError(
            "invalid_url",
            "URL hostname is required.",
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise URLImportError(
            "invalid_url",
            "URL port is invalid.",
        ) from exc
    if port not in {None, 443}:
        raise URLImportError(
            "unsafe_url_port",
            "URL must use the default HTTPS port.",
        )

    hostname = _normalized_hostname(parsed.hostname)
    if _is_forbidden_destination(hostname):
        raise URLImportError(
            "unsafe_url_destination",
            "URL destination is not public.",
        )
    path = parsed.path or "/"
    authority = _authority(hostname)
    fetch_url = urlunsplit((
        "https",
        authority,
        path,
        parsed.query,
        "",
    ))
    display_url = urlunsplit((
        "https",
        authority,
        path,
        "",
        "",
    ))
    source_ref_hash = hashlib.sha256(
        fetch_url.encode("utf-8")
    ).hexdigest()
    sensitive_tokens = tuple(dict.fromkeys(
        token
        for token in (
            parsed.query,
            *(
                value
                for _, value in parse_qsl(
                    parsed.query,
                    keep_blank_values=True,
                )
            ),
            unquote(parsed.fragment),
        )
        if token
    ))
    return ValidatedSourceURL(
        fetch_url=fetch_url,
        display_url=display_url,
        hostname=hostname,
        source_ref_hash=source_ref_hash,
        sensitive_tokens=sensitive_tokens,
    )

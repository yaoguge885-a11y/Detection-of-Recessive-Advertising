"""DNS-pinned, redirect-safe platform URL fetching boundary."""
from __future__ import annotations

import http.client
from ipaddress import ip_address
import socket
import ssl
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol
from urllib.parse import urljoin, urlsplit

from .contracts import URLImportError, ValidatedSourceURL
from .url_safety import validate_public_https_url


MAX_PAGE_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 10.0
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class ResolvedTarget:
    source: ValidatedSourceURL
    addresses: tuple[str, ...]
    connect_ip: str


@dataclass(frozen=True)
class OneHopResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class SafeFetchResult:
    body: bytes
    content_type: str | None
    display_url: str
    source_ref_hash: str


class DNSResolver(Protocol):
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        """Return numeric addresses for one normalized hostname."""


class HTTPTransport(Protocol):
    def request_once(
        self,
        *,
        url: str,
        hostname: str,
        connect_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> OneHopResponse:
        """Perform exactly one request without following redirects."""


class SocketDNSResolver:
    """Resolve a hostname without applying destination policy."""

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            records = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError as exc:
            raise URLImportError(
                "dns_resolution_failed",
                "URL destination could not be resolved.",
            ) from exc
        return tuple(dict.fromkeys(
            record[4][0] for record in records
        ))


def resolve_public_target(
    source: ValidatedSourceURL,
    resolver: DNSResolver,
) -> ResolvedTarget:
    try:
        raw_addresses = resolver.resolve(source.hostname, 443)
    except URLImportError:
        raise
    except Exception as exc:
        raise URLImportError(
            "dns_resolution_failed",
            "URL destination could not be resolved.",
        ) from exc
    if not raw_addresses:
        raise URLImportError(
            "dns_resolution_failed",
            "URL destination could not be resolved.",
        )

    parsed_addresses = []
    for value in raw_addresses:
        try:
            address = ip_address(value)
        except ValueError as exc:
            raise URLImportError(
                "dns_resolution_failed",
                "URL destination could not be resolved.",
            ) from exc
        if not address.is_global:
            raise URLImportError(
                "unsafe_url_destination",
                "URL destination is not public.",
            )
        parsed_addresses.append(address)

    addresses = tuple(
        str(item)
        for item in sorted(
            set(parsed_addresses),
            key=lambda item: (item.version, int(item)),
        )
    )
    return ResolvedTarget(
        source=source,
        addresses=addresses,
        connect_ip=addresses[0],
    )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection whose TCP peer is an already-validated numeric IP."""

    def __init__(
        self,
        hostname: str,
        connect_ip: str,
        port: int,
        timeout_seconds: float,
    ):
        super().__init__(
            hostname,
            port=port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        )
        self._connect_ip = connect_ip

    def connect(self) -> None:
        address = ip_address(self._connect_ip)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        try:
            raw_socket.settimeout(self.timeout)
            peer = (
                (self._connect_ip, self.port, 0, 0)
                if address.version == 6
                else (self._connect_ip, self.port)
            )
            raw_socket.connect(peer)
            self.sock = self._context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except Exception:
            raw_socket.close()
            raise


ConnectionFactory = Callable[
    [str, str, int, float],
    http.client.HTTPSConnection,
]


def _connection_factory(
    hostname: str,
    connect_ip: str,
    port: int,
    timeout_seconds: float,
) -> http.client.HTTPSConnection:
    return _PinnedHTTPSConnection(
        hostname,
        connect_ip,
        port,
        timeout_seconds,
    )


class PinnedHTTPSHTTPTransport:
    """One-hop HTTPS GET using a validated numeric connection peer."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory | None = None,
    ):
        self.connection_factory = connection_factory or _connection_factory

    def request_once(
        self,
        *,
        url: str,
        hostname: str,
        connect_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> OneHopResponse:
        source = validate_public_https_url(url)
        if source.hostname != hostname:
            raise URLImportError(
                "unsafe_url_destination",
                "URL destination changed before request.",
            )
        parsed = urlsplit(source.fetch_url)
        target = parsed.path or "/"
        if parsed.query:
            target += f"?{parsed.query}"
        host_header = (
            f"[{hostname}]" if ":" in hostname else hostname
        )
        connection = self.connection_factory(
            hostname,
            connect_ip,
            443,
            timeout_seconds,
        )
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Host": host_header,
                    "User-Agent": "implicit-ad-agent/0.1",
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.1",
                },
            )
            response = connection.getresponse()
            headers = {
                str(key).lower(): str(value)
                for key, value in response.getheaders()
            }
            declared = headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > max_bytes:
                        raise URLImportError(
                            "response_too_large",
                            "URL response exceeded the size limit.",
                        )
                except ValueError:
                    pass
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise URLImportError(
                    "response_too_large",
                    "URL response exceeded the size limit.",
                )
            return OneHopResponse(
                status_code=response.status,
                headers=headers,
                body=body,
            )
        finally:
            connection.close()


class SafeURLFetcher:
    """Validate, pin, and fetch one URL through bounded redirect hops."""

    def __init__(
        self,
        *,
        resolver: DNSResolver | None = None,
        transport: HTTPTransport | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = MAX_PAGE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        self.resolver = resolver or SocketDNSResolver()
        self.transport = transport or PinnedHTTPSHTTPTransport()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects

    def validate_target(self, url: str) -> ResolvedTarget:
        return resolve_public_target(
            validate_public_https_url(url),
            self.resolver,
        )

    def fetch(self, url: str) -> SafeFetchResult:
        current_url = url
        redirect_count = 0
        visited: set[str] = set()

        while True:
            try:
                target = self.validate_target(current_url)
            except URLImportError as exc:
                if redirect_count and exc.code == "invalid_url":
                    raise URLImportError(
                        "unsafe_redirect",
                        "Redirect target is invalid.",
                    ) from exc
                raise
            if target.source.source_ref_hash in visited:
                raise URLImportError(
                    "unsafe_redirect",
                    "Redirect loop was rejected.",
                )
            visited.add(target.source.source_ref_hash)

            response = self.transport.request_once(
                url=target.source.fetch_url,
                hostname=target.source.hostname,
                connect_ip=target.connect_ip,
                timeout_seconds=self.timeout_seconds,
                max_bytes=self.max_bytes,
            )
            if len(response.body) > self.max_bytes:
                raise URLImportError(
                    "response_too_large",
                    "URL response exceeded the size limit.",
                )
            headers = {
                str(key).lower(): str(value)
                for key, value in response.headers.items()
            }
            if response.status_code not in REDIRECT_STATUSES:
                return SafeFetchResult(
                    body=response.body,
                    content_type=headers.get("content-type"),
                    display_url=target.source.display_url,
                    source_ref_hash=target.source.source_ref_hash,
                )

            location = headers.get("location", "").strip()
            if not location:
                raise URLImportError(
                    "unsafe_redirect",
                    "Redirect target is invalid.",
                )
            if redirect_count >= self.max_redirects:
                raise URLImportError(
                    "redirect_limit_exceeded",
                    "URL redirect limit was exceeded.",
                )
            try:
                current_url = urljoin(target.source.fetch_url, location)
            except ValueError as exc:
                raise URLImportError(
                    "unsafe_redirect",
                    "Redirect target is invalid.",
                ) from exc
            redirect_count += 1


class DisabledURLFetcher:
    """Network-disabled default used until a real adapter is configured."""

    @staticmethod
    def _raise_disabled():
        raise URLImportError(
            "url_fetch_disabled",
            "Platform URL fetching is disabled.",
        )

    def validate_target(self, url: str) -> ResolvedTarget:
        self._raise_disabled()

    def fetch(self, url: str) -> SafeFetchResult:
        self._raise_disabled()

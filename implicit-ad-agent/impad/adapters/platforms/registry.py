"""Explicit host-to-platform-adapter registry."""
from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    PlatformAdapter,
    URLImportError,
    ValidatedSourceURL,
)


class PlatformAdapterRegistry:
    """Resolve only adapters explicitly registered for a host."""

    def __init__(
        self,
        adapters: Iterable[PlatformAdapter] = (),
    ):
        self._adapters = tuple(adapters)
        claimed_hosts = {}
        for adapter in self._adapters:
            for host in adapter.supported_hosts:
                normalized = host.lower().rstrip(".")
                if normalized in claimed_hosts:
                    raise ValueError(
                        f"duplicate platform host: {normalized}"
                    )
                claimed_hosts[normalized] = adapter
        self._claimed_hosts = claimed_hosts

    def resolve(
        self,
        source: ValidatedSourceURL,
    ) -> PlatformAdapter:
        matches = [
            (host, adapter)
            for host, adapter in self._claimed_hosts.items()
            if (
                source.hostname == host
                or source.hostname.endswith("." + host)
            )
        ]
        if not matches:
            raise URLImportError(
                "unsupported_url_host",
                "No registered platform adapter supports this URL.",
            )
        return max(matches, key=lambda item: len(item[0]))[1]

    @property
    def adapters(self) -> tuple[PlatformAdapter, ...]:
        return self._adapters

from __future__ import annotations

import pytest

from impad.adapters.platforms import (
    PlatformAdapterRegistry,
    URLImportError,
    validate_public_https_url,
)


class StaticAdapter:
    name = "static"
    version = "1"
    platform = "fixture"
    supported_hosts = ("example.test",)

    def preview(self, source):
        raise AssertionError("not used by registry resolution")


def test_registry_matches_exact_host_and_subdomain():
    registry = PlatformAdapterRegistry([StaticAdapter()])

    assert registry.resolve(
        validate_public_https_url("https://example.test/a")
    ).name == "static"
    assert registry.resolve(
        validate_public_https_url("https://www.example.test/a")
    ).name == "static"


def test_registry_rejects_unsupported_host():
    registry = PlatformAdapterRegistry([StaticAdapter()])

    with pytest.raises(
        URLImportError,
        match="No registered platform adapter",
    ) as exc:
        registry.resolve(
            validate_public_https_url("https://other.test/a")
        )

    assert exc.value.code == "unsupported_url_host"


def test_registry_rejects_duplicate_claimed_hosts():
    with pytest.raises(ValueError, match="duplicate platform host"):
        PlatformAdapterRegistry([StaticAdapter(), StaticAdapter()])


def test_empty_registry_reports_no_adapters():
    registry = PlatformAdapterRegistry()

    assert registry.adapters == ()

from __future__ import annotations

import pytest

from impad.adapters.platforms import (
    URLImportError,
    validate_public_https_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/post/1",
        "https://user:pass@example.test/post/1",
        "https://example.test:8443/post/1",
        "https://localhost/post/1",
        "https://sub.localhost/post/1",
        "https://service.local/post/1",
        "https://service.internal/post/1",
        "https://127.0.0.1/post/1",
        "https://10.0.0.1/post/1",
        "https://169.254.1.1/post/1",
        "https://[::1]/post/1",
    ],
)
def test_url_validator_rejects_unsafe_destinations(url):
    with pytest.raises(URLImportError, match="URL"):
        validate_public_https_url(url)


def test_url_validator_keeps_fetch_query_but_hides_display_query():
    result = validate_public_https_url(
        "https://EXAMPLE.test/post/1?token=secret#fragment"
    )

    assert result.fetch_url == (
        "https://example.test/post/1?token=secret"
    )
    assert result.display_url == "https://example.test/post/1"
    assert result.hostname == "example.test"
    assert len(result.source_ref_hash) == 64
    assert result.sensitive_tokens == ("token=secret", "fragment")


def test_url_validator_normalizes_default_port_and_empty_path():
    result = validate_public_https_url("https://example.test:443")

    assert result.fetch_url == "https://example.test/"
    assert result.display_url == "https://example.test/"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https:///missing-host",
        "https://example.test:invalid/post",
    ],
)
def test_url_validator_rejects_malformed_urls(url):
    with pytest.raises(URLImportError):
        validate_public_https_url(url)

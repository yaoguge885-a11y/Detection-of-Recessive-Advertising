from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from impad.adapters.platforms import URLImportError
from impad.adapters.platforms.safe_fetch import (
    MAX_PAGE_BYTES,
    OneHopResponse,
    PinnedHTTPSHTTPTransport,
    SafeURLFetcher,
)


@dataclass
class FakeResolver:
    answers: dict[str, tuple[str, ...]]
    calls: list[str] = field(default_factory=list)

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        assert port == 443
        self.calls.append(hostname)
        return self.answers.get(hostname, ())


@dataclass
class FakeTransport:
    responses: dict[str, OneHopResponse]
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def request_once(
        self,
        *,
        url: str,
        hostname: str,
        connect_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> OneHopResponse:
        assert timeout_seconds == 10.0
        assert max_bytes == MAX_PAGE_BYTES
        self.calls.append((url, hostname, connect_ip))
        return self.responses[url]


class FakeHTTPResponse:
    def __init__(self, *, status: int, headers: dict[str, str], body: bytes):
        self.status = status
        self._headers = headers
        self._body = body

    def getheaders(self):
        return list(self._headers.items())

    def read(self, amount: int):
        return self._body[:amount]


class RecordingConnection:
    def __init__(self, response: FakeHTTPResponse):
        self.response = response
        self.method = None
        self.request_target = None
        self.headers = None
        self.closed = False

    def request(self, method: str, target: str, *, headers: dict[str, str]):
        self.method = method
        self.request_target = target
        self.headers = headers

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class RecordingConnectionFactory:
    def __init__(self, response: FakeHTTPResponse):
        self.calls = []
        self.connection = RecordingConnection(response)

    def __call__(
        self,
        hostname: str,
        connect_ip: str,
        port: int,
        timeout_seconds: float,
    ):
        self.calls.append((hostname, connect_ip, port, timeout_seconds))
        return self.connection


def test_redirect_revalidates_and_pins_each_public_target():
    resolver = FakeResolver({
        "first.test": ("93.184.216.34",),
        "second.test": ("142.250.72.14",),
    })
    transport = FakeTransport({
        "https://first.test/start": OneHopResponse(
            status_code=302,
            headers={"Location": "https://second.test/final"},
            body=b"",
        ),
        "https://second.test/final": OneHopResponse(
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=b"ok",
        ),
    })

    result = SafeURLFetcher(
        resolver=resolver,
        transport=transport,
    ).fetch("https://first.test/start")

    assert result.body == b"ok"
    assert result.content_type == "text/html; charset=utf-8"
    assert result.display_url == "https://second.test/final"
    assert resolver.calls == ["first.test", "second.test"]
    assert transport.calls == [
        (
            "https://first.test/start",
            "first.test",
            "93.184.216.34",
        ),
        (
            "https://second.test/final",
            "second.test",
            "142.250.72.14",
        ),
    ]


@pytest.mark.parametrize(
    "answers",
    [
        ("127.0.0.1",),
        ("10.0.0.8",),
        ("169.254.10.1",),
        ("::1",),
        ("fc00::1",),
        ("93.184.216.34", "10.0.0.8"),
    ],
)
def test_dns_rejects_any_non_global_or_mixed_answer_before_io(answers):
    resolver = FakeResolver({"public.test": answers})
    transport = FakeTransport({})

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/post")

    assert exc.value.code == "unsafe_url_destination"
    assert transport.calls == []


def test_empty_dns_answer_fails_before_io():
    transport = FakeTransport({})

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=FakeResolver({}),
            transport=transport,
        ).fetch("https://missing.test/post")

    assert exc.value.code == "dns_resolution_failed"
    assert transport.calls == []


def test_redirect_to_private_literal_fails_before_second_request():
    resolver = FakeResolver({"public.test": ("93.184.216.34",)})
    transport = FakeTransport({
        "https://public.test/start": OneHopResponse(
            status_code=302,
            headers={
                "location": "https://127.0.0.1/admin?token=redirect-secret"
            },
            body=b"",
        ),
    })

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/start")

    assert exc.value.code == "unsafe_url_destination"
    assert len(transport.calls) == 1
    assert "redirect-secret" not in exc.value.message


def test_redirect_dns_change_to_private_fails_before_second_request():
    resolver = FakeResolver({
        "public.test": ("93.184.216.34",),
        "rebound.test": ("10.0.0.9",),
    })
    transport = FakeTransport({
        "https://public.test/start": OneHopResponse(
            status_code=302,
            headers={"location": "https://rebound.test/metadata"},
            body=b"",
        ),
    })

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/start")

    assert exc.value.code == "unsafe_url_destination"
    assert len(transport.calls) == 1
    assert resolver.calls == ["public.test", "rebound.test"]


@pytest.mark.parametrize(
    "location,expected_code",
    [
        ("https://user:pass@second.test/post", "unsafe_url_authority"),
        ("https://second.test:8443/post", "unsafe_url_port"),
        ("https://[broken", "unsafe_redirect"),
        ("", "unsafe_redirect"),
    ],
)
def test_unsafe_redirect_metadata_fails_closed(location, expected_code):
    resolver = FakeResolver({"public.test": ("93.184.216.34",)})
    transport = FakeTransport({
        "https://public.test/start": OneHopResponse(
            status_code=302,
            headers={"location": location},
            body=b"",
        ),
    })

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/start")

    assert exc.value.code == expected_code
    assert len(transport.calls) == 1
    if location:
        assert location not in exc.value.message


def test_redirect_loop_fails_without_repeating_request():
    resolver = FakeResolver({"public.test": ("93.184.216.34",)})
    transport = FakeTransport({
        "https://public.test/start": OneHopResponse(
            status_code=302,
            headers={"location": "/start"},
            body=b"",
        ),
    })

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/start")

    assert exc.value.code == "unsafe_redirect"
    assert len(transport.calls) == 1


def test_sixth_redirect_is_rejected_after_five_redirects():
    resolver = FakeResolver({
        f"hop{index}.test": (f"8.8.8.{index + 1}",)
        for index in range(7)
    })
    responses = {
        f"https://hop{index}.test/post": OneHopResponse(
            status_code=302,
            headers={"location": f"https://hop{index + 1}.test/post"},
            body=b"",
        )
        for index in range(6)
    }
    transport = FakeTransport(responses)

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://hop0.test/post")

    assert exc.value.code == "redirect_limit_exceeded"
    assert len(transport.calls) == 6


def test_response_over_five_mib_is_rejected():
    resolver = FakeResolver({"public.test": ("93.184.216.34",)})
    transport = FakeTransport({
        "https://public.test/post": OneHopResponse(
            status_code=200,
            headers={},
            body=b"x" * (MAX_PAGE_BYTES + 1),
        ),
    })

    with pytest.raises(URLImportError) as exc:
        SafeURLFetcher(
            resolver=resolver,
            transport=transport,
        ).fetch("https://public.test/post")

    assert exc.value.code == "response_too_large"


def test_fetch_query_is_used_but_display_and_fragment_are_hidden():
    resolver = FakeResolver({"public.test": ("93.184.216.34",)})
    fetch_url = "https://public.test/post?token=query-secret"
    transport = FakeTransport({
        fetch_url: OneHopResponse(
            status_code=200,
            headers={},
            body=b"ok",
        ),
    })

    result = SafeURLFetcher(
        resolver=resolver,
        transport=transport,
    ).fetch(fetch_url + "#fragment-secret")

    assert transport.calls[0][0] == fetch_url
    assert result.display_url == "https://public.test/post"
    assert "query-secret" not in repr(result)
    assert "fragment-secret" not in repr(result)


def test_pinned_https_transport_uses_validated_ip_and_original_tls_host():
    factory = RecordingConnectionFactory(FakeHTTPResponse(
        status=200,
        headers={"Content-Type": "text/html"},
        body=b"ok",
    ))
    transport = PinnedHTTPSHTTPTransport(connection_factory=factory)

    response = transport.request_once(
        url="https://platform.test/post?id=1",
        hostname="platform.test",
        connect_ip="93.184.216.34",
        timeout_seconds=10.0,
        max_bytes=MAX_PAGE_BYTES,
    )

    assert response.body == b"ok"
    assert factory.calls == [(
        "platform.test",
        "93.184.216.34",
        443,
        10.0,
    )]
    assert factory.connection.method == "GET"
    assert factory.connection.request_target == "/post?id=1"
    assert factory.connection.headers["Host"] == "platform.test"
    assert factory.connection.closed is True


def test_pinned_https_transport_stops_reading_after_size_limit():
    factory = RecordingConnectionFactory(FakeHTTPResponse(
        status=200,
        headers={},
        body=b"x" * (MAX_PAGE_BYTES + 1),
    ))

    with pytest.raises(URLImportError) as exc:
        PinnedHTTPSHTTPTransport(
            connection_factory=factory,
        ).request_once(
            url="https://platform.test/post",
            hostname="platform.test",
            connect_ip="93.184.216.34",
            timeout_seconds=10.0,
            max_bytes=MAX_PAGE_BYTES,
        )

    assert exc.value.code == "response_too_large"
    assert factory.connection.closed is True

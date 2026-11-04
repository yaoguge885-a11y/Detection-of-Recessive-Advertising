from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from impad.adapters.platforms import (
    OneHopResponse,
    SafeURLFetcher,
    URLImportError,
)
import impad.adapters.platforms.media_safety as media_safety_module
from impad.adapters.platforms.media_safety import PlatformMediaPolicy
from impad.contracts import MediaRecord


class FakeValidatingFetcher:
    def __init__(
        self,
        display_url: str = "https://cdn.example.test/image.jpg",
    ):
        self.display_url = display_url
        self.calls = []

    def validate_target(self, url: str):
        self.calls.append(url)
        return SimpleNamespace(source=SimpleNamespace(
            display_url=self.display_url,
        ))


class PrivateResolver:
    def resolve(self, hostname: str, port: int):
        return ("10.0.0.7",)


class FailIfCalledTransport:
    def request_once(self, **kwargs) -> OneHopResponse:
        raise AssertionError("media validation must not fetch the resource")


@pytest.mark.parametrize(
    "ref",
    [
        "../outside.jpg",
        "/etc/passwd",
        "C:/Windows/System32/config/SAM",
        r"\\server\share\secret.jpg",
        r"\\?\C:\secret.jpg",
        "safe.jpg:alternate",
        "file:///etc/passwd",
        "data:image/png;base64,AAAA",
        "javascript:alert(1)",
        "ftp://example.test/file.jpg",
        "bad\x00name.jpg",
        "bad\nname.jpg",
    ],
)
def test_platform_media_rejects_unsafe_references(tmp_path: Path, ref: str):
    policy = PlatformMediaPolicy(
        fetcher=FakeValidatingFetcher(),
        cache_root=tmp_path / "cache",
    )

    with pytest.raises(URLImportError) as exc:
        policy.normalize([MediaRecord(
            media_id="media-1",
            type="image",
            ref=ref,
        )])

    assert exc.value.code == "unsafe_media_reference"
    assert ref not in exc.value.message


def test_platform_media_allows_and_normalizes_in_root_cache_path(tmp_path):
    root = tmp_path / "cache"
    root.mkdir()
    policy = PlatformMediaPolicy(
        fetcher=FakeValidatingFetcher(),
        cache_root=root,
    )

    result = policy.normalize([MediaRecord(
        media_id="media-1",
        type="image",
        ref="post-1\\image.jpg",
    )])

    assert result[0].ref == "post-1/image.jpg"


def test_platform_media_stores_only_safe_remote_display_url(tmp_path):
    fetcher = FakeValidatingFetcher(
        display_url="https://cdn.example.test/image.jpg"
    )
    result = PlatformMediaPolicy(
        fetcher=fetcher,
        cache_root=None,
    ).normalize([MediaRecord(
        media_id="media-1",
        type="image",
        ref="https://cdn.example.test/image.jpg?token=media-secret#frag",
    )])

    assert result[0].ref == "https://cdn.example.test/image.jpg"
    assert fetcher.calls == [
        "https://cdn.example.test/image.jpg?token=media-secret#frag"
    ]
    assert "media-secret" not in result[0].model_dump_json()


def test_platform_media_rejects_remote_private_destination():
    fetcher = SafeURLFetcher(
        resolver=PrivateResolver(),
        transport=FailIfCalledTransport(),
    )
    policy = PlatformMediaPolicy(fetcher=fetcher, cache_root=None)

    with pytest.raises(URLImportError) as exc:
        policy.normalize([MediaRecord(
            media_id="media-1",
            type="image",
            ref="https://private.example.test/image.jpg?token=secret",
        )])

    assert exc.value.code == "unsafe_media_reference"
    assert "secret" not in exc.value.message


def test_platform_media_rejects_local_ref_without_cache_root():
    policy = PlatformMediaPolicy(
        fetcher=FakeValidatingFetcher(),
        cache_root=None,
    )

    with pytest.raises(URLImportError) as exc:
        policy.normalize([MediaRecord(
            media_id="media-1",
            type="image",
            ref="post/image.jpg",
        )])

    assert exc.value.code == "unsafe_media_reference"


def test_platform_media_preserves_explicit_missing_reference():
    media = MediaRecord(media_id="media-1", type="image", ref=None)

    result = PlatformMediaPolicy(
        fetcher=FakeValidatingFetcher(),
        cache_root=None,
    ).normalize([media])

    assert result == [media]


def test_platform_media_rejects_unsupported_media_type(tmp_path):
    with pytest.raises(URLImportError) as exc:
        PlatformMediaPolicy(
            fetcher=FakeValidatingFetcher(),
            cache_root=tmp_path,
        ).normalize([MediaRecord(
            media_id="media-1",
            type="archive",
            ref="payload.zip",
        )])

    assert exc.value.code == "unsafe_media_reference"


def test_platform_media_rejects_resolved_symlink_escape(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cache"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    def resolve_path(path):
        if "linked" in path.parts:
            return outside / "secret.jpg"
        return path.resolve(strict=False)

    monkeypatch.setattr(
        media_safety_module,
        "_resolve_path",
        resolve_path,
    )

    with pytest.raises(URLImportError) as caught:
        PlatformMediaPolicy(
            fetcher=FakeValidatingFetcher(),
            cache_root=root,
        ).normalize([MediaRecord(
            media_id="media-1",
            type="image",
            ref="linked/secret.jpg",
        )])

    assert caught.value.code == "unsafe_media_reference"


def test_platform_media_rejects_overlong_reference(tmp_path):
    with pytest.raises(URLImportError) as exc:
        PlatformMediaPolicy(
            fetcher=FakeValidatingFetcher(),
            cache_root=tmp_path,
        ).normalize([MediaRecord(
            media_id="media-1",
            type="image",
            ref="x" * 2049,
        )])

    assert exc.value.code == "unsafe_media_reference"

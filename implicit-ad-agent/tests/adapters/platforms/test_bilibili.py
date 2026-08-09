"""Deterministic synthetic Bilibili fixture adapter tests."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from impad.adapters.platforms import validate_public_https_url
from impad.adapters.platforms.bilibili import (
    BilibiliAdapter,
    content_type_from_url,
    parse_bilibili_state,
)
from impad.contracts import PostRecord


FIXTURE_ROOT = (
    Path(__file__).parents[2] / "fixtures" / "platforms" / "bilibili"
)


def _fixture(case: str) -> Path:
    return FIXTURE_ROOT / case


@pytest.mark.parametrize(
    ("case", "content_type"),
    [
        ("video_no_images", "video"),
        ("opus_partial_images", "opus"),
        ("article_missing_disclosure_surface", "article"),
    ],
)
def test_bilibili_fixture_matches_expected_post(case, content_type):
    fixture = _fixture(case)
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    first = parse_bilibili_state(
        state,
        content_type=content_type,
        source_ref_hash="b" * 64,
    )
    second = parse_bilibili_state(
        state,
        content_type=content_type,
        source_ref_hash="b" * 64,
    )

    assert first == expected
    assert first.model_dump_json() == second.model_dump_json()
    assert first.capture_status.modalities["comment"].status == "unsupported"


def test_bilibili_rejects_unknown_fixture_content_type():
    with pytest.raises(ValueError, match="unsupported Bilibili content type"):
        parse_bilibili_state(
            {},
            content_type="live",
            source_ref_hash="b" * 64,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/video/BV_SYNTHETIC_001",
        "https://www.bilibili.com/opus/bili_opus_001",
        "https://t.bilibili.com/123456",
        "https://www.bilibili.com/read/cv123456",
    ],
)
def test_bilibili_content_type_from_supported_urls(url):
    assert content_type_from_url(url) in {"video", "opus", "article"}


@pytest.mark.parametrize(
    "url",
    [
        "https://www.bilibili.com/",
        "https://www.bilibili.com/space/123",
        "https://b23.tv/abc",
    ],
)
def test_bilibili_rejects_unknown_url_path(url):
    with pytest.raises(ValueError, match="unsupported Bilibili content type"):
        content_type_from_url(url)


@dataclass
class _FixtureFetchResult:
    body: bytes
    source_ref_hash: str = "c" * 64


class FixtureFetcher:
    """Inject fixture bytes; no network implementation exists in this test."""

    def __init__(self, path: Path):
        self.path = path
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FixtureFetchResult:
        self.calls.append(url)
        return _FixtureFetchResult(self.path.read_bytes())


def test_bilibili_adapter_reads_injected_html_without_network():
    url = "https://www.bilibili.com/video/BV_SYNTHETIC_001"
    fetcher = FixtureFetcher(_fixture("video_no_images") / "source.html")
    adapter = BilibiliAdapter()

    post = adapter.preview(
        validate_public_https_url(url),
        fetcher=fetcher,
    )

    assert fetcher.calls == [url]
    assert post.platform == "bilibili"
    assert post.provenance.source_ref_hash == "c" * 64


@pytest.mark.parametrize(
    ("case", "content_type", "url"),
    [
        (
            "video_no_images",
            "video",
            "https://www.bilibili.com/video/BV_SYNTHETIC_001",
        ),
        (
            "opus_partial_images",
            "opus",
            "https://www.bilibili.com/opus/bili_opus_001",
        ),
        (
            "article_missing_disclosure_surface",
            "article",
            "https://www.bilibili.com/read/cv123456",
        ),
    ],
)
def test_bilibili_adapter_preview_matches_each_json_fixture(
    case, content_type, url
):
    fixture = _fixture(case)
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    post = BilibiliAdapter().preview(
        validate_public_https_url(url),
        fetcher=FixtureFetcher(fixture / "source.html"),
    )
    expected = expected.model_copy(update={
        "provenance": expected.provenance.model_copy(update={
            "source_ref_hash": "c" * 64,
        }),
    })

    assert post == expected
    assert post.model_dump_json() == parse_bilibili_state(
        json.loads((fixture / "source_state.json").read_text("utf-8")),
        content_type=content_type,
        source_ref_hash="c" * 64,
    ).model_dump_json()


def test_bilibili_video_image_capture_is_unsupported_with_stable_issue():
    fixture = _fixture("video_no_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))

    post = parse_bilibili_state(
        state,
        content_type="video",
        source_ref_hash="b" * 64,
    )

    modality = post.capture_status.modalities["image"]
    assert modality.status == "unsupported"
    assert modality.issues == ["image_unsupported"]
    assert modality.missing_fields == []


def test_bilibili_comments_are_explicitly_unsupported():
    fixture = _fixture("video_no_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))

    post = parse_bilibili_state(
        state,
        content_type="video",
        source_ref_hash="b" * 64,
    )

    modality = post.capture_status.modalities["comment"]
    assert modality.status == "unsupported"
    assert modality.issues == ["comments_unsupported"]
    assert modality.missing_fields == []


def test_bilibili_media_filters_empty_and_duplicate_refs_using_source_index():
    fixture = _fixture("opus_partial_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["opusModule"]["pictures"] = [
        {"url": "https://media.example.test/bilibili/image-a.jpg"},
        {"url": ""},
        {"url": None},
        {"url": "https://media.example.test/bilibili/image-a.jpg"},
        {"url": "https://media.example.test/bilibili/image-b.jpg"},
    ]

    post = parse_bilibili_state(
        state,
        content_type="opus",
        source_ref_hash="b" * 64,
    )

    assert [item.ref for item in post.media] == [
        "https://media.example.test/bilibili/image-a.jpg",
        "https://media.example.test/bilibili/image-b.jpg",
    ]
    assert [item.media_id for item in post.media] == [
        "bilibili_opus_image_0",
        "bilibili_opus_image_4",
    ]
    assert post.text.endswith("<图片1>\n<图片5>")
    modality = post.capture_status.modalities["image"]
    assert modality.status == "partial"
    assert modality.issues == ["image_ref_partial", "remote_image"]
    assert modality.missing_fields == ["media.ref", "local_media.ref"]


def test_bilibili_empty_image_refs_are_missing_without_media_placeholders():
    fixture = _fixture("opus_partial_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["opusModule"]["pictures"] = [{"url": ""}, {"url": None}]

    post = parse_bilibili_state(
        state,
        content_type="opus",
        source_ref_hash="b" * 64,
    )

    assert post.media == []
    assert "<图片" not in post.text
    modality = post.capture_status.modalities["image"]
    assert modality.status == "missing"
    assert modality.issues == ["image_ref_missing"]
    assert modality.missing_fields == ["media.ref"]


def test_bilibili_empty_text_is_missing_with_fact_field():
    fixture = _fixture("opus_partial_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["opusModule"]["title"] = ""
    state["opusModule"]["description"] = ""
    state["opusModule"]["pictures"] = []

    post = parse_bilibili_state(
        state,
        content_type="opus",
        source_ref_hash="b" * 64,
    )

    modality = post.capture_status.modalities["text"]
    assert post.text == ""
    assert modality.status == "missing"
    assert modality.issues == ["empty_text"]
    assert modality.missing_fields == ["text"]


def test_bilibili_article_disclosure_surface_missing_is_audited():
    fixture = _fixture("article_missing_disclosure_surface")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))

    post = parse_bilibili_state(
        state,
        content_type="article",
        source_ref_hash="b" * 64,
    )

    modality = post.capture_status.modalities["disclosure"]
    assert modality.status == "missing"
    assert modality.issues == ["disclosure_surface_missing"]
    assert modality.missing_fields == ["disclosures"]


def test_bilibili_disclosures_deduplicate_by_kind_text_source():
    fixture = _fixture("video_no_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["videoData"]["disclosureLabels"] = ["赞助", "赞助"]

    post = parse_bilibili_state(
        state,
        content_type="video",
        source_ref_hash="b" * 64,
    )

    assert [item.model_dump() for item in post.disclosures] == [
        {
            "kind": "platform_badge",
            "text": "赞助",
            "source": "platform_metadata",
        },
    ]


def test_bilibili_missing_disclosure_labels_are_audited():
    fixture = _fixture("opus_partial_images")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["opusModule"].pop("disclosureLabels")

    post = parse_bilibili_state(
        state,
        content_type="opus",
        source_ref_hash="b" * 64,
    )

    modality = post.capture_status.modalities["disclosure"]
    assert modality.status == "missing"
    assert modality.issues == ["disclosure_missing"]
    assert modality.missing_fields == ["disclosures"]


@pytest.mark.parametrize(
    ("case", "content_type", "path", "message"),
    [
        ("video_no_images", "video", "videoData", "bvid"),
        ("opus_partial_images", "opus", "opusModule", "dynamic_id"),
        ("article_missing_disclosure_surface", "article", "readInfo", "cv_id"),
    ],
)
def test_bilibili_parser_rejects_missing_native_id(
    case, content_type, path, message
):
    state = json.loads((_fixture(case) / "source_state.json").read_text("utf-8"))
    state[path]["bvid" if content_type == "video" else "dynamic_id" if content_type == "opus" else "id"] = ""

    with pytest.raises(ValueError, match=message):
        parse_bilibili_state(
            state,
            content_type=content_type,
            source_ref_hash="b" * 64,
        )


@pytest.mark.parametrize(
    ("case", "content_type", "path"),
    [
        ("video_no_images", "video", "videoData"),
        ("opus_partial_images", "opus", "opusModule"),
        ("article_missing_disclosure_surface", "article", "readInfo"),
    ],
)
def test_bilibili_parser_rejects_missing_creator_id(case, content_type, path):
    state = json.loads((_fixture(case) / "source_state.json").read_text("utf-8"))
    state[path]["owner" if content_type == "video" else "author"] = {}

    with pytest.raises(ValueError, match="creator_id"):
        parse_bilibili_state(
            state,
            content_type=content_type,
            source_ref_hash="b" * 64,
        )


@pytest.mark.parametrize(
    ("content_type", "state_key"),
    [("video", "videoData"), ("opus", "opusModule"), ("article", "readInfo")],
)
def test_bilibili_parser_requires_matching_state_key(content_type, state_key):
    fixture_case = {
        "video": "video_no_images",
        "opus": "opus_partial_images",
        "article": "article_missing_disclosure_surface",
    }[content_type]
    state = json.loads(
        (_fixture(fixture_case) / "source_state.json").read_text("utf-8")
    )
    state.pop(state_key)

    with pytest.raises(ValueError, match=state_key):
        parse_bilibili_state(
            state,
            content_type=content_type,
            source_ref_hash="b" * 64,
        )


def test_bilibili_parser_does_not_fallback_between_branches():
    state = json.loads(
        (_fixture("video_no_images") / "source_state.json").read_text("utf-8")
    )

    with pytest.raises(ValueError, match="opusModule"):
        parse_bilibili_state(
            state,
            content_type="opus",
            source_ref_hash="b" * 64,
        )

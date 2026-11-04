"""Deterministic synthetic Xiaohongshu fixture adapter tests."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from impad.adapters.platforms import validate_public_https_url
from impad.adapters.platforms.xiaohongshu import (
    XiaohongshuAdapter,
    parse_xiaohongshu_state,
)
from impad.contracts import PostRecord


FIXTURE_ROOT = (
    Path(__file__).parents[2] / "fixtures" / "platforms" / "xiaohongshu"
)


def _fixture(case: str) -> Path:
    return FIXTURE_ROOT / case


@pytest.mark.parametrize(
    "case",
    ["normal_complete", "video_missing_comments"],
)
def test_xiaohongshu_fixture_matches_expected_post(case):
    fixture = _fixture(case)
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )

    first = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)
    second = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert first == expected
    assert first.model_dump_json() == second.model_dump_json()


@dataclass
class _FixtureFetchResult:
    body: bytes
    source_ref_hash: str = "b" * 64


class FixtureFetcher:
    """Inject fixture bytes; no network implementation exists in this test."""

    def __init__(self, path: Path):
        self.path = path
        self.calls: list[str] = []

    def fetch(self, url: str) -> _FixtureFetchResult:
        self.calls.append(url)
        return _FixtureFetchResult(self.path.read_bytes())


def test_xiaohongshu_adapter_reads_injected_html_without_network():
    url = "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
    fetcher = FixtureFetcher(_fixture("normal_complete") / "source.html")
    adapter = XiaohongshuAdapter()

    post = adapter.preview(
        validate_public_https_url(url),
        fetcher=fetcher,
    )

    assert fetcher.calls == [url]
    assert post.platform == "xiaohongshu"
    assert post.provenance.source_ref_hash == "b" * 64


def test_xiaohongshu_adapter_preview_matches_json_parser_output():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    adapter = XiaohongshuAdapter()
    post = adapter.preview(
        validate_public_https_url(
            "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
        ),
        fetcher=FixtureFetcher(fixture / "source.html"),
    )

    expected = expected.model_copy(update={
        "provenance": expected.provenance.model_copy(update={
            "source_ref_hash": "b" * 64,
        }),
    })
    assert post == expected
    assert post.model_dump_json() == adapter.preview(
        validate_public_https_url(
            "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
        ),
        fetcher=FixtureFetcher(fixture / "source.html"),
    ).model_dump_json()


@pytest.mark.parametrize(
    "case",
    ["normal_complete", "video_missing_comments"],
)
def test_xiaohongshu_html_preview_matches_each_json_fixture(case):
    fixture = _fixture(case)
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    expected = PostRecord.model_validate_json(
        (fixture / "expected_post.json").read_text("utf-8")
    )
    expected = expected.model_copy(update={
        "provenance": expected.provenance.model_copy(update={
            "source_ref_hash": "b" * 64,
        }),
    })
    post = XiaohongshuAdapter().preview(
        validate_public_https_url(
            "https://www.xiaohongshu.com/explore/xhs_note_normal_001"
            if case == "normal_complete"
            else "https://www.xiaohongshu.com/explore/xhs_note_video_001"
        ),
        fetcher=FixtureFetcher(fixture / "source.html"),
    )

    assert post == expected
    assert post.model_dump_json() == parse_xiaohongshu_state(
        state,
        source_ref_hash="b" * 64,
    ).model_dump_json()


def test_xiaohongshu_comment_status_compares_declared_count():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["interactInfo"]["commentCount"] = 3
    note["comments"] = [note["comments"][0]]

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    modality = post.capture_status.modalities["comment"]
    assert len(post.comments) == 1
    assert modality.status == "partial"
    assert modality.issues == ["comments_partial"]
    assert modality.missing_fields == ["comments"]


def test_xiaohongshu_zero_declared_comments_are_complete_without_issues():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["interactInfo"]["commentCount"] = 0
    note["comments"] = []

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    modality = post.capture_status.modalities["comment"]
    assert modality.status == "complete"
    assert modality.issues == []
    assert modality.missing_fields == []


def test_xiaohongshu_declared_comments_without_rows_are_missing():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["interactInfo"]["commentCount"] = 3
    note["comments"] = []

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    modality = post.capture_status.modalities["comment"]
    assert post.comments == []
    assert modality.status == "missing"
    assert modality.issues == ["comments_missing"]
    assert modality.missing_fields == ["comments"]


def test_xiaohongshu_duplicate_comment_ids_keep_first_source_row():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    first = note["comments"][0]
    note["interactInfo"]["commentCount"] = 2
    note["comments"] = [
        first,
        {**first, "content": "later duplicate", "likeCount": 99},
        {**first, "id": "xhs_comment_002", "content": "second"},
    ]

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert [item.comment_id for item in post.comments] == [
        "xhs_comment_001",
        "xhs_comment_002",
    ]
    assert post.comments[0].text == "Synthetic comment"
    assert post.capture_status.modalities["comment"].status == "complete"
    assert post.capture_status.modalities["comment"].issues == []


def test_xiaohongshu_media_filters_empty_and_duplicate_refs_using_source_index():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["imageList"] = [
        {"urlDefault": "https://media.example.test/xhs/image-a.jpg"},
        {"urlDefault": ""},
        {"urlDefault": None},
        {"urlDefault": "https://media.example.test/xhs/image-a.jpg"},
        {"urlDefault": "https://media.example.test/xhs/image-b.jpg"},
    ]

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert [item.ref for item in post.media] == [
        "https://media.example.test/xhs/image-a.jpg",
        "https://media.example.test/xhs/image-b.jpg",
    ]
    assert [item.media_id for item in post.media] == [
        "xiaohongshu_image_0",
        "xiaohongshu_image_4",
    ]
    assert post.text.endswith("<图片1>\n<图片5>")
    modality = post.capture_status.modalities["image"]
    assert modality.status == "partial"
    assert modality.issues == ["image_ref_partial", "remote_image"]
    assert modality.missing_fields == ["media.ref", "local_media.ref"]


def test_xiaohongshu_empty_image_refs_are_missing_without_media_placeholders():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["imageList"] = [{"urlDefault": ""}, {"urlDefault": None}]

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert post.media == []
    assert "<图片" not in post.text
    modality = post.capture_status.modalities["image"]
    assert modality.status == "missing"
    assert modality.issues == ["image_ref_missing"]
    assert modality.missing_fields == ["media.ref"]


def test_xiaohongshu_empty_image_list_is_missing_without_media_placeholders():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["imageList"] = []

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert post.media == []
    modality = post.capture_status.modalities["image"]
    assert modality.status == "missing"
    assert modality.issues == ["image_ref_missing"]
    assert modality.missing_fields == ["media.ref"]


def test_xiaohongshu_empty_text_is_missing_with_fact_field():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["title"] = ""
    note["desc"] = ""

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    modality = post.capture_status.modalities["text"]
    assert post.text == "<图片1>"
    assert modality.status == "missing"
    assert modality.issues == ["empty_text"]
    assert modality.missing_fields == ["text"]


def test_xiaohongshu_disclosures_deduplicate_by_kind_text_source():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["disclosureLabels"] = ["品牌合作", "品牌合作"]
    note["desc"] = "Synthetic fixture body #品牌合作 #品牌合作"

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    assert [item.model_dump() for item in post.disclosures] == [
        {
            "kind": "platform_badge",
            "text": "品牌合作",
            "source": "platform_metadata",
        },
        {
            "kind": "hashtag",
            "text": "#品牌合作",
            "source": "post_text",
        },
    ]


def test_xiaohongshu_missing_disclosure_labels_are_audited():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note.pop("disclosureLabels")

    post = parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

    modality = post.capture_status.modalities["disclosure"]
    assert modality.status == "missing"
    assert modality.issues == ["disclosure_missing"]
    assert modality.missing_fields == ["disclosures"]


def test_xiaohongshu_parser_rejects_missing_note_id():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note.pop("noteId")

    with pytest.raises(ValueError, match="noteId"):
        parse_xiaohongshu_state(state, source_ref_hash="a" * 64)


def test_xiaohongshu_parser_rejects_missing_creator_id():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    note = next(iter(state["note"]["noteDetailMap"].values()))["note"]
    note["user"] = {}

    with pytest.raises(ValueError, match="userId"):
        parse_xiaohongshu_state(state, source_ref_hash="a" * 64)


def test_xiaohongshu_parser_requires_exactly_one_note():
    fixture = _fixture("normal_complete")
    state = json.loads((fixture / "source_state.json").read_text("utf-8"))
    state["note"]["noteDetailMap"]["extra"] = copy.deepcopy(
        next(iter(state["note"]["noteDetailMap"].values()))
    )

    with pytest.raises(ValueError, match="exactly one note"):
        parse_xiaohongshu_state(state, source_ref_hash="a" * 64)

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

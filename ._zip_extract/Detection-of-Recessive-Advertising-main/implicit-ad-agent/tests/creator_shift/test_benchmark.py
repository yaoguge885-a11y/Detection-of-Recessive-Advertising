from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from impad.creator_shift import (
    CreatorShiftBenchmarkFixture,
    run_creator_shift_benchmark,
)


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "creator_shift_eval_v1.json"
)


def _fixture() -> CreatorShiftBenchmarkFixture:
    return CreatorShiftBenchmarkFixture.model_validate_json(
        FIXTURE.read_text(encoding="utf-8")
    )


def test_benchmark_is_version_hash_and_method_bound():
    fixture = _fixture()

    report = run_creator_shift_benchmark(fixture)

    assert report.benchmark_version == "synthetic-creator-shift-v1"
    assert report.feature_version == "keyword_weights_v1"
    assert report.runtime_version == "creator_shift_runtime_v1"
    assert len(report.fixture_sha256) == 64
    assert report.methods == ["mean", "max", "ema"]
    assert report.case_count == 4
    assert len(report.cases) == 12
    assert report.minimum_history == 3
    assert report.ema_alpha == 0.5
    assert report.status_counts == {
        "sufficient": 6,
        "insufficient": 3,
        "unavailable": 3,
    }
    assert [
        (item.case_id, item.method)
        for item in report.cases[:3]
    ] == [
        ("shift_high", "mean"),
        ("shift_high", "max"),
        ("shift_high", "ema"),
    ]


def test_benchmark_preserves_nonnumeric_missing_states():
    report = run_creator_shift_benchmark(_fixture())

    missing = [
        item
        for item in report.cases
        if item.status != "sufficient"
    ]

    assert missing
    assert all(item.shift_score is None for item in missing)
    assert all(not item.top_features for item in missing)


def test_fixture_hash_is_stable_but_content_sensitive():
    fixture = _fixture()
    first = run_creator_shift_benchmark(fixture)
    same = run_creator_shift_benchmark(
        CreatorShiftBenchmarkFixture.model_validate(
            json.loads(FIXTURE.read_text(encoding="utf-8"))
        )
    )
    changed_post = fixture.posts[0].model_copy(
        update={"text": fixture.posts[0].text + "变化"}
    )
    changed = run_creator_shift_benchmark(fixture.model_copy(
        update={"posts": [changed_post, *fixture.posts[1:]]}
    ))

    assert same.fixture_sha256 == first.fixture_sha256
    assert changed.fixture_sha256 != first.fixture_sha256


def test_fixture_rejects_duplicate_target_post_ids():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["posts"][1]["post_id"] = payload["posts"][0]["post_id"]

    with pytest.raises(ValidationError, match="post_id values must be unique"):
        CreatorShiftBenchmarkFixture.model_validate(payload)

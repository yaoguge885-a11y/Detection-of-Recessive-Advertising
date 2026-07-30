from __future__ import annotations

from impad.adapters import post_record_from_manual
from impad.creator_shift import (
    assess_post_creator_shift,
    creator_shift_evidence,
)


def _post(*, published_at="2026-07-30T00:00:00Z", history=None):
    return post_record_from_manual({
        "post_id": "target",
        "creator_id": "creator_1",
        "published_at": published_at,
        "text": "限时推荐，点击链接购买",
        "history": history if history is not None else [
            {
                "post_id": "history_1",
                "text": "今天生活记录",
                "published_at": "2026-07-27T00:00:00Z",
            },
            {
                "post_id": "history_2",
                "text": "昨天学习记录",
                "published_at": "2026-07-28T00:00:00Z",
            },
            {
                "post_id": "history_3",
                "text": "周末朋友分享",
                "published_at": "2026-07-29T00:00:00Z",
            },
        ],
    })


def test_runtime_assessment_produces_neutral_traceable_evidence():
    summary = assess_post_creator_shift(_post())

    assert summary.status == "sufficient"
    assert summary.pooling_method == "ema"
    assert summary.history_count == 3
    assert summary.required_history == 3
    assert summary.shift_score is not None
    assert summary.history_post_ids == [
        "history_1",
        "history_2",
        "history_3",
    ]
    assert summary.feature_version == "keyword_weights_v1"
    assert summary.runtime_version == "creator_shift_runtime_v1"

    evidence = creator_shift_evidence(summary)

    assert evidence is not None
    assert evidence.kind == "creator_shift"
    assert evidence.polarity == "neutral"
    assert evidence.source_type == "history"
    assert evidence.producer == "agent:creator_shift"
    assert evidence.score == summary.shift_score
    assert evidence.metadata["status"] == "sufficient"


def test_runtime_assessment_preserves_non_numeric_missing_states():
    unavailable_time = assess_post_creator_shift(
        _post(published_at=None),
    )
    unavailable_history = assess_post_creator_shift(_post(history=[]))
    insufficient = assess_post_creator_shift(_post(history=[
        {
            "post_id": "history_1",
            "text": "今天生活记录",
            "published_at": "2026-07-29T00:00:00Z",
        }
    ]))

    assert unavailable_time.status == "unavailable"
    assert unavailable_history.status == "unavailable"
    assert insufficient.status == "insufficient"
    for summary in (
        unavailable_time,
        unavailable_history,
        insufficient,
    ):
        assert summary.shift_score is None
        assert summary.pooling_method is None
        assert creator_shift_evidence(summary) is None


def test_runtime_assessment_excludes_unknown_time_with_limitation():
    summary = assess_post_creator_shift(_post(history=[
        {
            "post_id": "history_unknown",
            "text": "缺少时间",
            "published_at": None,
        },
        {
            "post_id": "history_1",
            "text": "今天生活记录",
            "published_at": "2026-07-27T00:00:00Z",
        },
        {
            "post_id": "history_2",
            "text": "昨天学习记录",
            "published_at": "2026-07-28T00:00:00Z",
        },
        {
            "post_id": "history_3",
            "text": "周末朋友分享",
            "published_at": "2026-07-29T00:00:00Z",
        },
    ]))

    assert summary.status == "sufficient"
    assert summary.history_count == 3
    assert "excluded_history_without_timestamp:1" in summary.limitations

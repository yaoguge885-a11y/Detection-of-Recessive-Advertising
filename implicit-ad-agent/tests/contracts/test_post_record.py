"""Runtime post and capture contracts."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from impad.contracts.post import (
    CaptureModality,
    CaptureStatus,
    HistoryPost,
    PostRecord,
)


def _capture() -> CaptureStatus:
    return CaptureStatus(
        source="manual",
        modalities={"text": CaptureModality(status="complete")},
    )


def test_post_record_rejects_cross_creator_resolved_history():
    with pytest.raises(ValidationError, match="same creator"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            text="正文",
            capture_status=_capture(),
            history=[
                HistoryPost(
                    post_id="post_other",
                    creator_id="blogger_b",
                    text="历史",
                    published_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
                )
            ],
        )


def test_post_record_rejects_future_or_same_time_history():
    target_time = datetime(2026, 7, 20, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="strictly earlier"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=target_time,
            text="正文",
            capture_status=_capture(),
            history=[
                HistoryPost(
                    post_id="post_future",
                    creator_id="blogger_a",
                    text="未来内容",
                    published_at=target_time,
                )
            ],
        )


def test_post_record_serializes_capture_and_preserves_missing_as_state():
    post = PostRecord(
        schema_version="runtime-1",
        post_id="post_1",
        platform="other",
        source_type="manual",
        creator_id="blogger_1",
        text="正文",
        capture_status=CaptureStatus(
            source="manual",
            modalities={
                "text": CaptureModality(status="complete"),
                "image": CaptureModality(
                    status="missing",
                    missing_fields=["media.ref"],
                ),
            },
            can_assess_disclosure=False,
        ),
    )

    dumped = post.model_dump(mode="json")

    assert dumped["capture_status"]["modalities"]["image"]["status"] == "missing"
    assert dumped["capture_status"]["can_assess_disclosure"] is False


def test_post_record_rejects_unknown_runtime_fields():
    with pytest.raises(ValidationError, match="extra"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_1",
            platform="other",
            source_type="manual",
            creator_id="blogger_1",
            text="正文",
            capture_status=_capture(),
            invented_field="must not be silently dropped",
        )


def test_post_record_orders_known_history_before_unknown_timestamps():
    post = PostRecord(
        schema_version="runtime-1",
        post_id="post_target",
        platform="synthetic",
        source_type="synthetic",
        creator_id="blogger_a",
        published_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        text="正文",
        capture_status=_capture(),
        history=[
            HistoryPost(
                post_id="post_unknown",
                creator_id="blogger_a",
                text="时间未知",
            ),
            HistoryPost(
                post_id="post_old",
                creator_id="blogger_a",
                text="较早历史",
                published_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
            ),
        ],
    )

    assert [item.post_id for item in post.history] == [
        "post_old",
        "post_unknown",
    ]


def test_post_record_rejects_timezone_naive_target_time():
    with pytest.raises(ValidationError, match="timezone-aware"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=datetime(2026, 7, 20),
            text="正文",
            capture_status=_capture(),
        )


def test_post_record_rejects_duplicate_history_post_ids():
    history_time = datetime(2026, 7, 18, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="history post_id"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            text="正文",
            capture_status=_capture(),
            history=[
                HistoryPost(
                    post_id="post_duplicate",
                    creator_id="blogger_a",
                    text="历史一",
                    published_at=history_time,
                ),
                HistoryPost(
                    post_id="post_duplicate",
                    creator_id="blogger_a",
                    text="历史二",
                    published_at=history_time,
                ),
            ],
        )


def test_post_record_rejects_target_post_inside_resolved_history():
    with pytest.raises(ValidationError, match="target post_id"):
        PostRecord(
            schema_version="runtime-1",
            post_id="post_target",
            platform="synthetic",
            source_type="synthetic",
            creator_id="blogger_a",
            published_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
            text="正文",
            capture_status=_capture(),
            history=[
                HistoryPost(
                    post_id="post_target",
                    creator_id="blogger_a",
                    text="错误回填的目标帖子",
                    published_at=datetime(
                        2026,
                        7,
                        18,
                        tzinfo=timezone.utc,
                    ),
                )
            ],
        )

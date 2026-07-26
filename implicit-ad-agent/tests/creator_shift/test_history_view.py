from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from impad.creator_shift.contracts import (
    CreatorHistoryView,
    HistoryFeature,
)


TARGET_TIME = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _history(
    index: int,
    *,
    creator_id: str = "creator_1",
    published_at: datetime | None = None,
):
    return HistoryFeature(
        post_id=f"post_{index}",
        creator_id=creator_id,
        published_at=(
            published_at
            or TARGET_TIME - timedelta(days=4 - index)
        ),
        features={"commercial": index / 10, "visual_product": index / 20},
    )


def _view(history, *, minimum_history=3):
    return CreatorHistoryView(
        target_post_id="post_target",
        target_creator_id="creator_1",
        target_time=TARGET_TIME,
        minimum_history=minimum_history,
        history=history,
    )


def test_valid_history_is_sorted_and_reports_sufficient():
    view = _view([_history(3), _history(1), _history(2)])

    assert [item.post_id for item in view.history] == [
        "post_1",
        "post_2",
        "post_3",
    ]
    assert view.sufficiency.status == "sufficient"
    assert view.sufficiency.observed_count == 3


def test_empty_and_short_history_have_explicit_non_numeric_status():
    empty = _view([])
    short = _view([_history(1)], minimum_history=3)

    assert empty.sufficiency.status == "unavailable"
    assert short.sufficiency.status == "insufficient"
    assert short.sufficiency.required_count == 3


def test_history_rejects_cross_creator_record():
    with pytest.raises(ValidationError, match="same creator"):
        _view([_history(1, creator_id="creator_other")])


@pytest.mark.parametrize(
    "published_at",
    [TARGET_TIME, TARGET_TIME + timedelta(seconds=1)],
)
def test_history_rejects_equal_or_future_timestamp(published_at):
    with pytest.raises(ValidationError, match="strictly earlier"):
        _view([_history(1, published_at=published_at)])


def test_history_rejects_duplicate_or_target_post_id():
    duplicate = _history(1)
    with pytest.raises(ValidationError, match="post_id values must be unique"):
        _view([duplicate, duplicate])

    with pytest.raises(ValidationError, match="target post"):
        _view([
            HistoryFeature(
                post_id="post_target",
                creator_id="creator_1",
                published_at=TARGET_TIME - timedelta(days=1),
                features={"commercial": 0.1},
            )
        ])


def test_history_requires_timezone_aware_datetimes():
    with pytest.raises(ValidationError, match="timezone-aware"):
        HistoryFeature(
            post_id="post_1",
            creator_id="creator_1",
            published_at=datetime(2026, 7, 20),
            features={"commercial": 0.1},
        )

    with pytest.raises(ValidationError, match="timezone-aware"):
        CreatorHistoryView(
            target_post_id="post_target",
            target_creator_id="creator_1",
            target_time=datetime(2026, 7, 24),
            history=[],
        )

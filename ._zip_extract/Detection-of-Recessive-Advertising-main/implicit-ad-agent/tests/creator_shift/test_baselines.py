from datetime import datetime, timedelta, timezone

import pytest

from impad.creator_shift.baselines import (
    HistoryPoolingError,
    pool_history,
)
from impad.creator_shift.contracts import CreatorHistoryView, HistoryFeature


TARGET_TIME = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _view(*, minimum_history=3, mismatched=False):
    history = [
        HistoryFeature(
            post_id=f"post_{index}",
            creator_id="creator_1",
            published_at=TARGET_TIME - timedelta(days=4 - index),
            features=(
                {"commercial": index / 10}
                if mismatched and index == 3
                else {
                    "commercial": index / 10,
                    "visual_product": index / 20,
                }
            ),
        )
        for index in range(1, 4)
    ]
    return CreatorHistoryView(
        target_post_id="post_target",
        target_creator_id="creator_1",
        target_time=TARGET_TIME,
        minimum_history=minimum_history,
        history=history,
    )


def test_mean_pooling_uses_all_history_in_feature_name_order():
    pooled = pool_history(_view(), method="mean")

    assert list(pooled.values) == ["commercial", "visual_product"]
    assert pooled.values == {
        "commercial": pytest.approx(0.2),
        "visual_product": pytest.approx(0.1),
    }
    assert pooled.history_post_ids == ["post_1", "post_2", "post_3"]
    assert pooled.history_count == 3


def test_max_pooling_is_per_feature():
    pooled = pool_history(_view(), method="max")

    assert pooled.values == {
        "commercial": pytest.approx(0.3),
        "visual_product": pytest.approx(0.15),
    }


def test_ema_pooling_is_chronological_and_records_alpha():
    pooled = pool_history(_view(), method="ema", alpha=0.5)

    assert pooled.values == {
        "commercial": pytest.approx(0.225),
        "visual_product": pytest.approx(0.1125),
    }
    assert pooled.alpha == 0.5


def test_pooling_rejects_unavailable_or_insufficient_history():
    unavailable = CreatorHistoryView(
        target_post_id="post_target",
        target_creator_id="creator_1",
        target_time=TARGET_TIME,
        history=[],
    )
    insufficient = _view(minimum_history=4)

    with pytest.raises(HistoryPoolingError, match="unavailable"):
        pool_history(unavailable, method="mean")
    with pytest.raises(HistoryPoolingError, match="insufficient"):
        pool_history(insufficient, method="mean")


def test_pooling_rejects_feature_key_mismatch_and_invalid_alpha():
    with pytest.raises(HistoryPoolingError, match="feature keys"):
        pool_history(_view(mismatched=True), method="mean")
    with pytest.raises(ValueError, match="alpha"):
        pool_history(_view(), method="ema", alpha=0)

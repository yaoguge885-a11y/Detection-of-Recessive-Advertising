from datetime import datetime, timedelta, timezone

import pytest

from impad.creator_shift.baselines import pool_history
from impad.creator_shift.contracts import CreatorHistoryView, HistoryFeature
from impad.creator_shift.shift import calculate_shift


TARGET_TIME = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _pooled():
    history = [
        HistoryFeature(
            post_id=f"post_{index}",
            creator_id="creator_1",
            published_at=TARGET_TIME - timedelta(days=4 - index),
            features={
                "commercial": index / 10,
                "visual_product": index / 20,
            },
        )
        for index in range(1, 4)
    ]
    view = CreatorHistoryView(
        target_post_id="post_target",
        target_creator_id="creator_1",
        target_time=TARGET_TIME,
        history=history,
    )
    return pool_history(view, method="mean")


def test_shift_is_mean_absolute_delta_with_interpretable_features():
    result = calculate_shift(
        {
            "commercial": 0.5,
            "visual_product": 0.15,
        },
        _pooled(),
    )

    assert result.shift_score == pytest.approx(0.175)
    assert result.feature_deltas == {
        "commercial": pytest.approx(0.3),
        "visual_product": pytest.approx(0.05),
    }
    assert result.top_features == ["commercial", "visual_product"]
    assert result.pooling_method == "mean"
    assert result.history_count == 3
    assert result.history_post_ids == ["post_1", "post_2", "post_3"]
    assert result.limitations


def test_top_features_break_equal_contributions_by_feature_name():
    pooled = _pooled().model_copy(update={
        "values": {"zeta": 0.1, "alpha": 0.1},
    })
    result = calculate_shift(
        {"zeta": 0.2, "alpha": 0.2},
        pooled,
    )

    assert result.top_features == ["alpha", "zeta"]


def test_shift_rejects_mismatched_or_non_finite_target_features():
    with pytest.raises(ValueError, match="feature keys"):
        calculate_shift({"commercial": 0.5}, _pooled())

    with pytest.raises(ValueError, match="finite"):
        calculate_shift(
            {
                "commercial": float("nan"),
                "visual_product": 0.15,
            },
            _pooled(),
        )

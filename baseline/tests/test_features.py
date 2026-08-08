"""Focused tests for leakage-safe history feature construction."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from baseline.contracts import (
    BaselineInputError,
    ContentPost,
    GoldRecord,
    InputBundle,
    SplitAssignments,
)
from baseline.features import (
    FEATURE_VERSION,
    WEIGHT_DIMENSIONS,
    FeatureRow,
    build_common_cohort,
    compute_keyword_weights,
    method_vector,
    pool_history,
)


UTC = timezone.utc
LABELS = ("明广", "暗广", "非广")


def _rows(*vectors: tuple[float, ...]) -> tuple[FeatureRow, ...]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return tuple(
        FeatureRow(
            post_id=f"history-{index}",
            blogger_id="creator",
            published_at=start + timedelta(days=index),
            values=vector,
        )
        for index, vector in enumerate(vectors)
    )


def test_pooling_exact_values():
    rows = _rows((0.1, 0.2), (0.3, 0.4), (0.5, 0.8))
    assert pool_history(rows, method="mean") == pytest.approx((0.3, 0.4666666667))
    assert pool_history(rows, method="max") == pytest.approx((0.5, 0.8))
    assert pool_history(rows, method="ema", alpha=0.5) == pytest.approx((0.35, 0.55))


def test_keyword_weights_keep_agent_parity_and_dimension_order():
    text = "品牌赞助，限时优惠，点击链接购买，今天分享体验"
    assert FEATURE_VERSION == "keyword_weights_v1"
    assert WEIGHT_DIMENSIONS == (
        "promotion_words",
        "price_mentions",
        "urgency_expressions",
        "brand_mentions",
        "action_words",
        "natural_expression",
    )
    assert compute_keyword_weights(text) == pytest.approx(
        (0.0, 0.25, 0.33, 0.67, 1.0, 0.6)
    )


def _make_bundle() -> InputBundle:
    posts: dict[str, ContentPost] = {}
    gold: dict[str, GoldRecord] = {}
    split_values: dict[str, set[str]] = {"train": set(), "dev": set(), "test": set()}
    start = datetime(2024, 1, 1, tzinfo=UTC)

    for split_index, split in enumerate(split_values):
        for label_index, label in enumerate(LABELS):
            target_id = f"target-{split}-{label_index}"
            creator = f"creator-{split}-{label_index}"
            target_time = start + timedelta(days=split_index * 20 + 10)
            history_refs: list[str] = []
            for history_index in range(3):
                history_id = f"{target_id}-history-{history_index}"
                history_refs.append(history_id)
                posts[history_id] = ContentPost(
                    post_id=history_id,
                    blogger_id=creator,
                    published_at=target_time - timedelta(days=history_index + 1),
                    text=f"history {history_index}",
                    history_refs=(),
                    content_group_id=None,
                )
            posts[target_id] = ContentPost(
                post_id=target_id,
                blogger_id=creator,
                published_at=target_time,
                text="品牌赞助，限时优惠，点击链接购买，今天分享体验",
                history_refs=tuple(history_refs),
                content_group_id=None,
            )
            gold[target_id] = GoldRecord(post_id=target_id, label=label)
            split_values[split].add(target_id)

    return InputBundle(
        mode="synthetic",
        posts=posts,
        gold=gold,
        splits=SplitAssignments(
            train=frozenset(split_values["train"]),
            dev=frozenset(split_values["dev"]),
            test=frozenset(split_values["test"]),
        ),
        evaluation_split="dev",
        confirm_test_evaluation=False,
        input_hashes={},
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_ref", "history reference is missing"),
        ("cross_creator", "history creator mismatch"),
        ("self_ref", "history self-reference"),
        ("equal_time", "history timestamp is not earlier"),
        ("future_time", "history timestamp is not earlier"),
        ("duplicate_ref", "duplicate history reference"),
        ("naive_time", "timezone-aware timestamp required"),
    ],
)
def test_history_integrity_aborts_entire_run(
    mutation: str, message: str
):
    bundle = _make_bundle()
    target_id = "target-train-0"
    target = bundle.posts[target_id]
    first_history_id = target.history_refs[0]
    first_history = bundle.posts[first_history_id]

    if mutation == "missing_ref":
        posts = {**bundle.posts, "bad": target}
        posts[target_id] = replace(target, history_refs=("not-present",))
    elif mutation == "cross_creator":
        posts = dict(bundle.posts)
        posts[first_history_id] = replace(first_history, blogger_id="other-creator")
    elif mutation == "self_ref":
        posts = dict(bundle.posts)
        posts[target_id] = replace(target, history_refs=(target_id,))
    elif mutation == "equal_time":
        posts = dict(bundle.posts)
        posts[first_history_id] = replace(first_history, published_at=target.published_at)
    elif mutation == "future_time":
        posts = dict(bundle.posts)
        posts[first_history_id] = replace(
            first_history, published_at=target.published_at + timedelta(seconds=1)
        )
    elif mutation == "duplicate_ref":
        posts = dict(bundle.posts)
        posts[target_id] = replace(
            target, history_refs=(first_history_id, first_history_id, *target.history_refs[1:])
        )
    elif mutation == "naive_time":
        posts = dict(bundle.posts)
        posts[first_history_id] = replace(first_history, published_at=datetime(2024, 1, 1))
    else:  # pragma: no cover
        raise AssertionError(mutation)

    mutated = replace(bundle, posts=posts)
    with pytest.raises(BaselineInputError, match=message):
        build_common_cohort(mutated)


def test_missing_target_and_insufficient_history_are_aggregate_exclusions():
    bundle = _make_bundle()
    missing_target = "target-train-0"
    insufficient_target = "target-dev-0"
    posts = dict(bundle.posts)
    gold = dict(bundle.gold)
    train_extra = "target-train-extra"
    dev_extra = "target-dev-extra"
    posts[train_extra] = replace(
        posts[missing_target], post_id=train_extra
    )
    posts[dev_extra] = replace(
        posts[insufficient_target], post_id=dev_extra
    )
    gold[train_extra] = GoldRecord(post_id=train_extra, label="明广")
    gold[dev_extra] = GoldRecord(post_id=dev_extra, label="明广")
    posts[missing_target] = replace(posts[missing_target], published_at=None)
    posts[insufficient_target] = replace(
        posts[insufficient_target], history_refs=posts[insufficient_target].history_refs[:2]
    )
    splits = replace(
        bundle.splits,
        train=frozenset((*bundle.splits.train, train_extra)),
        dev=frozenset((*bundle.splits.dev, dev_extra)),
    )
    cohort = build_common_cohort(replace(bundle, posts=posts, gold=gold, splits=splits))

    assert cohort.exclusion_counts["target_timestamp_unavailable"] == 1
    assert cohort.exclusion_counts["history_insufficient"] == 1
    assert missing_target not in {sample.post_id for sample in cohort.samples}
    assert insufficient_target not in {sample.post_id for sample in cohort.samples}


def test_all_methods_share_identical_complete_cohort_ids():
    cohort = build_common_cohort(_make_bundle())
    expected_ids = tuple(sample.post_id for sample in cohort.samples)
    assert expected_ids
    method_ids = {
        method: tuple(sample.post_id for sample in cohort.samples)
        for method in ("single_post", "history_mean", "history_max", "history_ema")
    }
    assert all(ids == expected_ids for ids in method_ids.values())
    assert cohort.split_gold_counts == {"train": 3, "dev": 3, "test": 3}
    assert cohort.split_cohort_counts == {"train": 3, "dev": 3, "test": 3}


def test_method_vectors_pool_target_and_history():
    sample = build_common_cohort(_make_bundle()).samples[0]
    assert len(method_vector(sample, "single_post")) == 6
    assert len(method_vector(sample, "history_mean")) == 12
    assert method_vector(sample, "history_mean")[6:] == pytest.approx(
        pool_history(sample.history_rows, method="mean")
    )

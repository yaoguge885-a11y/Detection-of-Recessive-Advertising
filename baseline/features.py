"""Deterministic keyword features and leakage-safe history pooling.

This module is intentionally independent from the Agent runtime.  It turns the
already-validated :class:`~baseline.contracts.InputBundle` into one shared,
complete cohort; every baseline method consumes that same cohort so method
comparisons cannot be affected by different missing-history filters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Literal, Sequence

from .contracts import LABELS, BaselineInputError, ContentPost, InputBundle


FEATURE_VERSION = "keyword_weights_v1"
WEIGHT_DIMENSIONS = (
    "promotion_words",
    "price_mentions",
    "urgency_expressions",
    "brand_mentions",
    "action_words",
    "natural_expression",
)

# Keep this table byte-for-byte equivalent to the approved Agent-side table.
PROMOTION_WORDS = (
    "种草",
    "安利",
    "必买",
    "回购",
    "强烈推荐",
    "推荐",
    "爆款",
    "热卖",
    "超赞",
    "真香",
    "宝藏",
    "好用到哭",
    "值得入",
    "闭眼入",
    "无限回购",
)
PRICE_WORDS = (
    "价格",
    "多少钱",
    "性价比",
    "划算",
    "超值",
    "便宜",
    "实惠",
    "优惠",
    "折扣",
    "特价",
    "促销",
    "满减",
    "到手价",
    "直降",
    "原价",
    "秒杀",
    "领券",
)
URGENCY_WORDS = (
    "限时",
    "抢购",
    "赶紧",
    "快来",
    "马上",
    "立刻",
    "立即",
    "不要错过",
    "仅剩",
    "名额有限",
    "最后一天",
    "手慢无",
    "库存告急",
    "冲鸭",
)
BRAND_WORDS = (
    "品牌",
    "官方",
    "正品",
    "旗舰店",
    "专营",
    "授权",
    "代理",
    "招商",
    "加盟",
    "货源",
    "批发",
    "一件代发",
    "赞助",
    "恰饭",
)
ACTION_WORDS = (
    "点击",
    "扫码",
    "链接",
    "私信",
    "购买",
    "下单",
    "加购",
    "购物车",
    "小黄车",
    "点上方",
    "戳这里",
    "领取",
    "蹲一个",
    "冲同款",
)
NATURAL_WORDS = (
    "我觉得",
    "我认为",
    "感受",
    "体验",
    "心情",
    "日记",
    "分享",
    "记录",
    "吐槽",
    "生活",
    "学习",
    "朋友",
    "家人",
    "今天",
    "昨天",
    "周末",
    "假期",
    "随手记",
    "碎碎念",
)

# Public names make the pinned table auditable while preserving the Agent
# source's dimension keys and sequence values exactly.
CATEGORY_WORDS = {
    "promotion_words": PROMOTION_WORDS,
    "price_mentions": PRICE_WORDS,
    "urgency_expressions": URGENCY_WORDS,
    "brand_mentions": BRAND_WORDS,
    "action_words": ACTION_WORDS,
    "natural_expression": NATURAL_WORDS,
}
SATURATION = {
    "promotion_words": 4,
    "price_mentions": 4,
    "urgency_expressions": 3,
    "brand_mentions": 3,
    "action_words": 3,
    "natural_expression": 5,
}

MINIMUM_HISTORY = 3
DEFAULT_EMA_ALPHA = 0.5
_SPLIT_ORDER = ("train", "dev", "test")
PoolingMethod = Literal["mean", "max", "ema"]


@dataclass(frozen=True)
class FeatureRow:
    post_id: str
    blogger_id: str
    published_at: datetime
    values: tuple[float, ...]


@dataclass(frozen=True)
class PreparedSample:
    post_id: str
    split: str
    label: str
    target_values: tuple[float, ...]
    history_rows: tuple[FeatureRow, ...]


@dataclass(frozen=True)
class Cohort:
    samples: tuple[PreparedSample, ...]
    gold_count: int
    split_gold_counts: dict[str, int]
    split_cohort_counts: dict[str, int]
    exclusion_counts: dict[str, int]


def compute_keyword_weights(text: str) -> tuple[float, ...]:
    """Return the fixed six-dimensional Agent-parity keyword vector."""

    if not isinstance(text, str):
        raise BaselineInputError("post text must be text")
    hits = {
        name: sum(word in text for word in CATEGORY_WORDS[name])
        for name in WEIGHT_DIMENSIONS
    }
    return tuple(
        round(min(hits[name] / SATURATION[name], 1.0), 2)
        for name in WEIGHT_DIMENSIONS
    )


def pool_history(
    rows: Sequence[FeatureRow] | Iterable[FeatureRow],
    method: PoolingMethod | str,
    alpha: float = DEFAULT_EMA_ALPHA,
) -> tuple[float, ...]:
    """Pool feature rows in chronological order using mean, max, or EMA.

    Histories are sorted internally rather than trusting JSON/reference order.
    The function validates timestamp awareness, finite values, and equal vector
    dimensions before calculating any aggregate.
    """

    if method not in {"mean", "max", "ema"}:
        raise BaselineInputError("history pooling method is invalid")
    materialized = tuple(rows)
    if not materialized:
        raise BaselineInputError("history rows are empty")

    checked: list[tuple[FeatureRow, tuple[float, ...]]] = []
    expected_length: int | None = None
    for row in materialized:
        if not isinstance(row, FeatureRow):
            raise BaselineInputError("history row is invalid")
        if not _is_aware(row.published_at):
            raise BaselineInputError("timezone-aware timestamp required")
        values = _finite_values(row.values)
        if expected_length is None:
            expected_length = len(values)
        elif len(values) != expected_length:
            raise BaselineInputError("history vectors must have identical dimensions")
        checked.append((row, values))

    checked.sort(key=lambda item: item[0].published_at)
    vectors = [values for _, values in checked]
    assert expected_length is not None

    if method == "mean":
        count = float(len(vectors))
        return tuple(sum(vector[index] for vector in vectors) / count for index in range(expected_length))
    if method == "max":
        return tuple(max(vector[index] for vector in vectors) for index in range(expected_length))

    if isinstance(alpha, bool):
        raise BaselineInputError("EMA alpha is invalid")
    try:
        alpha_value = float(alpha)
    except (TypeError, ValueError) as exc:
        raise BaselineInputError("EMA alpha is invalid") from exc
    if not math.isfinite(alpha_value) or not 0.0 <= alpha_value <= 1.0:
        raise BaselineInputError("EMA alpha is invalid")
    state = list(vectors[0])
    for vector in vectors[1:]:
        state = [
            alpha_value * current + (1.0 - alpha_value) * previous
            for current, previous in zip(vector, state)
        ]
    return tuple(state)


def build_common_cohort(bundle: InputBundle) -> Cohort:
    """Build the one complete, leakage-safe cohort shared by every method."""

    if not isinstance(bundle, InputBundle):
        raise BaselineInputError("baseline input bundle is invalid")

    split_values = {
        "train": bundle.splits.train,
        "dev": bundle.splits.dev,
        "test": bundle.splits.test,
    }
    _target_split_map(split_values, set(bundle.gold))
    split_gold_counts = {split: len(split_values[split]) for split in _SPLIT_ORDER}
    exclusion_counts = {
        "target_timestamp_unavailable": 0,
        "history_insufficient": 0,
    }
    samples: list[PreparedSample] = []

    for split in _SPLIT_ORDER:
        for post_id in sorted(split_values[split]):
            if post_id not in bundle.gold:
                raise BaselineInputError("split/Gold coverage mismatch")
            target = bundle.posts.get(post_id)
            if target is None:
                raise BaselineInputError("target post is missing")
            label = bundle.gold[post_id].label
            if label not in LABELS:
                raise BaselineInputError("invalid formal Gold label")

            target_time = target.published_at
            if target_time is not None and not _is_aware(target_time):
                raise BaselineInputError("timezone-aware timestamp required")

            history_rows = _prepare_history_rows(
                target=target,
                posts=bundle.posts,
                target_time=target_time,
            )
            if target_time is None:
                exclusion_counts["target_timestamp_unavailable"] += 1
                continue
            if len(history_rows) < MINIMUM_HISTORY:
                exclusion_counts["history_insufficient"] += 1
                continue

            samples.append(
                PreparedSample(
                    post_id=post_id,
                    split=split,
                    label=label,
                    target_values=compute_keyword_weights(target.text),
                    history_rows=tuple(history_rows),
                )
            )

    samples.sort(key=lambda sample: (_SPLIT_ORDER.index(sample.split), sample.post_id))
    split_cohort_counts = {
        split: sum(sample.split == split for sample in samples)
        for split in _SPLIT_ORDER
    }
    cohort_labels = {
        split: {sample.label for sample in samples if sample.split == split}
        for split in _SPLIT_ORDER
    }
    if any(labels != set(LABELS) for labels in cohort_labels.values()):
        raise BaselineInputError("each cohort split must contain all three labels")

    return Cohort(
        samples=tuple(samples),
        gold_count=len(bundle.gold),
        split_gold_counts=split_gold_counts,
        split_cohort_counts=split_cohort_counts,
        exclusion_counts=exclusion_counts,
    )


def method_vector(sample: PreparedSample, method: str) -> tuple[float, ...]:
    """Return a target-only or target-plus-history vector for one sample."""

    if not isinstance(sample, PreparedSample):
        raise BaselineInputError("prepared sample is invalid")
    target_values = _finite_values(sample.target_values)
    if method == "single_post":
        return target_values
    pooling_method: str
    if method == "history_mean":
        pooling_method = "mean"
    elif method == "history_max":
        pooling_method = "max"
    elif method == "history_ema":
        pooling_method = "ema"
    else:
        raise BaselineInputError("feature method is invalid")
    return target_values + pool_history(
        sample.history_rows,
        method=pooling_method,
        alpha=DEFAULT_EMA_ALPHA,
    )


def _target_split_map(
    split_values: dict[str, frozenset[str]], gold_ids: set[str]
) -> dict[str, str]:
    observed: dict[str, str] = {}
    for split in _SPLIT_ORDER:
        for post_id in split_values[split]:
            if post_id in observed:
                raise BaselineInputError("split IDs overlap")
            observed[post_id] = split
    if set(observed) != gold_ids:
        raise BaselineInputError("split/Gold coverage mismatch")
    return observed


def _prepare_history_rows(
    *,
    target: ContentPost,
    posts: dict[str, ContentPost],
    target_time: datetime | None,
) -> list[FeatureRow]:
    seen: set[str] = set()
    rows: list[FeatureRow] = []
    if not isinstance(target.history_refs, (tuple, list)):
        raise BaselineInputError("content history_refs field is invalid")
    for history_id in target.history_refs:
        if not isinstance(history_id, str) or not history_id.strip():
            raise BaselineInputError("history reference is invalid")
        if history_id in seen:
            raise BaselineInputError("duplicate history reference")
        seen.add(history_id)
        history = posts.get(history_id)
        if history is None:
            raise BaselineInputError("history reference is missing")
        if history_id == target.post_id:
            raise BaselineInputError("history self-reference")
        if history.blogger_id != target.blogger_id:
            raise BaselineInputError("history creator mismatch")
        history_time = history.published_at
        if history_time is None or not _is_aware(history_time):
            raise BaselineInputError("timezone-aware timestamp required")
        if target_time is not None and history_time >= target_time:
            raise BaselineInputError("history timestamp is not earlier")
        rows.append(
            FeatureRow(
                post_id=history.post_id,
                blogger_id=history.blogger_id,
                published_at=history_time,
                values=compute_keyword_weights(history.text),
            )
        )
    return rows


def _finite_values(values: Sequence[float] | Iterable[float]) -> tuple[float, ...]:
    try:
        materialized = tuple(values)
    except TypeError as exc:
        raise BaselineInputError("feature vector is invalid") from exc
    if not materialized:
        raise BaselineInputError("feature vector is empty")
    checked: list[float] = []
    for value in materialized:
        if isinstance(value, bool):
            raise BaselineInputError("feature vector contains non-finite values")
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise BaselineInputError("feature vector contains non-finite values") from exc
        if not math.isfinite(numeric):
            raise BaselineInputError("feature vector contains non-finite values")
        checked.append(numeric)
    return tuple(checked)


def _is_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


__all__ = [
    "FEATURE_VERSION",
    "WEIGHT_DIMENSIONS",
    "CATEGORY_WORDS",
    "SATURATION",
    "MINIMUM_HISTORY",
    "DEFAULT_EMA_ALPHA",
    "FeatureRow",
    "PreparedSample",
    "Cohort",
    "compute_keyword_weights",
    "pool_history",
    "build_common_cohort",
    "method_vector",
]

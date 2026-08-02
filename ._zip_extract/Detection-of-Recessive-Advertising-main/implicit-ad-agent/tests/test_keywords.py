"""Six-dimensional keyword features and their tool/graph propagation."""
from impad.graph import graph
from impad.tools.keywords import (
    WEIGHT_DIMENSIONS,
    ad_pressure,
    compute_keyword_weights,
    summarize_weights,
)


def test_weights_shape_and_range():
    weights = compute_keyword_weights("今天去图书馆看书，心情不错")
    assert set(weights) == set(WEIGHT_DIMENSIONS)
    assert all(0.0 <= value <= 1.0 for value in weights.values())


def test_natural_text_scores_natural_high():
    weights = compute_keyword_weights(
        "今天和朋友周末逛街，分享一下心情和生活"
    )
    assert weights["natural_expression"] > 0
    assert ad_pressure(weights) < weights["natural_expression"]


def test_promo_text_has_pressure():
    weights = compute_keyword_weights(
        "限时抢购！扫码下单立减，爆款种草必买，手慢无"
    )
    assert ad_pressure(weights) >= 0.5
    assert weights["natural_expression"] == 0.0
    summary = summarize_weights(weights)
    assert "促销种草" in summary or "行动召唤" in summary


def test_summary_empty_when_no_signal():
    assert (
        summarize_weights(compute_keyword_weights("嗯嗯好的"))
        == "无显著关键词信号"
    )


def test_graph_carries_tool_keyword_weights_without_agent_vote():
    out = graph.invoke({
        "post": {
            "text": "限时抢购！扫码下单立减，爆款种草必买",
        }
    })

    assert set(out["keyword_weights"]) == set(WEIGHT_DIMENSIONS)
    text_result = next(
        result
        for result in out["tool_results"]
        if result.tool_name == "analyze_text_intent"
    )
    assert text_result.payload["keyword_weights"] == out["keyword_weights"]
    assert out["verdict_report"].label == "需复核"

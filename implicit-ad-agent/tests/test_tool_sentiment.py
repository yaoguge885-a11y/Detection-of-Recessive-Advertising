from impad.tools.sentiment import SentimentCurveInput, _sentiment_curve_core


def test_sentiment_separates_negative_from_urgency():
    negative = _sentiment_curve_core(SentimentCurveInput(text="今天很失望也很生气"))
    urgent = _sentiment_curve_core(SentimentCurveInput(text="最后一天限时抢购，手慢无"))
    assert negative.payload["current_sentiment"] == "negative"
    assert negative.score == 0
    assert urgent.payload["urgency_score"] > 0


def test_short_history_has_no_change_points():
    result = _sentiment_curve_core(SentimentCurveInput(
        text="赶紧抢购", history=[{"post_id": "1", "text": "日常分享"}]))
    assert result.payload["change_points"] == []
    assert result.warnings


def test_history_is_sorted():
    result = _sentiment_curve_core(SentimentCurveInput(text="普通记录", history=[
        {"post_id": "later", "text": "开心", "published_at": "2026-02-01"},
        {"post_id": "early", "text": "难过", "published_at": "2026-01-01"},
        {"post_id": "middle", "text": "平常", "published_at": "2026-01-15"},
    ]))
    assert [p["post_id"] for p in result.payload["curve_points"][:3]] == ["early", "middle", "later"]


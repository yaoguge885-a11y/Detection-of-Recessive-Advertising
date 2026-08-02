from impad.tools.topic_drift import TopicDriftInput, _topic_drift_core


HISTORY = [
    {"post_id": "1", "text": "Python 编程学习笔记和代码练习", "published_at": "2026-01-01"},
    {"post_id": "2", "text": "今天继续学习 Python 编程", "published_at": "2026-01-02"},
    {"post_id": "3", "text": "分享代码练习和编程心得", "published_at": "2026-01-03"},
]


def test_cross_topic_scores_higher_than_same_topic():
    same = _topic_drift_core(TopicDriftInput(post_id="x", text="Python 编程代码学习", history=HISTORY))
    cross = _topic_drift_core(TopicDriftInput(post_id="y", text="口红美妆限时优惠购买", history=HISTORY))
    assert same.status == cross.status == "degraded"
    assert same.score < cross.score
    assert same.evidence


def test_insufficient_history_is_skipped_not_zero():
    result = _topic_drift_core(TopicDriftInput(post_id="x", text="测试", history=HISTORY[:2]))
    assert result.status == "skipped"
    assert result.score is None


def test_future_history_is_filtered():
    result = _topic_drift_core(TopicDriftInput(
        post_id="x", text="Python", published_at="2026-01-03", history=HISTORY))
    assert result.status == "skipped"
    assert result.payload["distance_details"]["valid_history_count"] == 2


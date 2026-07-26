from impad.tools.comment_anomaly import CommentAnomalyInput, _comment_anomaly_core


def test_too_few_comments_are_skipped():
    result = _comment_anomaly_core(CommentAnomalyInput(comments=[]))
    assert result.status == "skipped"
    assert result.score is None


def test_duplicate_praise_is_traceable():
    comments = [{"comment_id": str(i), "text": "太好用了，已下单",
                 "created_at": f"2026-01-01T10:0{i}:00"} for i in range(5)]
    result = _comment_anomaly_core(CommentAnomalyInput(comments=comments))
    assert result.status == "ok"
    assert result.score > 0.5
    assert set(result.payload["suspicious_comment_ids"]) == {str(i) for i in range(5)}
    assert result.evidence[0].comment_ids


def test_missing_timestamps_skip_only_burst_feature():
    comments = [{"comment_id": str(i), "text": f"不同的正常讨论内容{i}"} for i in range(5)]
    result = _comment_anomaly_core(CommentAnomalyInput(comments=comments))
    assert result.status == "ok"
    assert result.payload["burst_score"] is None
    assert result.warnings


from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.data.annotation.apply_image_placement_disposition import WAIVER_STATUS, apply_disposition


def test_disposition_excludes_definite_and_ignores_decisions():
    candidates = [{"post_id": "post_bad"}, {"post_id": "post_keep"}]
    queue = [{"post_id": "post_bad", "review_status": "pending"},
             {"post_id": "post_keep", "review_status": "pending"}]
    decisions = [{"post_id": "post_bad", "review_status": "pass"},
                 {"post_id": "post_keep", "review_status": "pass"}]
    report = {"posts": [
        {"post_id": "post_bad", "classification": "definite_layout_error",
         "classification_reasons": ["marker_in_or_adjacent_url"]},
        {"post_id": "post_keep", "classification": "no_rule_signal"},
    ]}
    kept, waived, exclusions, dispositions, result = apply_disposition(
        candidates, queue, decisions, report, "fixture-policy")
    assert [row["post_id"] for row in kept] == ["post_keep"]
    assert waived[0]["llm_needs_review"] is False
    assert waived[0]["review_status"] == WAIVER_STATUS
    assert exclusions[0]["existing_human_decision_preserved_and_ignored"] is True
    assert {row["human_review_performed"] for row in dispositions} == {False}
    assert result["human_decisions_used"] == 0

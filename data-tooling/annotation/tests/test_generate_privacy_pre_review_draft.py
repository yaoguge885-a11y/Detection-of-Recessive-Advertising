"""Regression tests for the human-facing privacy pre-review packet."""

from __future__ import annotations

import sys
from pathlib import Path


ANNOTATION_DIR = Path(__file__).resolve().parent.parent
if str(ANNOTATION_DIR) not in sys.path:
    sys.path.insert(0, str(ANNOTATION_DIR))

from generate_privacy_pre_review_draft import (  # noqa: E402
    existing_mask_categories,
    mask_sensitive,
    recommendation,
    render_item,
)


def test_masker_preserves_already_masked_email_state() -> None:
    masked = mask_sensitive("投简历至 s***n@dxy.cn")
    assert "s***n@dxy.cn" in masked
    assert "[EMAIL]" not in masked


def test_masker_does_not_treat_guide_as_uid() -> None:
    assert "guide-rpc-framework" in mask_sensitive("guide-rpc-framework")
    assert "[ACCOUNT_ID]" not in mask_sensitive("guide-rpc-framework")


def test_existing_mask_allows_resolved_sensitive_flag() -> None:
    record = {
        "text": "投简历至 s***n@dxy.cn",
        "privacy": {"contains_sensitive_data": True},
    }
    categories = existing_mask_categories(record)
    decision, _ = recommendation("mandatory", record, [], categories)
    assert categories == ["email"]
    assert decision == "allow"


def test_unlocalized_flag_stays_exclude() -> None:
    record = {"text": "普通正文", "privacy": {"contains_sensitive_data": True}}
    decision, _ = recommendation("mandatory", record, [], [])
    assert decision == "exclude"


class _NoFindingScanner:
    @staticmethod
    def scan_record(record):
        return []


def test_render_uses_clickable_task_boxes_and_migrates_unchanged_agree() -> None:
    record = {
        "post_id": "post_0123456789abcdef0123456789abcdef",
        "text": "普通正文",
        "comments": [],
        "media": [],
        "privacy": {"contains_sensitive_data": False},
    }
    rendered = render_item(
        1,
        "mandatory",
        {"confirmed": False, "decision": None},
        record,
        _NoFindingScanner,
        {record["post_id"]: {"draft": "allow", "choice": "agree"}},
    )
    assert "  - [x] agree（同意 AI 建议）" in rendered
    assert "  - [ ] disagree（不同意 AI 建议）" in rendered
    assert "Source state: **clear**" in rendered

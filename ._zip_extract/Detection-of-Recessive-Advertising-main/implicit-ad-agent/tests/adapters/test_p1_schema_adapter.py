"""P1 authoritative-schema adapter tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from impad.adapters.p1_schema import post_record_from_content_record


REPO_ROOT = Path(__file__).resolve().parents[3]


def _first_content_record() -> dict:
    payload = json.loads(
        (REPO_ROOT / "data/synthetic/simulated_posts_v1.json").read_text(
            encoding="utf-8"
        )
    )
    return payload["content_records"][0]


def _v12_content_record(schema_version: str = "1.2") -> dict:
    return {
        "schema_version": schema_version,
        "post_id": "post_v12_bilibili_001",
        "platform": "bilibili",
        "source_type": "manual_public_collection",
        "blogger_id": "blogger_v12_001",
        "published_at": "2026-07-28T12:00:00+08:00",
        "title": "测试视频",
        "content_group_id": None,
        "text": "本期视频介绍测试产品",
        "media": [
            {
                "media_id": "media_v12_001",
                "type": "image",
                "ref": "media/post_v12_bilibili_001/00.jpg",
                "sha256": None,
                "phash": None,
                "ocr_text": None,
                "source_url": None,
                "caption": "封面",
                "is_content": True,
            }
        ],
        "comments": [],
        "blogger_history_refs": [],
        "provenance": {
            "source_ref_hash": "source-v12-001",
            "collected_at": "2026-07-28T12:01:00+08:00",
            "collector": "A",
            "terms_checked_at": "2026-07-28",
            "llm_mode": None,
            "llm_confidence": None,
            "llm_needs_review": False,
            "llm_notes": None,
        },
        "privacy": {
            "anonymized": True,
            "contains_sensitive_data": False,
        },
    }


def test_p1_adapter_validates_and_maps_real_synthetic_fixture():
    record = _first_content_record()

    post = post_record_from_content_record(record)

    assert post.post_id == "post_explicit_sponsor"
    assert post.creator_id == "blogger_style_001"
    assert post.media[0].ref == "media/post_explicit_sponsor/01.jpg"
    assert post.capture_status.source == "p1_schema_v1"
    assert post.capture_status.can_assess_disclosure is True
    assert record["blogger_id"] == "blogger_style_001"


def test_p1_adapter_validates_and_maps_schema_v12_record():
    post = post_record_from_content_record(_v12_content_record())

    assert post.schema_version == "1.2"
    assert post.platform == "bilibili"
    assert post.creator_id == "blogger_v12_001"
    assert post.media[0].ref == "media/post_v12_bilibili_001/00.jpg"


def test_p1_adapter_accepts_schema_v11_through_v12_validator():
    post = post_record_from_content_record(_v12_content_record("1.1"))

    assert post.schema_version == "1.1"


def test_p1_adapter_rejects_unknown_schema_version():
    with pytest.raises(ValueError, match=r"unsupported schema_version: 9.9"):
        post_record_from_content_record(_v12_content_record("9.9"))


def test_p1_adapter_rejects_unknown_v12_fields():
    record = _v12_content_record()
    record["invented_field"] = "must fail"

    with pytest.raises(ValueError, match=r"invented_field"):
        post_record_from_content_record(record)


def test_p1_adapter_rejects_unknown_fields_instead_of_dropping_them():
    record = deepcopy(_first_content_record())
    record["invented_field"] = "must fail"

    with pytest.raises(ValueError, match=r"invented_field"):
        post_record_from_content_record(record)


def test_p1_adapter_reports_missing_required_field_path():
    record = deepcopy(_first_content_record())
    del record["privacy"]

    with pytest.raises(ValueError, match=r"privacy"):
        post_record_from_content_record(record)


def test_p1_adapter_marks_unresolved_history_as_partial_capture():
    record = deepcopy(_first_content_record())
    record["blogger_history_refs"] = ["post_prior_1"]

    post = post_record_from_content_record(record)

    history = post.capture_status.modalities["history"]
    assert history.status == "partial"
    assert history.missing_fields == ["resolved_history"]
    assert post.history == []
    assert post.history_refs == ["post_prior_1"]


def test_p1_adapter_does_not_claim_disclosure_coverage_for_video():
    record = deepcopy(_first_content_record())
    record["media"][0]["type"] = "video"

    post = post_record_from_content_record(record)

    assert post.capture_status.can_assess_disclosure is False

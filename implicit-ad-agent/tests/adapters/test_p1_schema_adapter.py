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


def test_p1_adapter_validates_and_maps_real_synthetic_fixture():
    record = _first_content_record()

    post = post_record_from_content_record(record)

    assert post.post_id == "post_explicit_sponsor"
    assert post.creator_id == "blogger_style_001"
    assert post.media[0].ref == "media/post_explicit_sponsor/01.jpg"
    assert post.capture_status.source == "p1_schema_v1"
    assert post.capture_status.can_assess_disclosure is True
    assert record["blogger_id"] == "blogger_style_001"


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

"""Governance checks for synthetic, offline platform fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import re

from impad.adapters.platforms.embedded_json import extract_assigned_json
from impad.contracts import PostRecord


FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "platforms"
CASES = sorted(
    (FIXTURE_ROOT / "xiaohongshu").iterdir()
) + sorted((FIXTURE_ROOT / "bilibili").iterdir())
EXPECTED_FILES = {
    "source.html",
    "source_state.json",
    "manifest.json",
    "expected_post.json",
}
EXPECTED_FIXTURES = {
    ("xiaohongshu", "normal_complete"): {
        "content_type": "normal",
        "expected_modalities": {
            "text": "complete",
            "image": "partial",
            "comment": "complete",
            "disclosure": "complete",
        },
    },
    ("xiaohongshu", "video_missing_comments"): {
        "content_type": "video",
        "expected_modalities": {
            "text": "complete",
            "image": "unsupported",
            "comment": "missing",
            "disclosure": "complete",
        },
    },
    ("bilibili", "video_no_images"): {
        "content_type": "video",
        "expected_modalities": {
            "text": "complete",
            "image": "unsupported",
            "comment": "unsupported",
            "disclosure": "complete",
        },
    },
    ("bilibili", "opus_partial_images"): {
        "content_type": "opus",
        "expected_modalities": {
            "text": "complete",
            "image": "partial",
            "comment": "unsupported",
            "disclosure": "complete",
        },
    },
    ("bilibili", "article_missing_disclosure_surface"): {
        "content_type": "article",
        "expected_modalities": {
            "text": "complete",
            "image": "partial",
            "comment": "unsupported",
            "disclosure": "missing",
        },
    },
}
EXPECTED_MANIFEST_KEYS = {
    "fixture_version",
    "synthetic",
    "contains_real_user_data",
    "network_required",
    "platform",
    "content_type",
    "expected_modalities",
    "real_platform_compatibility_verified",
    "terms_approved",
}
GOVERNANCE_FLAGS = {
    "synthetic",
    "contains_real_user_data",
    "network_required",
    "real_platform_compatibility_verified",
    "terms_approved",
}
VALID_MODALITY_STATUSES = {"complete", "partial", "missing", "unsupported"}


def test_all_platform_fixture_manifests_are_explicitly_synthetic():
    assert len(CASES) == 5
    assert {
        (case.parent.name, case.name)
        for case in CASES
    } == set(EXPECTED_FIXTURES)
    assert all(case.is_dir() for case in CASES)
    for case in CASES:
        assert {
            path.name for path in case.iterdir()
        } == EXPECTED_FILES
        assert all(
            (case / filename).is_file()
            for filename in EXPECTED_FILES
        )
        manifest = json.loads((case / "manifest.json").read_text("utf-8"))
        expected = EXPECTED_FIXTURES[(case.parent.name, case.name)]
        assert set(manifest) == EXPECTED_MANIFEST_KEYS
        assert manifest["fixture_version"] == "platform-fixture-v1"
        assert manifest["platform"] == case.parent.name
        assert manifest["content_type"] == expected["content_type"]
        assert manifest["expected_modalities"] == (
            expected["expected_modalities"]
        )
        assert set(manifest["expected_modalities"]) == {
            "text",
            "image",
            "comment",
            "disclosure",
        }
        assert all(
            status in VALID_MODALITY_STATUSES
            for status in manifest["expected_modalities"].values()
        )
        assert all(
            isinstance(manifest[field], bool)
            for field in GOVERNANCE_FLAGS
        )
        assert manifest["synthetic"] is True
        assert manifest["contains_real_user_data"] is False
        assert manifest["network_required"] is False
        assert manifest["real_platform_compatibility_verified"] is False
        assert manifest["terms_approved"] is False
        PostRecord.model_validate_json(
            (case / "expected_post.json").read_text("utf-8")
        )


def test_platform_fixture_html_matches_checked_in_source_state():
    for case in CASES:
        source_state = json.loads(
            (case / "source_state.json").read_text("utf-8")
        )
        html_state = extract_assigned_json(
            (case / "source.html").read_text("utf-8"),
            "window.__INITIAL_STATE__",
        )
        assert html_state == source_state, case


def test_platform_fixtures_contain_no_secret_or_direct_identifier_patterns():
    forbidden = re.compile(
        r"(?i)(cookie\s*:|authorization\s*:|bearer\s+|"
        r"api[_-]?key|secret[_-]?key|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"\b1[3-9]\d{9}\b|[A-Z0-9._%+-]+@(?!example\.test))"
    )
    for case in CASES:
        for path in case.iterdir():
            assert forbidden.search(path.read_text("utf-8")) is None, path

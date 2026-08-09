"""Governance checks for synthetic, offline platform fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import re


FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "platforms"
CASES = sorted(
    (FIXTURE_ROOT / "xiaohongshu").iterdir()
) + sorted((FIXTURE_ROOT / "bilibili").iterdir())


def test_all_platform_fixture_manifests_are_explicitly_synthetic():
    assert len(CASES) == 5
    assert all(case.is_dir() and any(case.iterdir()) for case in CASES)
    for case in CASES:
        manifest = json.loads((case / "manifest.json").read_text("utf-8"))
        assert manifest["synthetic"] is True
        assert manifest["contains_real_user_data"] is False
        assert manifest["network_required"] is False
        assert manifest["real_platform_compatibility_verified"] is False
        assert manifest["terms_approved"] is False


def test_platform_fixtures_contain_no_secret_or_direct_identifier_patterns():
    forbidden = re.compile(
        r"(?i)(cookie\s*:|authorization\s*:|bearer\s+|"
        r"api[_-]?key|secret[_-]?key|BEGIN (RSA |EC )?PRIVATE KEY|"
        r"\b1[3-9]\d{9}\b|[A-Z0-9._%+-]+@(?!example\.test))"
    )
    for case in CASES:
        for path in case.iterdir():
            assert forbidden.search(path.read_text("utf-8")) is None, path

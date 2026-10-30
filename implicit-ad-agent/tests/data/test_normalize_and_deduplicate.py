from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "data-tooling"
    / "annotation"
    / "normalize_and_deduplicate.py"
)
SPEC = importlib.util.spec_from_file_location("normalize_and_deduplicate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_duplicate_post_id_keeps_richest_record() -> None:
    records = [
        {
            "post_id": "post_same",
            "platform": "wechat_official_account",
            "text": "short",
            "media": [],
        },
        {
            "post_id": "post_same",
            "platform": "wechat_official_account",
            "text": "a substantially longer and more complete record",
            "media": [{"ref": "media/example.jpg"}],
        },
    ]

    deduped, report = MODULE.deduplicate(records)

    assert len(deduped) == 1
    assert deduped[0]["text"].startswith("a substantially longer")
    assert report["duplicate_post_ids_removed"] == 1
    assert report["duplicates_removed"] == 1


def test_exact_duplicate_content_with_different_ids_is_removed() -> None:
    records = [
        {
            "post_id": "post_one",
            "platform": "wechat_official_account",
            "text": "same content",
            "media": [],
        },
        {
            "post_id": "post_two",
            "platform": "wechat_official_account",
            "text": "same content",
            "media": [],
        },
    ]

    deduped, report = MODULE.deduplicate(records)

    assert len(deduped) == 1
    assert report["exact_content_duplicates_removed"] == 1

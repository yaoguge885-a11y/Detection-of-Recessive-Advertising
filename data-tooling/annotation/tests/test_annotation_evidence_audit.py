import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("evidence_audit", Path(__file__).resolve().parents[2] / "audit_annotation_evidence.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def row(pid, **kwargs):
    return {"post_id": pid, "platform": "bilibili", "media": [], "text": "", "published_at": "2026-01-01", "blogger_id": "synthetic_creator", "content_group_id": pid, **kwargs}


def test_video_hints_and_local_files_do_not_imply_complete_video_evidence(tmp_path):
    (tmp_path / "icon.jpg").write_bytes(b"synthetic")
    records = [row("a", text="投稿了视频", media=[{"type": "image", "ref": "icon.jpg"}]), row("b", text="普通文字帖子")]
    result, details = audit.audit_records(records, tmp_path)
    assert result["counts"]["video_hint_without_video_entry"] == 1
    assert result["counts"]["video_hint_with_only_nonvideo_media"] == 1
    assert result["counts"]["records_with_local_video"] == 0
    assert "video_hint_without_video_entry" in details[0]["flags"]


def test_remote_entry_is_not_claimed_as_watched_or_locally_available(tmp_path):
    result, _ = audit.audit_records([row("remote", media=[{"type": "video", "source_url": "https://example.invalid/private-video"}])], tmp_path)
    assert result["counts"]["records_with_unpinned_remote_video"] == 1
    assert result["counts"]["records_with_local_video"] == 0
    assert "https://" not in json.dumps(result)
    assert "remote" not in result


def test_paths_cannot_escape_media_base_and_missing_refs_are_distinct(tmp_path):
    result, _ = audit.audit_records([row("paths", media=[{"type": "image", "ref": "../outside.jpg"}, {"type": "image", "ref": "missing.jpg"}])], tmp_path)
    assert result["media_reference_states"] == {"unsafe": 1, "missing": 1}
    assert result["counts"]["records_with_unsafe_refs"] == 1
    assert result["counts"]["records_with_missing_local_refs"] == 1


def test_aggregate_has_no_record_ids_text_urls_or_automatic_labels(tmp_path):
    records = [row("private-id", text="private-text", published_at=""), row("private-id", text="private-text")]
    result, details = audit.audit_records(records, tmp_path)
    assert result["duplicate_row_count"] == 1
    assert result["counts"]["records_missing_published_at"] == 1
    serialized = json.dumps(result)
    assert "private-id" not in serialized and "private-text" not in serialized
    assert details[0]["post_id"] == "private-id"
    assert all("label" not in d for d in details)


def test_image_hint_is_collection_warning_not_label(tmp_path):
    result, details = audit.audit_records([row("image", text="查看大图", media=[])], tmp_path)
    assert result["counts"]["image_hint_without_image_entry"] == 1
    assert details[0]["flags"] == ["image_hint_without_image_entry"]


def test_invalid_record_structure_fails_with_no_content_echo(tmp_path):
    with pytest.raises(ValueError, match="record 1"):
        audit.audit_records([{"text": "sensitive"}], tmp_path)

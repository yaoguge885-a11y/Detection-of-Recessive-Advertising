"""Manual and legacy-input adapter tests."""
from __future__ import annotations

from impad.adapters.manual import post_record_from_manual


def test_manual_adapter_normalizes_legacy_comments_history_and_creator():
    post = post_record_from_manual(
        {
            "text": "亲测好用，链接在评论区",
            "blogger": "小美",
            "comments": ["求链接", "已下单"],
            "history": ["读书笔记", "今天散步"],
        }
    )

    assert post.post_id.startswith("post_manual_")
    assert post.creator_id.startswith("blogger_manual_")
    assert [item.text for item in post.comments] == ["求链接", "已下单"]
    assert [item.text for item in post.history] == ["读书笔记", "今天散步"]
    assert all(item.creator_id == post.creator_id for item in post.history)
    assert post.capture_status.can_assess_disclosure is False
    assert post.privacy.anonymized is None
    assert post.privacy.contains_sensitive_data is None


def test_manual_adapter_is_deterministic_for_the_same_input():
    raw = {"text": "同一条内容", "blogger": "同一作者"}

    first = post_record_from_manual(raw)
    second = post_record_from_manual(raw)

    assert first.post_id == second.post_id
    assert first.creator_id == second.creator_id


def test_manual_adapter_only_marks_disclosure_assessable_for_complete_capture(
    tmp_path,
):
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"fixture")

    post = post_record_from_manual(
        {
            "text": "完整手工输入",
            "image_path": str(image_path),
            "capture_complete": True,
        }
    )

    assert post.media[0].ref == str(image_path)
    assert post.capture_status.modalities["image"].status == "complete"
    assert post.capture_status.can_assess_disclosure is True


def test_manual_adapter_does_not_treat_remote_url_as_local_image_capability():
    post = post_record_from_manual(
        {
            "text": "只有远程图片URL",
            "image_url": "https://example.com/image.jpg",
            "capture_complete": True,
        }
    )

    assert post.media[0].ref == "https://example.com/image.jpg"
    assert post.capture_status.modalities["image"].status == "partial"
    assert post.capture_status.can_assess_disclosure is False


def test_manual_adapter_does_not_claim_disclosure_coverage_for_video():
    post = post_record_from_manual(
        {
            "text": "正文已完整采集",
            "capture_complete": True,
            "media": [
                {
                    "media_id": "media_video_1",
                    "type": "video",
                    "ref": "video.mp4",
                }
            ],
        }
    )

    assert post.capture_status.can_assess_disclosure is False

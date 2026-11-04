from __future__ import annotations

from pathlib import Path

from scripts.data.annotation import manual_review_annotate


def _post_with_null_media_ref() -> dict:
    return {
        "post_id": "post_null_media",
        "title": "视频帖子",
        "text": "正文仍然可以用于人工判断。",
        "platform": "bilibili",
        "blogger_id": "blogger_test",
        "published_at": None,
        "media": [{"type": "video", "ref": None}],
        "comments": [],
    }


def test_format_post_display_handles_null_media_ref() -> None:
    rendered = manual_review_annotate.format_post_display(
        _post_with_null_media_ref(), 2, 100
    )

    assert "post_null_media" in rendered
    assert "(无本地引用)" in rendered


def test_view_images_skips_null_media_ref(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "a")
    monkeypatch.setattr(
        manual_review_annotate,
        "_open_file",
        lambda _: (_ for _ in ()).throw(AssertionError("must not open a null ref")),
    )

    assert manual_review_annotate.view_images(_post_with_null_media_ref(), tmp_path) == 0

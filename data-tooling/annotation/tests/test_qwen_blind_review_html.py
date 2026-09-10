from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_m1_qwen_blind_html as generator


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_blind_delivery_contains_no_model_suggestions_and_keeps_roles_isolated(tmp_path):
    source = tmp_path / "candidates.jsonl"
    media_root = tmp_path / "media_root"
    media_dir = media_root / "media"
    media_dir.mkdir(parents=True)
    (media_dir / "one.jpg").write_bytes(b"synthetic-image")
    _write_jsonl(
        source,
        [
            {
                "post_id": "post_a",
                "platform": "synthetic",
                "title": "测试标题",
                "text": "测试正文",
                "comments": [{"comment_id": "c1", "text": "测试评论"}],
                "media": [{"type": "image", "ref": "media/one.jpg"}],
            },
        ],
    )
    guide = tmp_path / "guide.md"
    guide.write_text("GUIDE_SENTINEL\nuncertain 必须保留", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "status": "awaiting_A_B_blind_labels",
                "sample_count": 1,
                "source": {"sha256": _sha256(source), "record_count": 1},
                "items": [{"ordinal": 1, "post_id": "post_a"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "delivery"

    result = generator.generate_delivery(
        repo_root=tmp_path,
        manifest_path=manifest,
        input_path=source,
        guide_path=guide,
        media_base=media_root,
        output_root=output_root,
        roles=("A", "B"),
    )

    html_a = (output_root / "A" / "M1_Blind_Human_Review_A.html").read_text(
        encoding="utf-8"
    )
    html_b = (output_root / "B" / "M1_Blind_Human_Review_B.html").read_text(
        encoding="utf-8"
    )
    assert result["sample_count"] == 1
    assert result["missing_media_count"] == 0
    assert "post_a" in html_a and "GUIDE_SENTINEL" in html_a
    assert "model_label" not in html_a
    assert "model_confidence" not in html_a
    assert '"qwen_visible":false' in html_a
    assert 'annotation_method:"human"' in html_a
    assert "media_review_audit" in html_a
    assert "item.media.length&&!r.media_review_confirmed" in html_a
    assert "r.media_review_confirmed||item.media.length===0" in html_a
    assert '"role":"A"' in html_a
    assert '"role":"B"' in html_b
    assert "M1_Blind_Human_Review_B.html" not in html_a
    assert (output_root / "COORDINATOR" / "delivery_manifest.json").is_file()
    assert (output_root / "COORDINATOR" / "SHA256SUMS.txt").is_file()


def test_missing_media_is_explicitly_reported_without_external_fallback(tmp_path):
    source = tmp_path / "candidates.jsonl"
    _write_jsonl(
        source,
        [
            {
                "post_id": "post_missing",
                "platform": "synthetic",
                "title": "missing",
                "text": "text",
                "media": [{"type": "video", "ref": None}],
            }
        ],
    )
    guide = tmp_path / "guide.md"
    guide.write_text("GUIDE", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "sample_count": 1,
                "qwen_run_performed": False,
                "source": {"sha256": _sha256(source)},
                "items": [{"ordinal": 1, "post_id": "post_missing"}],
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "delivery"
    (tmp_path / "media").mkdir()
    result = generator.generate_delivery(
        repo_root=tmp_path,
        manifest_path=manifest,
        input_path=source,
        guide_path=guide,
        media_base=tmp_path / "media",
        output_root=output_root,
        roles=("A",),
    )
    html = (output_root / "A" / "M1_Blind_Human_Review_A.html").read_text(
        encoding="utf-8"
    )
    delivery_manifest = json.loads(
        (output_root / "COORDINATOR" / "delivery_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["missing_media_count"] == 1
    assert '"missing_media_count":1' in html
    assert "completed_with_declared_evidence_gaps" in html
    assert delivery_manifest["missing_media_items"][0]["post_id"] == "post_missing"


def test_allowlisted_remote_video_link_requires_explicit_human_review_status(tmp_path):
    source = tmp_path / "candidates.jsonl"
    remote_url = "https://www.bilibili.com/video/BV1Test123AbC"
    _write_jsonl(
        source,
        [
            {
                "post_id": "post_remote",
                "platform": "bilibili",
                "title": "remote video",
                "text": "text",
                "media": [
                    {"type": "video", "ref": None, "source_url": remote_url}
                ],
            }
        ],
    )
    guide = tmp_path / "guide.md"
    guide.write_text("GUIDE", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "sample_count": 1,
                "qwen_run_performed": False,
                "source": {"sha256": _sha256(source)},
                "items": [{"ordinal": 1, "post_id": "post_remote"}],
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "delivery"
    (tmp_path / "media").mkdir()

    result = generator.generate_delivery(
        repo_root=tmp_path,
        manifest_path=manifest,
        input_path=source,
        guide_path=guide,
        media_base=tmp_path / "media",
        output_root=output_root,
        roles=("A",),
    )

    html = (output_root / "A" / "M1_Blind_Human_Review_A.html").read_text(
        encoding="utf-8"
    )
    delivery_manifest = json.loads(
        (output_root / "COORDINATOR" / "delivery_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["missing_media_count"] == 0
    assert result["remote_link_media_count"] == 1
    assert delivery_manifest["remote_link_media_count"] == 1
    assert delivery_manifest["remote_link_media_items"][0]["post_id"] == "post_remote"
    assert remote_url in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "在新标签页打开源视频" in html
    assert "已成功打开并检查视频" in html
    assert "链接无法访问或内容不可用" in html
    assert "remote_media_statuses" in html
    assert "remote_open_attempts" in html
    assert "completed_with_remote_unpinned_media_evidence" in html


def test_non_allowlisted_remote_url_remains_an_explicit_evidence_gap(tmp_path):
    source = tmp_path / "candidates.jsonl"
    unsafe_url = "https://example.invalid/video/BV1Unsafe"
    _write_jsonl(
        source,
        [
            {
                "post_id": "post_unsafe_remote",
                "platform": "synthetic",
                "title": "unsafe remote",
                "text": "text",
                "media": [
                    {"type": "video", "ref": None, "source_url": unsafe_url}
                ],
            }
        ],
    )
    guide = tmp_path / "guide.md"
    guide.write_text("GUIDE", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "sample_count": 1,
                "qwen_run_performed": False,
                "source": {"sha256": _sha256(source)},
                "items": [{"ordinal": 1, "post_id": "post_unsafe_remote"}],
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "delivery"
    (tmp_path / "media").mkdir()

    result = generator.generate_delivery(
        repo_root=tmp_path,
        manifest_path=manifest,
        input_path=source,
        guide_path=guide,
        media_base=tmp_path / "media",
        output_root=output_root,
        roles=("A",),
    )

    html = (output_root / "A" / "M1_Blind_Human_Review_A.html").read_text(
        encoding="utf-8"
    )
    assert result["missing_media_count"] == 1
    assert result["remote_link_media_count"] == 0
    assert unsafe_url not in html

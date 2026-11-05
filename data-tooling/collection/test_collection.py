#!/usr/bin/env python3
"""标注前置采集方案的单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backfill  # noqa: E402
import intake_cli  # noqa: E402

SALT = "testsalt"
URL = "https://www.bilibili.com/video/BV1PgKr6uEvE"
NOW = "2026-11-05T12:00:00+08:00"


def make_record(**overrides):
    kwargs = dict(
        url=URL,
        viewed_media="full",
        disclosure_status="absent_complete",
        disclosure_note="看了简介和置顶评论",
        draft_label="暗广",
        draft_confidence=0.8,
        draft_evidence="单品牌只夸不提缺点",
        annotator_id="A",
        title="测试标题",
        text="正文",
        salt=SALT,
    )
    kwargs.update(overrides)
    return intake_cli.build_record(**kwargs)


class TestPostIdDerivation:
    def test_deterministic(self):
        assert intake_cli.derive_post_id(URL, SALT) == intake_cli.derive_post_id(URL, SALT)

    def test_prefix_and_length(self):
        post_id = intake_cli.derive_post_id(URL, SALT)
        assert post_id.startswith("post_")
        assert len(post_id) == len("post_") + 32

    def test_matches_existing_pool_convention(self):
        """与既有候选池的 post_id 生成方式一致（sha256(salt+url)[:32]）。"""
        import hashlib

        expected = "post_" + hashlib.sha256((SALT + URL).encode("utf-8")).hexdigest()[:32]
        assert intake_cli.derive_post_id(URL, SALT) == expected

    def test_whitespace_insensitive(self):
        assert intake_cli.derive_post_id(f"  {URL}  ", SALT) == intake_cli.derive_post_id(URL, SALT)

    def test_differs_by_url(self):
        other = "https://www.bilibili.com/video/BV1xxxxxxxxx"
        assert intake_cli.derive_post_id(URL, SALT) != intake_cli.derive_post_id(other, SALT)

    def test_differs_by_salt(self):
        assert intake_cli.derive_post_id(URL, SALT) != intake_cli.derive_post_id(URL, "other")


class TestPlatformDetection:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.bilibili.com/video/BV1PgKr6uEvE", "bilibili"),
            ("https://b23.tv/abc123", "bilibili"),
            ("https://mp.weixin.qq.com/s/abc", "wechat_official_account"),
            ("https://www.xiaohongshu.com/explore/abc", "xiaohongshu"),
            ("https://www.douyin.com/video/123", "douyin"),
            ("https://weibo.com/123/abc", "weibo"),
            ("https://example.com/post", "other"),
        ],
    )
    def test_detect(self, url, expected):
        assert intake_cli.detect_platform(url) == expected


class TestCollectionComplete:
    @pytest.mark.parametrize(
        "viewed,status,expected",
        [
            ("full", "ok", "complete"),
            ("full", "partial", "incomplete"),
            ("full", "failed", "incomplete"),
            ("full", "pending", "incomplete"),
            ("partial", "ok", "incomplete"),
            ("partial", "failed", "incomplete"),
            ("none", "ok", "unknown"),
            ("none", "failed", "unknown"),
        ],
    )
    def test_derive(self, viewed, status, expected):
        assert intake_cli.derive_collection_complete(viewed, status) == expected

    def test_backfill_module_agrees(self):
        for viewed in ("full", "partial", "none"):
            for status in ("ok", "partial", "failed", "pending"):
                assert intake_cli.derive_collection_complete(
                    viewed, status
                ) == backfill.derive_collection_complete(viewed, status)


class TestBuildRecord:
    def test_authoritative_fields_present(self):
        record = make_record()
        intake = record["intake"]
        assert intake["viewed_media"] == "full"
        assert intake["disclosure_status"] == "absent_complete"
        assert intake["disclosure_note"] == "看了简介和置顶评论"
        assert intake["draft_label"] == "暗广"
        assert intake["annotator_id"] == "A"

    def test_initial_state(self):
        record = make_record()
        assert record["schema_version"] == "1.3"
        assert record["backfill"]["status"] == "pending"
        assert record["disclosure_status"] == "absent_complete"
        assert record["collection_complete"] == "incomplete"

    def test_blogger_id_unknown_at_intake(self):
        """录入时不知博主，必须留空而不是猜。"""
        assert make_record()["blogger_id"] is None

    def test_no_draft_label_allowed(self):
        record = make_record(draft_label=None, draft_confidence=None, draft_evidence=None)
        assert record["intake"]["draft_label"] is None

    def test_provenance_and_collected_present(self):
        record = make_record()
        for key in ("source_ref_hash", "collected_at", "collector", "terms_checked_at"):
            assert key in record["provenance"]
        assert record["_collected"]["source_url"] == URL


class TestApplyBackfill:
    def test_success_sets_complete(self):
        record = make_record()
        fetched = {
            "title": "真标题",
            "text": "真正文",
            "media": [{"media_id": "m1", "type": "video"}],
            "comments": [{"comment_id": "c1", "text": "评论"}],
            "blogger_id": "blogger_abc123",
            "published_at": "2026-01-01T00:00:00+08:00",
            "blogger_history_refs": ["ref1"],
        }
        updated = backfill.apply_backfill(record, fetched, now=NOW)
        assert updated["backfill"]["status"] == "ok"
        assert updated["collection_complete"] == "complete"
        assert updated["blogger_id"] == "blogger_abc123"
        assert updated["title"] == "真标题"
        assert set(updated["backfill"]["fields_filled"]) == set(backfill.BACKFILL_OWNED_FIELDS)

    def test_failure_keeps_intake_judgement(self):
        """回填失败不得作废人工判定——这是本方案的核心保证。"""
        record = make_record()
        updated = backfill.apply_backfill(record, None, error="timeout", now=NOW)
        assert updated["backfill"]["status"] == "failed"
        assert updated["backfill"]["error"] == "timeout"
        assert updated["collection_complete"] == "incomplete"
        assert updated["intake"] == record["intake"]
        assert updated["disclosure_status"] == "absent_complete"

    def test_never_overwrites_intake(self):
        record = make_record()
        fetched = {
            "intake": {"viewed_media": "none", "disclosure_status": "present"},
            "title": "抓到的标题",
        }
        updated = backfill.apply_backfill(record, fetched, now=NOW)
        assert updated["intake"]["viewed_media"] == "full"
        assert updated["intake"]["disclosure_status"] == "absent_complete"

    def test_partial_fill(self):
        record = make_record()
        updated = backfill.apply_backfill(record, {"title": "只有标题"}, now=NOW)
        assert updated["backfill"]["status"] == "partial"
        assert updated["backfill"]["fields_filled"] == ["title"]
        assert updated["collection_complete"] == "incomplete"

    def test_empty_result_is_failure(self):
        record = make_record()
        updated = backfill.apply_backfill(record, {}, now=NOW)
        assert updated["backfill"]["status"] == "failed"

    def test_viewed_none_stays_unknown_even_on_success(self):
        record = make_record(viewed_media="none")
        fetched = {f: "x" for f in backfill.BACKFILL_OWNED_FIELDS}
        updated = backfill.apply_backfill(record, fetched, now=NOW)
        assert updated["backfill"]["status"] == "ok"
        assert updated["collection_complete"] == "unknown"


class TestSchemaValidation:
    @pytest.fixture(scope="class")
    @classmethod
    def schema(cls):
        jsonschema = pytest.importorskip("jsonschema")
        path = HERE / "schema_v1_3.json"
        return jsonschema.Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))

    def test_fresh_record_valid(self, schema):
        errors = list(schema.iter_errors(make_record()))
        assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]

    def test_backfilled_record_valid(self, schema):
        record = make_record()
        fetched = {f: "x" for f in backfill.BACKFILL_OWNED_FIELDS}
        fetched["blogger_id"] = "blogger_abc123"
        fetched["media"] = []
        fetched["comments"] = []
        fetched["blogger_history_refs"] = []
        updated = backfill.apply_backfill(record, fetched, now=NOW)
        errors = list(schema.iter_errors(updated))
        assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]

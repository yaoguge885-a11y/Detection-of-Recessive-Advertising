#!/usr/bin/env python3
"""manual_entry（人工采集 + 标注一次完成）的单元测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import manual_entry as m  # noqa: E402

SALT = "testsalt"
URL = "https://www.bilibili.com/video/BV1YjPszpEo7"


def make_record(**overrides):
    kwargs = dict(
        url=URL,
        platform="bilibili",
        title="测试标题",
        desc="测试简介",
        text="测试正文",
        tags=["汽车", "科普"],
        comments=m.parse_comments(["[新]评论一 | 12", "[热]评论二"]),
        creator_key="硬件茶谈",
        viewed_media="full",
        disclosure_status="absent_complete",
        disclosure_note="看完视频，无广告标识",
        label="暗广",
        confidence=0.8,
        evidence_codes=["C", "P"],
        evidence_text="单品牌正面铺垫无披露",
        uncertain_reason=None,
        annotator_id="A",
        salt=SALT,
        reviewed_all_comments=True,
    )
    kwargs.update(overrides)
    return m.build_record(**kwargs)


class TestTagParsing:
    def test_chinese_and_english_separators(self):
        assert m.parse_tags("汽车，科普,莲花、测试") == ["汽车", "科普", "莲花", "测试"]

    def test_strips_hash_and_dedupes(self):
        assert m.parse_tags("#汽车# #科普# 汽车") == ["汽车", "科普"]

    def test_empty(self):
        assert m.parse_tags("   ") == []


class TestCommentParsing:
    def test_latest_marker_with_like(self):
        result = m.parse_comments(["[新]然后莲花破产了 | 42"])
        assert result[0]["text"] == "然后莲花破产了"
        assert result[0]["sort_source"] == ["latest"]
        assert result[0]["like_count"] == 42

    def test_hot_marker(self):
        result = m.parse_comments(["[热]产品决策难崩"])
        assert result[0]["sort_source"] == ["hot"]

    def test_combined_marker_single_token(self):
        result = m.parse_comments(["[新热]既新又热"])
        assert result[0]["sort_source"] == ["latest", "hot"]
        assert result[0]["text"] == "既新又热"

    def test_combined_marker_stacked(self):
        """[热][新] 连写时两个标记都要剥掉，不能把 [新] 留在正文里。"""
        result = m.parse_comments(["[热][新]宣传减重结果3吨 | 18"])
        assert result[0]["text"] == "宣传减重结果3吨"
        assert result[0]["sort_source"] == ["hot", "latest"]
        assert result[0]["like_count"] == 18

    def test_no_marker_keeps_empty_sources(self):
        result = m.parse_comments(["纯评论"])
        assert result[0]["sort_source"] == []
        assert result[0]["text"] == "纯评论"

    def test_pipe_without_number_is_text(self):
        result = m.parse_comments(["a|b"])
        assert result[0]["text"] == "a|b"
        assert result[0]["like_count"] == 0

    def test_blank_lines_skipped(self):
        result = m.parse_comments(["", "   ", "有效"])
        assert len(result) == 1

    def test_ids_are_unique(self):
        result = m.parse_comments(["a", "b", "c"])
        assert len({c["comment_id"] for c in result}) == 3


class TestDerivation:
    def test_post_id_stable(self):
        assert m.derive_post_id(URL, SALT) == m.derive_post_id(URL, SALT)
        assert m.derive_post_id(URL, SALT).startswith("post_")

    def test_blogger_id_from_creator(self):
        assert m.derive_blogger_id("硬件茶谈", SALT).startswith("blogger_")

    def test_blogger_id_empty(self):
        assert m.derive_blogger_id("", SALT) is None

    def test_collection_complete_from_viewed(self):
        assert m.derive_collection_complete("full") == "complete"
        assert m.derive_collection_complete("partial") == "incomplete"
        assert m.derive_collection_complete("none") == "unknown"

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://www.bilibili.com/video/BV1", "bilibili"),
            ("https://mp.weixin.qq.com/s/x", "wechat_official_account"),
            ("https://example.com/x", "other"),
        ],
    )
    def test_platform(self, url, expected):
        assert m.detect_platform(url) == expected


class TestRecord:
    def test_label_and_content_together(self):
        """核心要求：内容与标签在同一条记录里完成。"""
        record = make_record()
        assert record["title"] == "测试标题"
        assert record["desc"] == "测试简介"
        assert record["tags"] == ["汽车", "科普"]
        assert len(record["comments"]) == 2
        assert record["annotation"]["label"] == "暗广"
        assert record["annotation"]["confidence"] == 0.8
        assert record["annotation"]["evidence_codes"] == ["C", "P"]

    def test_manual_mode_flags(self):
        record = make_record()
        assert record["annotation_method"] == "human"
        assert record["annotation"]["collection_mode"] == "manual_platform"
        assert record["backfill"]["status"] == "ok"

    def test_complete_when_viewed_fully(self):
        """人工采集时完整性天然可确认，这是相对爬虫流程的关键改善。"""
        assert make_record()["collection_complete"] == "complete"

    def test_incomplete_when_partial(self):
        assert make_record(viewed_media="partial")["collection_complete"] == "incomplete"

    def test_annotation_post_id_matches(self):
        record = make_record()
        assert record["annotation"]["post_id"] == record["post_id"]

    def test_desc_separate_from_text(self):
        record = make_record(desc="这是简介", text="这是正文")
        assert record["desc"] == "这是简介"
        assert record["text"] == "这是正文"

    def test_comments_meta_aggregates_sorts(self):
        record = make_record()
        assert set(record["comments_meta"]["sorts_used"]) == {"latest", "hot"}
        assert record["comments_meta"]["returned"] == 2
        assert record["comments_meta"]["degraded"] is False


class TestSchema:
    @pytest.fixture(scope="class")
    @classmethod
    def schema(cls):
        jsonschema = pytest.importorskip("jsonschema")
        path = HERE / "schema_v1_4.json"
        return jsonschema.Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))

    def test_record_valid(self, schema):
        errors = list(schema.iter_errors(make_record()))
        assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]

    def test_uncertain_with_reason_valid(self, schema):
        record = make_record(
            label="uncertain", confidence=0.4, evidence_codes=[],
            uncertain_reason="评论未看完，披露状态无法确认",
        )
        assert not list(schema.iter_errors(record))

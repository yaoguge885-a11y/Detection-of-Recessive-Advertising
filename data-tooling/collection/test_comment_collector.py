#!/usr/bin/env python3
"""comment_collector 的单元测试（完全离线，不依赖网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from comment_collector import (  # noqa: E402
    ANONYMOUS_CAP,
    CommentPage,
    collect_comments_dual_sort,
    required_cookies_present,
    session_from_storage_state,
)


def reply(rpid, text="c", like=0, ctime=None, mid="u1", pinned=False):
    return {
        "comment_id": str(rpid),
        "author_id": mid,
        "text": text,
        "like_count": like,
        "is_pinned": pinned,
        "created_at": ctime,
    }


class FakePlatform:
    """可构造的假平台：按排序返回不同顺序的评论。"""

    def __init__(self, latest, hot, total=None, page_size=20, fail_sorts=(), anonymous=False):
        self.latest = latest
        self.hot = hot
        self.total = total if total is not None else max(len(latest), len(hot))
        self.page_size = page_size
        self.fail_sorts = set(fail_sorts)
        self.anonymous = anonymous
        self.calls = []

    def fetch(self, sort, page):
        self.calls.append((sort, page))
        if sort in self.fail_sorts:
            raise RuntimeError("network down")
        if self.anonymous:
            # 未登录：平台只给 3 条热评
            return CommentPage(replies=self.hot[:ANONYMOUS_CAP], total=self.total)
        source = self.latest if sort == "latest" else self.hot
        start = (page - 1) * self.page_size
        chunk = source[start : start + self.page_size]
        return CommentPage(replies=chunk, total=self.total)


class TestDualSortCollection:
    def test_takes_n_from_each_sort(self):
        latest = [reply(f"L{i}") for i in range(20)]
        hot = [reply(f"H{i}") for i in range(20)]
        platform = FakePlatform(latest, hot, total=100)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert len(result.comments) == 20
        assert result.meta["target_n"] == 10
        assert result.meta["sorts_used"] == ["latest", "hot"]
        assert result.meta["fetched_per_sort"] == {"latest": 10, "hot": 10}

    def test_merges_overlap_and_records_both_sources(self):
        """同一条评论既新又热时只保留一条，但 sort_source 记两个来源。"""
        shared = reply("SAME")
        latest = [shared, reply("L1"), reply("L2")]
        hot = [shared, reply("H1"), reply("H2")]
        platform = FakePlatform(latest, hot, total=4)
        result = collect_comments_dual_sort(platform.fetch, target_n=3, sleep_seconds=0)
        ids = [c["comment_id"] for c in result.comments]
        assert ids.count("SAME") == 1
        same = next(c for c in result.comments if c["comment_id"] == "SAME")
        assert same["sort_source"] == ["latest", "hot"]

    def test_all_when_total_below_target(self):
        """总数不足 N 时取全部，并标记 exhausted。"""
        latest = [reply(f"L{i}") for i in range(4)]
        hot = [reply(f"L{i}") for i in range(4)]
        platform = FakePlatform(latest, hot, total=4)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert len(result.comments) == 4
        assert result.meta["exhausted"] is True
        assert result.meta["total_available"] == 4

    def test_not_exhausted_when_total_larger(self):
        latest = [reply(f"L{i}") for i in range(20)]
        hot = [reply(f"H{i}") for i in range(20)]
        platform = FakePlatform(latest, hot, total=500)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert result.meta["exhausted"] is False
        assert result.meta["total_available"] == 500

    def test_paginates_when_page_smaller_than_target(self):
        latest = [reply(f"L{i}") for i in range(30)]
        hot = [reply(f"H{i}") for i in range(30)]
        platform = FakePlatform(latest, hot, total=200, page_size=5)
        result = collect_comments_dual_sort(
            platform.fetch, target_n=10, page_size=5, sleep_seconds=0
        )
        assert len(result.comments) == 20
        # 每个排序需要 2 页
        assert result.meta["requests_made"] == 4

    def test_one_sort_failure_keeps_other(self):
        latest = [reply(f"L{i}") for i in range(20)]
        hot = [reply(f"H{i}") for i in range(20)]
        platform = FakePlatform(latest, hot, total=100, fail_sorts={"hot"})
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert len(result.comments) == 10
        assert result.meta["fetched_per_sort"]["hot"] == 0
        assert "errors" in result.meta
        assert "network down" in result.meta["errors"][0]

    def test_target_zero_collects_nothing(self):
        platform = FakePlatform([reply("L0")], [reply("H0")], total=2)
        result = collect_comments_dual_sort(platform.fetch, target_n=0)
        assert result.comments == []
        assert result.meta["requests_made"] == 0
        assert platform.calls == []


class TestDegradedDetection:
    def test_anonymous_cap_flagged(self):
        """平台报告 500 条但只返回 3 条 → 必须标记降级，不能静默接受。"""
        latest = [reply(f"L{i}") for i in range(20)]
        hot = [reply(f"H{i}") for i in range(20)]
        platform = FakePlatform(latest, hot, total=500, anonymous=True)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert result.meta["degraded"] is True
        assert "未登录" in result.meta["degraded_reason"]
        assert result.meta["exhausted"] is False

    def test_normal_collection_not_degraded(self):
        latest = [reply(f"L{i}") for i in range(20)]
        hot = [reply(f"H{i}") for i in range(20)]
        platform = FakePlatform(latest, hot, total=100)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert result.meta["degraded"] is False
        assert result.meta["degraded_reason"] is None


class TestCookieInjection:
    def test_extract_from_storage_state(self):
        state = {
            "cookies": [
                {"name": "SESSDATA", "value": "abc123"},
                {"name": "buvid3", "value": "xyz"},
            ]
        }
        cookies = session_from_storage_state(state)
        assert cookies == {"SESSDATA": "abc123", "buvid3": "xyz"}

    def test_handles_missing_state(self):
        assert session_from_storage_state(None) == {}
        assert session_from_storage_state({}) == {}

    def test_skips_malformed_entries(self):
        state = {"cookies": [None, {"no_name": 1}, {"name": "SESSDATA", "value": "v"}]}
        assert session_from_storage_state(state) == {"SESSDATA": "v"}

    def test_login_detection(self):
        ok, missing = required_cookies_present({"SESSDATA": "x"})
        assert ok is True and missing == []
        ok, missing = required_cookies_present({})
        assert ok is False and missing == ["SESSDATA"]


class TestNormalization:
    def test_platform_raw_shape(self):
        """兼容平台原始字段名（rpid / content.message / like）。"""
        raw = {
            "rpid": 12345,
            "member": {"mid": "999", "uname": "u"},
            "content": {"message": "  真实评论  "},
            "like": 7,
            "is_pinned": True,
            "ctime": 1700000000,
        }
        platform = FakePlatform([raw], [raw], total=1)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        item = result.comments[0]
        assert item["comment_id"] == "12345"
        assert item["text"] == "真实评论"
        assert item["like_count"] == 7
        assert item["is_pinned"] is True

    def test_skips_reply_without_id(self):
        platform = FakePlatform([{"text": "无 id"}], [], total=2)
        result = collect_comments_dual_sort(platform.fetch, target_n=10, sleep_seconds=0)
        assert result.comments == []

#!/usr/bin/env python3
"""评论区双排序采集：最新与最热各取 N 条，不足则取全部。

解决的问题：原采集用未登录的 requests.Session 调 B站评论接口，平台只返回 3 条热评，
导致全池 74.8% 的帖子恰好 3 条评论，依赖评论区的判定规则几乎无数据支撑。

设计要点：
  - 采集策略（排序、翻页、去重、耗尽判断）与 HTTP 传输解耦，便于离线测试；
  - 每条评论记录 sort_source，标明它来自「最新」「最热」中的哪些排序；
  - 记录 total_available 与 exhausted，区分「平台只有这些」与「我们只取了这些」；
  - 检测降级返回（请求要得多、拿到得少）并显式标记，不静默接受。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

CST = timezone(timedelta(hours=8))

SORT_LATEST = "latest"
SORT_HOT = "hot"

# B站 /x/v2/reply 的 sort 取值
BILI_SORT_VALUE = {SORT_LATEST: 0, SORT_HOT: 1}
# B站 /x/v2/reply/wbi/main 的 mode 取值
BILI_MODE_VALUE = {SORT_LATEST: 2, SORT_HOT: 3}

# 未登录时平台对单个帖子的评论返回上限，用于识别降级
ANONYMOUS_CAP = 3


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


@dataclass
class CommentPage:
    """一次评论分页请求的结果。"""

    replies: List[Dict[str, Any]] = field(default_factory=list)
    total: Optional[int] = None


@dataclass
class CommentCollection:
    comments: List[Dict[str, Any]]
    meta: Dict[str, Any]


def _normalize(reply: Dict[str, Any], sort_source: str) -> Optional[Dict[str, Any]]:
    """把平台原始回复转成 comment_item，并记下来源排序。"""
    if not isinstance(reply, dict):
        return None
    comment_id = str(reply.get("comment_id") or reply.get("rpid") or "").strip()
    if not comment_id:
        return None
    text = reply.get("text")
    if text is None:
        content = reply.get("content")
        if isinstance(content, dict):
            text = content.get("message")
    return {
        "comment_id": comment_id,
        "author_id": str(reply.get("author_id") or reply.get("mid") or ""),
        "text": str(text or "").strip(),
        "like_count": int(reply.get("like_count") or reply.get("like") or 0),
        "is_pinned": bool(reply.get("is_pinned", False)),
        "created_at": reply.get("created_at"),
        "is_deleted": bool(reply.get("is_deleted", False)),
        "sort_source": [sort_source],
    }


def collect_comments_dual_sort(
    fetch_page: Callable[[str, int], CommentPage],
    *,
    target_n: int = 10,
    page_size: int = 20,
    max_pages_per_sort: int = 5,
    sleep_seconds: float = 0.3,
    sleep: Callable[[float], None] = time.sleep,
    collected_at: Optional[str] = None,
) -> CommentCollection:
    """按最新与最热两种排序各取 target_n 条，按 comment_id 去重合并。

    fetch_page(sort, page) 需返回 CommentPage；sort 取 "latest" / "hot"，page 从 1 开始。
    任何一次请求抛异常都视为该排序中止，已取得的评论仍保留。
    """
    if target_n < 0:
        raise ValueError("target_n 不能为负")

    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    total: Optional[int] = None
    requests_made = 0
    errors: List[str] = []
    sorts_used: List[str] = []
    fetched_counts: Dict[str, int] = {}

    if target_n == 0:
        return CommentCollection(
            comments=[],
            meta=_build_meta(
                target_n=0,
                sorts_used=[],
                total=None,
                returned=0,
                requests_made=0,
                degraded=False,
                degraded_reason="target_n=0，未采集评论",
                collected_at=collected_at,
                errors=errors,
                fetched_counts={},
            ),
        )

    for sort in (SORT_LATEST, SORT_HOT):
        got_this_sort = 0
        page = 1
        sorts_used.append(sort)
        while got_this_sort < target_n and page <= max_pages_per_sort:
            try:
                result = fetch_page(sort, page)
                requests_made += 1
            except Exception as exc:  # 单个排序失败不放弃另一个排序
                errors.append(f"{sort} p{page}: {type(exc).__name__}: {exc}")
                break

            if total is None and result.total is not None:
                total = result.total

            replies = result.replies or []
            if not replies:
                break

            for raw in replies:
                if got_this_sort >= target_n:
                    break
                item = _normalize(raw, sort)
                if item is None:
                    continue
                got_this_sort += 1
                cid = item["comment_id"]
                if cid in merged:
                    if sort not in merged[cid]["sort_source"]:
                        merged[cid]["sort_source"].append(sort)
                    continue
                merged[cid] = item
                order.append(cid)

            # 平台已给全，无需再翻页
            if total is not None and len(merged) >= total:
                break
            if len(replies) < page_size:
                break
            page += 1
            if sleep_seconds:
                sleep(sleep_seconds)

        fetched_counts[sort] = got_this_sort

    comments = [merged[cid] for cid in order]

    degraded = False
    degraded_reason = None
    if total is not None and total > ANONYMOUS_CAP and len(comments) == ANONYMOUS_CAP:
        degraded = True
        degraded_reason = (
            f"平台报告 {total} 条评论但仅返回 {ANONYMOUS_CAP} 条，"
            "疑似未登录降级返回；需注入登录态 Cookie 后重采"
        )
    elif total is not None and total > len(comments) and sorted(fetched_counts.values()) == [0, 0]:
        degraded = True
        degraded_reason = f"平台报告 {total} 条评论但两次排序均未取到"

    return CommentCollection(
        comments=comments,
        meta=_build_meta(
            target_n=target_n,
            sorts_used=sorts_used,
            total=total,
            returned=len(comments),
            requests_made=requests_made,
            degraded=degraded,
            degraded_reason=degraded_reason,
            collected_at=collected_at,
            errors=errors,
            fetched_counts=fetched_counts,
        ),
    )


def _build_meta(
    *,
    target_n: int,
    sorts_used: Sequence[str],
    total: Optional[int],
    returned: int,
    requests_made: int,
    degraded: bool,
    degraded_reason: Optional[str],
    collected_at: Optional[str],
    errors: Sequence[str],
    fetched_counts: Dict[str, int],
) -> Dict[str, Any]:
    exhausted = total is not None and returned >= total
    meta: Dict[str, Any] = {
        "target_n": target_n,
        "sorts_used": list(sorts_used),
        "total_available": total,
        "exhausted": exhausted,
        "returned": returned,
        "requests_made": requests_made,
        "degraded": degraded,
        "degraded_reason": degraded_reason,
        "collected_at": collected_at or now_iso(),
        "fetched_per_sort": dict(fetched_counts),
    }
    if errors:
        meta["errors"] = list(errors)
    return meta


def session_from_storage_state(state: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """把 Playwright storage_state 里的 cookies 抽成 {name: value}。

    原采集的缺陷：Playwright 的登录态只用于抓 HTML，从未注入 requests.Session，
    因此评论接口始终以匿名身份调用，被平台限制为 3 条。
    """
    cookies: Dict[str, str] = {}
    if not isinstance(state, dict):
        return cookies
    for cookie in state.get("cookies") or []:
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = cookie.get("value")
        if name and value is not None:
            cookies[name] = str(value)
    return cookies


def required_cookies_present(cookies: Dict[str, str]) -> Tuple[bool, List[str]]:
    """B站评论接口在登录态下才返回完整列表，SESSDATA 缺失即为匿名。"""
    missing = [name for name in ("SESSDATA",) if not cookies.get(name)]
    return (not missing, missing)

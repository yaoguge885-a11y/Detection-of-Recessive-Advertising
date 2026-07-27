#!/usr/bin/env python3
"""
小红书 HTML 结构提取器 —— 从 SSR 渲染的小红书笔记页面提取纯净正文 + <图片N> 标记。

核心策略：解析 HTML 中嵌入的 window.__INITIAL_STATE__ JSON，
从中提取标题、正文、图片列表、视频信息、评论数据。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════════════
# JSON 提取
# ═══════════════════════════════════════════════════════════════

def _extract_initial_state(html: str) -> Optional[Dict]:
    """从 HTML 中提取 window.__INITIAL_STATE__ JSON。"""
    # 方法 1: 直接匹配 'window.__INITIAL_STATE__ = {...}'
    m = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*\n",
        html, re.DOTALL
    )
    if not m:
        m = re.search(
            r"window\.__INITIAL_STATE__\s*=\s*(.+?);\s*\n",
            html, re.DOTALL
        )
    if not m:
        # 替换换行符可能干扰 JSON 解析
        m = re.search(
            r'window\.__INITIAL_STATE__\s*=\s*(\{.*?})\s*</script>',
            html, re.DOTALL
        )

    if not m:
        return None

    json_str = m.group(1)
    # 修复常见 JSON 问题
    json_str = json_str.replace("undefined", "null")

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试用更宽松的匹配
        try:
            # 找到第一个 { 到匹配的 }
            start = html.index("window.__INITIAL_STATE__")
            brace_start = html.index("{", start)
            depth = 0
            end = brace_start
            for i, ch in enumerate(html[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            json_str = html[brace_start:end].replace("undefined", "null")
            return json.loads(json_str)
        except Exception:
            return None


def _append_response_comments(result: Dict, html: str) -> None:
    """Normalize comment API payloads appended by the browser collector."""
    for raw in re.findall(r"<!--XHS_COMMENTS:(.*?)-->", html, re.DOTALL):
        try:
            payloads = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for payload in payloads if isinstance(payloads, list) else [payloads]:
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            candidates = data.get("comments") or data.get("commentList") or data.get("list") or []
            for item in candidates:
                user = item.get("user") or {}
                result["comments_raw"].append({
                    "comment_id": str(item.get("id") or item.get("commentId") or ""),
                    "author_id": str(user.get("userId") or user.get("id") or ""),
                    "text": item.get("content") or item.get("text") or "",
                    "picture_urls": [],
                    "like_count": int(item.get("likeCount") or item.get("like_count") or 0),
                    "is_pinned": bool(item.get("pinned") or item.get("isPinned")),
                })


# ═══════════════════════════════════════════════════════════════
# 主提取函数
# ═══════════════════════════════════════════════════════════════

def extract_xhs_note(html: str) -> Dict:
    """从小红书笔记页面 HTML 中提取结构化内容。

    Returns:
        {
            "title": str,
            "clean_text": str,           # 带 <图片N> 标记的正文
            "image_urls": List[str],     # 原始图片 URL
            "media_enrichments": [...],
            "note_type": "normal"|"video",
            "published_at": str,
            "author_name": str,
            "author_id": str,
            "note_id": str,
            "like_count": int,
            "collect_count": int,
            "comment_count": int,
            "comments_raw": List[dict],
        }
    """
    result = {
        "title": None,
        "clean_text": "",
        "image_urls": [],
        "media_enrichments": [],
        "note_type": "normal",
        "published_at": None,
        "author_name": None,
        "author_id": None,
        "note_id": None,
        "like_count": 0,
        "collect_count": 0,
        "comment_count": 0,
        "comments_raw": [],
    }

    init_state = _extract_initial_state(html)
    if not init_state:
        _append_response_comments(result, html)
        return result

    try:
        # 路径: note.noteDetailMap[noteId].note
        note_detail_map = init_state.get("note", {}).get("noteDetailMap", {})
        if not note_detail_map:
            # 另一可能路径
            note_detail_map = init_state.get("noteDetailMap", {})

        # 获取第一个 note
        note_data = None
        note_id = None
        for nid, ndata in note_detail_map.items():
            note = ndata.get("note", ndata)
            if note:
                note_data = note
                note_id = nid
                break

        if not note_data:
            # 尝试直接路径
            note_data = init_state.get("note")
            note_id = note_data.get("noteId") if note_data else None

        if not note_data:
            return result

        # ── 基本字段 ──
        result["note_id"] = note_id or note_data.get("noteId") or note_data.get("id")
        result["title"] = note_data.get("title") or note_data.get("displayTitle") or ""
        result["note_type"] = note_data.get("type") or "normal"

        # ── 正文 ──
        desc = note_data.get("desc") or ""
        result["clean_text"] = desc.strip()

        # ── 图片列表 → <图片N> 标记 ──
        image_list = note_data.get("imageList") or note_data.get("image_list") or []
        img_urls = []
        for i, img in enumerate(image_list):
            img_url = ""
            if isinstance(img, dict):
                # 优先使用原始 URL
                img_url = (
                    img.get("urlDefault") or
                    img.get("url") or
                    img.get("original") or
                    img.get("traceId", "")
                )
                # 小红书的 URL 可能有多个尺寸版本
                info_list = img.get("infoList") or []
                if info_list and isinstance(info_list, list):
                    # 取最后一项（通常最大尺寸）
                    last_info = info_list[-1] if info_list else {}
                    img_url = last_info.get("url") or img_url

            if img_url and img_url.startswith("http"):
                if img_url not in img_urls:
                    img_urls.append(img_url)

        result["image_urls"] = img_urls

        # 在正文中插入 <图片N> 标记
        if img_urls:
            markers = "".join(f"<图片{i+1}>" for i in range(len(img_urls)))
            if desc.strip():
                result["clean_text"] = desc.strip() + "\n" + markers
            else:
                result["clean_text"] = markers

        # ── 媒体增强信息 ──
        for i in range(len(img_urls)):
            result["media_enrichments"].append({
                "index": i,
                "is_content": True,
                "caption": None,
            })

        # ── 作者 ──
        user = note_data.get("user") or note_data.get("author") or {}
        result["author_name"] = user.get("nickname") or user.get("name")
        result["author_id"] = user.get("userId") or user.get("id") or user.get("redId")

        # ── 互动数据 ──
        interact = note_data.get("interactInfo") or note_data.get("interact_info") or {}
        result["like_count"] = int(interact.get("likedCount") or interact.get("liked_count") or 0)
        result["collect_count"] = int(interact.get("collectedCount") or interact.get("collected_count") or 0)
        result["comment_count"] = int(interact.get("commentCount") or interact.get("comment_count") or 0)

        # ── 发布时间 ──
        pub_time = note_data.get("time") or note_data.get("createTime") or note_data.get("create_time")
        if pub_time:
            try:
                from datetime import datetime, timezone, timedelta
                CST = timezone(timedelta(hours=8))
                if isinstance(pub_time, (int, float)) and pub_time > 1000000000:
                    dt = datetime.fromtimestamp(pub_time / 1000 if pub_time > 1e12 else pub_time, tz=CST)
                else:
                    dt = datetime.fromtimestamp(int(pub_time), tz=CST)
                result["published_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            except Exception:
                result["published_at"] = str(pub_time)

        # ── 评论（可能有初始的）──
        comments_list = note_data.get("comments") or note_data.get("commentList") or []
        for c in comments_list[:50]:  # 最多取 50 条初始评论
            comment = {
                "comment_id": str(c.get("id") or c.get("commentId") or ""),
                "author_name": c.get("user", {}).get("nickname") or c.get("nickname") or "",
                "author_id": str(c.get("user", {}).get("userId") or c.get("user", {}).get("id") or ""),
                "text": c.get("content") or c.get("text") or "",
                "picture_urls": [],
                "like_count": int(c.get("likeCount") or c.get("like_count") or 0),
                "is_pinned": bool(c.get("pinned") or c.get("isPinned") or False),
                "created_at": str(c.get("createTime") or c.get("create_time") or ""),
            }
            # 评论中的图片
            pics = c.get("pictures") or c.get("images") or []
            for pic in pics:
                pic_url = pic.get("url") or pic.get("fileUrl") or ""
                if pic_url and pic_url.startswith("http"):
                    comment["picture_urls"].append(pic_url)
            result["comments_raw"].append(comment)

    except Exception:
        pass

    _append_response_comments(result, html)
    return result

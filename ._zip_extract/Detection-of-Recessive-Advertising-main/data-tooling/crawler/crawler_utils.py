#!/usr/bin/env python3
"""爬虫共享工具模块。

从 crawl_public_posts.py 提取的通用函数，供所有平台爬虫（微信/B站/小红书）共用。
包括：哈希脱敏、图片下载、标准化 post 记录构建、平台识别、时间解析等。

所有函数保持与原 crawl_public_posts.py 相同的签名和行为。
"""
from __future__ import annotations

import collections
import hashlib
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CST = timezone(timedelta(hours=8))
DEFAULT_OUTPUT_ROOT = "data/run_outputs"

HEADERS = {"User-Agent": USER_AGENT}

# ═══════════════════════════════════════════════════════════════
# 脱敏与哈希
# ═══════════════════════════════════════════════════════════════

def get_salt() -> str:
    salt = os.getenv("ANONYMIZATION_SALT")
    if not salt:
        raise RuntimeError(
            "ANONYMIZATION_SALT is required. Set it in your environment or .env file."
        )
    return salt


def stable_hash(value: str, salt: str, length: int = 16) -> str:
    digest = hashlib.sha256((salt + value).encode("utf-8")).hexdigest()
    return digest[:length]


def fuzzy_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    if len(name) <= 2:
        return name[0] + "*" * (len(name) - 1)
    return name[0] + "*" * (len(name) - 2) + name[-1]


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ═══════════════════════════════════════════════════════════════
# 时间解析
# ═══════════════════════════════════════════════════════════════

def parse_iso_datetime(raw: str) -> Optional[str]:
    """将各种格式的时间字符串归一化为 ISO 8601 +08:00。"""
    raw = raw.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=CST)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except ValueError:
            continue
    return None


def unix_to_iso(ts: int) -> str:
    """Unix 时间戳 → ISO 8601 +08:00。"""
    dt = datetime.fromtimestamp(ts, tz=CST)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")


# ═══════════════════════════════════════════════════════════════
# 平台识别（扩展支持 B站/小红书）
# ═══════════════════════════════════════════════════════════════

def platform_from_url(url: str) -> str:
    """根据 URL 域名识别内容来源平台。"""
    if not url:
        return "other"
    url_lower = url.lower()
    if "mp.weixin.qq.com" in url_lower or "weixin.qq.com" in url_lower:
        return "wechat_official_account"
    if "bilibili.com" in url_lower:
        return "bilibili"
    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xiaohongshu"
    if "weibo.com" in url_lower or "m.weibo.cn" in url_lower:
        return "weibo_public_account"
    return "web_public"


# ═══════════════════════════════════════════════════════════════
# 图片下载
# ═══════════════════════════════════════════════════════════════

def download_images(
    image_urls: List[str],
    post_id: str,
    media_base_dir: Path,
    session: Optional[requests.Session] = None,
    referer: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict]:
    """下载图片到 media/{post_id}/ 目录，返回 media 字段数组。

    Args:
        image_urls: 图片 URL 列表
        post_id: 帖子/笔记 ID（用作子目录名）
        media_base_dir: 媒体根目录
        session: 可复用的 requests.Session（可选）
        referer: Referer 请求头（平台特定，如图片防盗链需要）
        timeout: 下载超时秒数
    """
    if session is None:
        session = requests.Session()

    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer

    media_records: List[Dict] = []
    post_media_dir = media_base_dir / f"post_{post_id[:16]}"
    post_media_dir.mkdir(parents=True, exist_ok=True)

    valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    for idx, img_url in enumerate(image_urls):
        try:
            parsed = urlparse(img_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if not ext or ext not in valid_exts:
                ext = ".jpg"

            filename = f"{idx:02d}{ext}"
            filepath = post_media_dir / filename

            resp = session.get(img_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)

            media_records.append({
                "ref": str(filepath.relative_to(media_base_dir.parent)).replace("\\", "/"),
                "source_url": img_url,
            })
        except Exception as exc:
            print(f"  [img-err] {img_url[:80]}... → {exc}", file=sys.stderr)
            media_records.append({
                "ref": None,
                "source_url": img_url,
            })

    return media_records


def download_comment_images(
    image_urls: List[str],
    comment_id: str,
    media_base_dir: Path,
    session: Optional[requests.Session] = None,
    referer: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict]:
    """下载评论中的图片到 media/comment_{comment_id}/ 目录。"""
    if session is None:
        session = requests.Session()

    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer

    media_records: List[Dict] = []
    comment_media_dir = media_base_dir / f"comment_{comment_id[:16]}"
    comment_media_dir.mkdir(parents=True, exist_ok=True)

    valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    for idx, img_url in enumerate(image_urls):
        try:
            parsed = urlparse(img_url)
            ext = os.path.splitext(parsed.path)[1].lower()
            if not ext or ext not in valid_exts:
                ext = ".jpg"

            filename = f"{idx:02d}{ext}"
            filepath = comment_media_dir / filename

            resp = session.get(img_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)

            media_records.append({
                "ref": str(filepath.relative_to(media_base_dir.parent)).replace("\\", "/"),
                "source_url": img_url,
            })
        except Exception as exc:
            print(f"  [comment-img-err] {img_url[:80]}... → {exc}", file=sys.stderr)
            media_records.append({
                "ref": None,
                "source_url": img_url,
            })

    return media_records


# ═══════════════════════════════════════════════════════════════
# 标准化记录构建
# ═══════════════════════════════════════════════════════════════

def build_post_record(
    url: str,
    publisher_name: str,
    publisher_id: str,
    title: str,
    body_text: str,
    media_records: List[Dict],
    published_at: Optional[str],
    history_post_ids: Optional[List[str]],
    salt: str,
    collector: str,
    terms_checked_at: Optional[str],
    llm_meta: Optional[Dict] = None,
    comments: Optional[List[Dict]] = None,
    source_type: str = "manual_public_collection",
    content_group_id: Optional[str] = None,
) -> Dict:
    """构建一条 v1.1 Schema 规范的帖子记录。

    严格遵循 data-tooling/schema/data_schema_v1_1.json 的 content_record 定义。

    Returns:
        OrderedDict 格式的 v1.1 帖子记录
    """
    source_ref_hash = stable_hash(url, salt, length=32)
    blogger_id = "blogger_" + stable_hash(publisher_id or publisher_name or url, salt, length=24)
    post_id = "post_" + stable_hash(url, salt, length=32)

    if not published_at:
        published_at = None

    # ── 规范化 media 数组为 v1.1 格式 ──
    media_v1 = []
    for i, m in enumerate(media_records or []):
        media_item = collections.OrderedDict()
        media_item["media_id"] = f"media_{post_id}_{i:03d}"
        # 视频类型
        if m.get("_media_type") == "video":
            media_item["type"] = "video"
        elif m.get("ref") and any(m.get("ref", "").lower().endswith(ext)
                                   for ext in (".mp4", ".mov", ".avi", ".webm")):
            media_item["type"] = "video"
        else:
            media_item["type"] = "image"
        media_item["ref"] = m.get("ref")
        media_item["sha256"] = m.get("sha256")
        media_item["phash"] = m.get("phash")
        media_item["ocr_text"] = m.get("ocr_text")
        # 保留扩展字段（source_url, caption 等）
        if m.get("source_url"):
            media_item["source_url"] = m["source_url"]
        if m.get("caption"):
            media_item["caption"] = m["caption"]
        if m.get("is_content") is not None:
            media_item["is_content"] = m["is_content"]
        media_v1.append(media_item)

    # ── 规范化 comments 为 v1.1 格式 ──
    comments_v1 = []
    for i, c in enumerate(comments or []):
        comment_item = collections.OrderedDict()
        comment_item["comment_id"] = c.get("comment_id", f"comment_{post_id}_{i:03d}")
        comment_item["author_id"] = c.get("author_id", "")
        comment_item["text"] = c.get("text", "")
        comment_item["like_count"] = int(c.get("like_count", 0))
        comment_item["is_pinned"] = bool(c.get("is_pinned", False))
        comments_v1.append(comment_item)

    # ── provenance ──
    provenance = collections.OrderedDict()
    provenance["source_ref_hash"] = source_ref_hash
    provenance["collected_at"] = datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    provenance["collector"] = collector
    provenance["terms_checked_at"] = terms_checked_at
    # 保留 LLM 元数据
    if llm_meta:
        provenance["llm_mode"] = "html_direct"
        provenance["llm_needs_review"] = llm_meta.get("needs_review", True)
        provenance["llm_confidence"] = llm_meta.get("confidence", 0)
        if llm_meta.get("notes"):
            provenance["llm_notes"] = llm_meta["notes"][:2000]

    # ── privacy ──
    privacy = collections.OrderedDict()
    privacy["anonymized"] = True
    privacy["contains_sensitive_data"] = False

    # ── 组装主记录 ──
    record = collections.OrderedDict()
    record["schema_version"] = "1.2"
    record["post_id"] = post_id
    record["platform"] = platform_from_url(url)
    record["source_type"] = source_type
    record["blogger_id"] = blogger_id
    record["published_at"] = published_at
    record["title"] = title if title else None
    record["content_group_id"] = content_group_id
    record["text"] = body_text
    record["media"] = media_v1
    record["comments"] = comments_v1
    record["blogger_history_refs"] = history_post_ids or []
    record["provenance"] = provenance
    record["privacy"] = privacy

    # 向后兼容：保留旧字段
    record["_collected"] = provenance.copy()
    record["_collected"]["source_url"] = url

    return record


# ═══════════════════════════════════════════════════════════════
# Playwright 通用工具
# ═══════════════════════════════════════════════════════════════

def launch_stealth_context(
    browser,
    referer: Optional[str] = None,
    cookies: Optional[List[Dict]] = None,
):
    """创建带反检测措施的 Playwright browser context。

    Args:
        browser: Playwright browser 实例
        referer: 可选 Referer header
        cookies: 可选 cookies 列表 [{name,value,domain},...]
    """
    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    # 隐藏 webdriver 标记
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
    """)

    if cookies:
        context.add_cookies(cookies)

    page = context.new_page()
    if referer:
        page.set_extra_http_headers({"Referer": referer})

    return context, page


def parse_cookies(cookies_arg: str) -> dict:
    """解析 cookies 字符串或文件路径，返回 {name: value} 字典。"""
    import json as _json

    if not cookies_arg:
        return {}

    if os.path.exists(cookies_arg):
        raw = Path(cookies_arg).read_text(encoding="utf-8").strip()
    else:
        raw = cookies_arg.strip()

    # JSON 格式（EditThisCookie 导出）
    if raw.startswith("[") and raw.endswith("]"):
        try:
            arr = _json.loads(raw)
            return {
                c["name"]: c["value"]
                for c in arr
                if c.get("name") and c.get("value")
            }
        except Exception:
            pass

    # Netscape / key=value 格式
    cookies: dict = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for item in line.split(";"):
            item = item.strip()
            if not item or "=" not in item:
                continue
            k, v = item.split("=", 1)
            k, v = k.strip(), v.strip()
            if v:
                cookies[k] = v
    return cookies

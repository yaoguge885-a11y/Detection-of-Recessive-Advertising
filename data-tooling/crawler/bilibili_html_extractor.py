#!/usr/bin/env python3
"""
B站 HTML 结构提取器 —— 用 BeautifulSoup 从 B站页面提取纯净正文 + <图片N> 标记。

处理三种内容类型：
  - 视频页 (bilibili.com/video/{bvid}): 仅提取简介文字，不下载封面/视频
  - 图文动态 (t.bilibili.com/{id}): 提取正文 + 图片位置
  - 专栏文章 (bilibili.com/read/cv{id}): 提取文章 + 插图位置

所有图片使用 <图片N> 标记（N 从 1 开始），与微信提取器行为一致。
视频类型记录的 media.type="video", ref=null。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ═══════════════════════════════════════════════════════════════
# 图片判定
# ═══════════════════════════════════════════════════════════════

MIN_CONTENT_WIDTH = 200
MIN_CONTENT_HEIGHT = 150
MIN_CONTENT_AREA = 40000

# B站图片 CDN
BILIBILI_IMG_CDNS = {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com", "i3.hdslb.com"}

# 装饰图特征
DECORATION_PATTERNS = [
    r"static\.hdslb\.com",     # B站 UI 图标
    r"emoticon|emoji|face",     # 表情包
    r"avatar",                  # 头像
    r"/50x50|/30x30",          # 极小图
    r"live\.bilibili\.com",     # 直播相关
]


def _is_content_image(img_tag) -> Tuple[bool, str]:
    """判断 <img> 是否内容图片（非装饰）。"""
    src = img_tag.get("data-src") or img_tag.get("src") or ""

    for pattern in DECORATION_PATTERNS:
        if re.search(pattern, src, re.IGNORECASE):
            return False, f"decoration: {pattern}"

    width = _parse_dim(img_tag.get("data-w") or img_tag.get("width") or "0")
    height = _parse_dim(img_tag.get("data-h") or img_tag.get("height") or "0")

    if width and width < MIN_CONTENT_WIDTH:
        return False, f"narrow: {width}px"
    if height and height < MIN_CONTENT_HEIGHT:
        return False, f"short: {height}px"
    if width and height and (width * height) < MIN_CONTENT_AREA:
        return False, f"small: {width}x{height}"

    # B站图床 CDN 的视为内容图
    parsed_domain = _extract_domain(src)
    if parsed_domain in BILIBILI_IMG_CDNS:
        return True, "bilibili_cdn"

    if src.startswith("http"):
        return True, "has_url"

    return False, "no_url"


def _parse_dim(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(re.sub(r"[^\d]", "", str(val)))
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    """从 URL 提取域名。"""
    m = re.search(r"://([^/]+)", url)
    return m.group(1) if m else ""


# ═══════════════════════════════════════════════════════════════
# 辅助: JSON 提取
# ═══════════════════════════════════════════════════════════════

def _extract_json_from_html(html: str, key: str = "__INITIAL_STATE__") -> Optional[Dict]:
    """从 HTML 中提取 window.__INITIAL_STATE__ 或类似 JSON 数据。"""
    pattern = rf"window\.{key}\s*=\s*(.*?);\s*(?:\(function|var\s+\w+|window\.)"
    m = re.search(pattern, html, re.DOTALL)
    if not m:
        # 宽松匹配：找到 = {...}; 后跟函数定义
        m2 = re.search(rf"window\.{key}\s*=\s*(.*?);\s*\n", html, re.DOTALL)
        if not m2:
            return None
        json_str = m2.group(1)
    else:
        json_str = m.group(1)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


# ═══════════════════════════════════════════════════════════════
# 视频页提取
# ═══════════════════════════════════════════════════════════════

def extract_bilibili_video(html: str) -> Dict:
    """从 B站视频页提取信息。

    Returns:
        {title, clean_text, image_urls, aid, bvid, published_at, author_name, author_mid}
    """
    result = {
        "title": None,
        "clean_text": "",
        "image_urls": [],
        "aid": None,
        "bvid": None,
        "published_at": None,
        "author_name": None,
        "author_mid": None,
    }

    soup = BeautifulSoup(html, "html.parser") if HAS_BS4 else None

    # 从 meta 标签提取
    if soup:
        for meta in soup.find_all("meta"):
            prop = meta.get("property") or meta.get("name") or ""
            content = meta.get("content", "")
            if prop == "og:title" or prop == "title":
                result["title"] = content.strip()
            elif prop == "og:description" or prop == "description":
                if content.strip() and len(content.strip()) > len(result["clean_text"]):
                    result["clean_text"] = content.strip()
            elif prop == "og:video:release_date":
                result["published_at"] = content.strip()

    # 从 __INITIAL_STATE__ 提取更多元数据
    init_state = _extract_json_from_html(html)
    if init_state:
        try:
            video_data = init_state.get("videoData", {})
            if video_data:
                if not result["title"]:
                    result["title"] = video_data.get("title")
                if not result["clean_text"]:
                    result["clean_text"] = video_data.get("desc") or ""
                result["aid"] = video_data.get("aid")
                result["bvid"] = video_data.get("bvid")
                result["author_name"] = video_data.get("owner", {}).get("name")
                result["author_mid"] = video_data.get("owner", {}).get("mid")
                if video_data.get("pubdate"):
                    from datetime import datetime, timezone, timedelta
                    CST = timezone(timedelta(hours=8))
                    dt = datetime.fromtimestamp(video_data["pubdate"], tz=CST)
                    result["published_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except Exception:
            pass

    # 清洗正文
    result["clean_text"] = (result["clean_text"] or "").strip()

    return result


# ═══════════════════════════════════════════════════════════════
# 图文动态 (Opus) 提取
# ═══════════════════════════════════════════════════════════════

def extract_bilibili_opus(html: str) -> Dict:
    """从 B站图文动态页面提取文本和图片。

    Returns:
        {title, clean_text (含<图片N>标记), image_urls, dynamic_id, published_at, author_name, author_mid}
    """
    result = {
        "title": None,
        "clean_text": "",
        "image_urls": [],
        "dynamic_id": None,
        "published_at": None,
        "author_name": None,
        "author_mid": None,
    }

    if not HAS_BS4:
        return result

    soup = BeautifulSoup(html, "html.parser")

    # 从 __INITIAL_STATE__ 提取结构化数据
    init_state = _extract_json_from_html(html)
    if init_state:
        try:
            # B站动态详情数据结构路径可能有变化
            detail = None
            for key in ["detail", "card", "opusModule"]:
                detail = init_state.get(key)
                if detail:
                    break
            if not detail:
                # 尝试嵌套路径
                detail = init_state.get("data", {}).get("card")

            if detail:
                result["title"] = detail.get("title") or ""
                result["author_name"] = detail.get("user", {}).get("name") or detail.get("author", {}).get("name")
                result["author_mid"] = detail.get("user", {}).get("mid") or detail.get("author", {}).get("mid")
                result["dynamic_id"] = detail.get("id_str") or detail.get("dynamic_id_str")

                # 提取文本和图片
                card_content = detail.get("card") or ""
                item = detail.get("item") or {}
                description = item.get("description") or detail.get("desc") or ""

                # 图片 URL 从 item.pictures[] 提取
                pictures = item.get("pictures") or detail.get("pictures") or []
                for pic in pictures:
                    img_url = pic.get("img_src") or pic.get("img_url") or ""
                    if img_url and img_url.startswith("http"):
                        result["image_urls"].append(img_url)

                # 组合文本
                text_parts = []
                if card_content and isinstance(card_content, str):
                    text_parts.append(card_content)
                if description and isinstance(description, str):
                    text_parts.append(description)
                result["clean_text"] = "\n".join(text_parts).strip()

                # 时间
                if detail.get("pubdate"):
                    from datetime import datetime, timezone, timedelta
                    CST = timezone(timedelta(hours=8))
                    dt = datetime.fromtimestamp(detail["pubdate"], tz=CST)
                    result["published_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                elif detail.get("timestamp"):
                    from datetime import datetime, timezone, timedelta
                    CST = timezone(timedelta(hours=8))
                    dt = datetime.fromtimestamp(detail["timestamp"], tz=CST)
                    result["published_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
                return result
        except Exception:
            pass

    # 回退：从 HTML DOM 提取
    content_div = soup.find("div", class_=lambda c: c and "opus" in c.lower() if c else False)
    if not content_div:
        content_div = soup.find("div", class_=lambda c: c and "dyn" in c.lower() if c else False)
    if not content_div:
        content_div = soup.find("body")

    if content_div:
        paragraphs = []
        img_counter = 0

        for child in content_div.descendants:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text and len(text) > 2:
                    paragraphs.append(text)
            elif isinstance(child, Tag) and child.name == "img":
                is_content, _ = _is_content_image(child)
                if is_content:
                    img_counter += 1
                    paragraphs.append(f"<图片{img_counter}>")
                    src = child.get("data-src") or child.get("src") or ""
                    if src.startswith("http") and src not in result["image_urls"]:
                        result["image_urls"].append(src)

        result["clean_text"] = "\n".join(paragraphs)

    return result


# ═══════════════════════════════════════════════════════════════
# 专栏文章提取
# ═══════════════════════════════════════════════════════════════

def extract_bilibili_article(html: str) -> Dict:
    """从 B站专栏文章页提取正文和插图。

    Returns:
        {title, clean_text (含<图片N>标记), image_urls, cv_id, published_at, author_name, author_mid}
    """
    result = {
        "title": None,
        "clean_text": "",
        "image_urls": [],
        "cv_id": None,
        "published_at": None,
        "author_name": None,
        "author_mid": None,
    }

    if not HAS_BS4:
        return result

    soup = BeautifulSoup(html, "html.parser")

    # 标题
    title_tag = soup.find("title")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        result["title"] = re.sub(r"[_\-—|]\s*\S{2,30}$", "", raw_title).strip()

    h1_tag = soup.find("h1")
    if h1_tag and not result["title"]:
        result["title"] = h1_tag.get_text(strip=True)

    # 从 __INITIAL_STATE__ 提取元数据
    init_state = _extract_json_from_html(html)
    if init_state:
        try:
            read_info = init_state.get("readInfo") or init_state
            if read_info:
                result["author_name"] = read_info.get("author", {}).get("name") or read_info.get("authorName")
                result["author_mid"] = read_info.get("author", {}).get("mid") or read_info.get("authorMid")
                result["cv_id"] = read_info.get("id") or read_info.get("cv")
                if read_info.get("publish_time"):
                    from datetime import datetime, timezone, timedelta
                    CST = timezone(timedelta(hours=8))
                    dt = datetime.fromtimestamp(read_info["publish_time"], tz=CST)
                    result["published_at"] = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        except Exception:
            pass

    # 文章正文容器
    article_body = (
        soup.find("div", class_="article-content") or
        soup.find("div", id="read-article-holder") or
        soup.find("article") or
        soup.find("div", class_="read-content")
    )
    if not article_body:
        article_body = soup.find("body")

    # DOM 遍历提取文本和图片
    paragraphs = []
    img_counter = 0
    skip_classes = {"article-cover", "article-banner", "cover-container"}

    if article_body:
        def _walk(node, current_texts):
            nonlocal img_counter
            if isinstance(node, NavigableString):
                t = str(node).strip()
                if t:
                    current_texts.append(t)
                return
            if not isinstance(node, Tag):
                return
            if node.name in ("script", "style", "noscript", "svg"):
                return
            # 跳过封面
            cls = " ".join(node.get("class", []))
            if any(sc in cls.lower() for sc in skip_classes):
                return
            if node.name == "img":
                is_content, _ = _is_content_image(node)
                if is_content:
                    if current_texts:
                        paragraphs.append(" ".join(current_texts))
                        current_texts.clear()
                    img_counter += 1
                    paragraphs.append(f"<图片{img_counter}>")
                    src = node.get("data-src") or node.get("src") or ""
                    if src.startswith("http") and src not in result["image_urls"]:
                        result["image_urls"].append(src)
                return
            if node.name in ("p", "div", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "br"):
                if current_texts:
                    paragraphs.append(" ".join(current_texts))
                    current_texts.clear()
            for child in node.children:
                _walk(child, current_texts)
            if node.name in ("p", "div", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"):
                if current_texts:
                    paragraphs.append(" ".join(current_texts))
                    current_texts.clear()

        cur = []
        for child in article_body.children:
            _walk(child, cur)
        if cur:
            paragraphs.append(" ".join(cur))

    result["clean_text"] = "\n".join(p for p in paragraphs if p.strip())

    return result


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════

def extract_from_bilibili_html(html: str, content_type: str = "auto") -> Dict:
    """B站 HTML 提取统一入口。

    Args:
        html: 页面 HTML
        content_type: "video" | "opus" | "article" | "auto"

    Returns:
        {title, clean_text, image_urls, media_enrichments, content_type, metadata...}
    """
    if content_type == "auto":
        # 自动检测
        soup = BeautifulSoup(html, "html.parser") if HAS_BS4 else None
        if soup:
            og_type = soup.find("meta", property="og:type")
            if og_type and og_type.get("content", "") == "video":
                content_type = "video"
            elif "bilibili.com/video/" in html[:500]:
                content_type = "video"
            elif "bilibili.com/read/cv" in html[:500]:
                content_type = "article"
            elif "t.bilibili.com/" in html[:500]:
                content_type = "opus"
            else:
                content_type = "video"

    if content_type == "video":
        data = extract_bilibili_video(html)
    elif content_type == "opus":
        data = extract_bilibili_opus(html)
    elif content_type == "article":
        data = extract_bilibili_article(html)
    else:
        data = {"title": None, "clean_text": "", "image_urls": [], "published_at": None}

    # 构建 media_enrichments
    media_enrichments = []
    for i, _img_url in enumerate(data.get("image_urls", [])):
        media_enrichments.append({
            "index": i,
            "is_content": True,
            "caption": None,
        })

    return {
        "title": data.get("title"),
        "clean_text": data.get("clean_text", ""),
        "image_urls": data.get("image_urls", []),
        "media_enrichments": media_enrichments,
        "content_type": content_type,
        "published_at": data.get("published_at"),
        "author_name": data.get("author_name"),
        "author_mid": data.get("author_mid"),
        "aid": data.get("aid"),
        "bvid": data.get("bvid"),
        "dynamic_id": data.get("dynamic_id"),
        "cv_id": data.get("cv_id"),
        "confidence": 0.85,
        "needs_review": False,
        "notes": f"BS4: {content_type}",
        "_method": "bs4_bilibili",
    }

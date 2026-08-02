#!/usr/bin/env python3
"""
增强 HTML 结构提取器 —— 用 BeautifulSoup 替代 LLM 完成图片定位。

解决的问题（LLM 之前在做的事）：
  1. 从微信 HTML 中提取纯净正文段落
  2. 在正文中插入 <图片N> 标记（图片原始出现位置）
  3. 区分内容图片 vs 平台装饰图（二维码、头像、SVG图标等）
  4. 提取图片标注文字（图片前后的说明文本）

用法：
  # 在 crawl_public_posts.py 中替代 llm_extract_from_html
  from scripts.data.crawler.html_structure_extractor import extract_from_html

  # 独立测试
  python scripts/data/crawler/html_structure_extractor.py --html-file test.html

依赖：pip install beautifulsoup4 lxml
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# ═══════════════════════════════════════════════════════════════
# 装饰图判定规则（基于 URL 模式 + 尺寸 + 位置）
# ═══════════════════════════════════════════════════════════════

# 微信装饰图 URL 特征
DECORATION_URL_PATTERNS = [
    r"wx_fmt=svg",           # SVG 图标（公众号头像、菜单图标）
    r"/300\b",               # 300px 宽的头像尺寸（公众号头像约 300x300）
    r"wxfrom=5",             # 特定来源的装饰图
    r"tp=webp",              # WebP 格式的图标
    r"mmbiz_qrcode",         # 二维码图片
    r"qr_code",              # 二维码
    r"icon",                 # 图标
    r"avatar",               # 头像
    r"emoji",                # 表情
    r"cover",                # 封面图
]

# 内容图 URL 特征（微信图床 + 大图）
CONTENT_URL_PATTERNS = [
    r"mmbiz_qpic\.cn.*wx_fmt=(jpeg|png|jpg)",
    r"mmbiz_qpic\.cn.*/640\b",    # 640px 宽是微信文章常见图宽度
    r"mmbiz_qpic\.cn.*/1080\b",   # 高清图
]

# 图片最小尺寸阈值（像素），小于此值的视为装饰图
MIN_CONTENT_WIDTH = 200
MIN_CONTENT_HEIGHT = 150
MIN_CONTENT_AREA = 40000  # 200*200


def _is_likely_content_image(img_tag: Tag) -> Tuple[bool, str]:
    """判断 <img> 是否可能是内容图片（而非装饰图）。

    Returns:
        (is_content: bool, reason: str)
    """
    src = img_tag.get("data-src") or img_tag.get("src") or ""

    # 1. URL 模式匹配
    for pattern in DECORATION_URL_PATTERNS:
        if re.search(pattern, src, re.IGNORECASE):
            return False, f"decoration_url: {pattern}"

    # 2. 尺寸判定
    width = _parse_dimension(img_tag.get("data-w") or img_tag.get("width") or "0")
    height = _parse_dimension(img_tag.get("data-h") or img_tag.get("height") or "0")
    style = img_tag.get("style", "")
    if not width:
        m = re.search(r"width\s*:\s*(\d+)px", style)
        if m:
            width = int(m.group(1))
    if not height:
        m = re.search(r"height\s*:\s*(\d+)px", style)
        if m:
            height = int(m.group(1))

    if width and width < MIN_CONTENT_WIDTH:
        return False, f"too_narrow: {width}px < {MIN_CONTENT_WIDTH}px"
    if height and height < MIN_CONTENT_HEIGHT:
        return False, f"too_short: {height}px < {MIN_CONTENT_HEIGHT}px"
    if width and height and (width * height) < MIN_CONTENT_AREA:
        return False, f"too_small: {width}x{height} = {width*height}px2"

    # 3. 默认：URL 来自微信图床的视为内容图
    for pattern in CONTENT_URL_PATTERNS:
        if re.search(pattern, src, re.IGNORECASE):
            return True, f"content_url: {pattern}"

    # 4. 兜底：有 HTTP URL 的视为内容图
    if src.startswith("http"):
        return True, "default: has_url"

    return False, "default: no_url"


def _parse_dimension(val: str) -> Optional[int]:
    """解析图片尺寸值（可能是 "640" 或 "640px"）。"""
    if not val:
        return None
    try:
        return int(re.sub(r"[^\d]", "", str(val)))
    except ValueError:
        return None


def _extract_image_caption(img_tag: Tag) -> Optional[str]:
    """从图片后面的 DOM 节点提取标注文字。

    微信文章中，图片标注通常是图片后面紧跟的 <span> 或文本节点，
    常见格式："新华社记者 XXX 摄"、"2021年8月4日，中国组合..."
    """
    # 查找图片标签后面的兄弟节点
    sibling = img_tag.next_sibling
    caption_texts = []

    # 最多往后查找 3 个兄弟节点
    for _ in range(3):
        if sibling is None:
            break
        if isinstance(sibling, NavigableString):
            text = sibling.strip()
            if text:
                caption_texts.append(text)
        elif isinstance(sibling, Tag):
            # 只在 span/em/small 等小标签中查找
            if sibling.name in ("span", "em", "small", "p", "figcaption"):
                text = sibling.get_text(strip=True)
                if text and len(text) < 200:
                    # 排除明显不是标注的文字（太长或太短）
                    if 5 < len(text) < 200 and not text.startswith("微信"):
                        caption_texts.append(text)
        sibling = sibling.next_sibling

    caption = " ".join(caption_texts).strip()
    return caption if caption else None


def _get_text_without_nested_tags(element: Tag, exclude_tags: set) -> str:
    """获取元素内文本，排除指定标签内的文字。"""
    texts = []
    for child in element.descendants:
        if isinstance(child, NavigableString):
            texts.append(str(child))
        elif isinstance(child, Tag) and child.name in exclude_tags:
            continue
    return " ".join(texts)


# ═══════════════════════════════════════════════════════════════
# 核心：DOM 遍历提取
# ═══════════════════════════════════════════════════════════════

def extract_from_html(html: str) -> Dict:
    """从微信文章 HTML 中提取纯净正文 + 图片位置 + 图片标注。

    不依赖 LLM，纯 DOM 解析 + 规则判定。

    Returns:
        {
            "title": str|None,       # 纯净标题
            "clean_text": str,        # 带 <图片N> 标记的正文
            "media_enrichments": [    # 图片补充信息
                {"index": 0, "is_content": bool, "caption": str|None}
            ],
            "confidence": float,      # 固定的规则置信度
            "needs_review": bool,     # 是否建议人工复核
            "notes": str,             # 处理说明
        }
    """
    if not HAS_BS4:
        return {
            "title": None, "clean_text": "", "media_enrichments": [],
            "confidence": 0.0, "needs_review": True,
            "notes": "BeautifulSoup 未安装 (pip install beautifulsoup4 lxml)"
        }

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # ── 1. 提取标题 ──
    title = None
    title_tag = soup.find("title")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        # 去除公众号名称后缀（常见格式："文章标题_公众号名称" 或 "文章标题 - 公众号"）
        title = re.sub(r"[_\-—|]\s*\S{2,20}$", "", raw_title).strip()
        if not title or len(title) < 2:
            title = raw_title

    # ── 2. 定位文章正文容器 ──
    content_div = soup.find("div", id="js_content")
    if not content_div:
        # 尝试其他常见容器
        content_div = soup.find("div", class_="rich_media_content")
    if not content_div:
        content_div = soup.find("article")
    if not content_div:
        content_div = soup.find("body")
    if not content_div:
        return {
            "title": title, "clean_text": "", "media_enrichments": [],
            "confidence": 0.0, "needs_review": True,
            "notes": "无法定位文章正文容器"
        }

    # ── 3. 标记需要跳过的装饰性元素 ──
    skip_tags = {"script", "style", "noscript", "iframe", "svg", "video", "audio"}
    skip_classes = {"qr_code", "qrcode", "reward", "copyright", "profile",
                    "avatar", "emoji", "wx_tap_link", "original_primary",
                    "rich_media_meta", "reward_area", "like_comment",
                    "qr_code_pc", "code_pc", "img_loading"}

    # ── 4. DOM 遍历：按文档顺序收集文本和图片 ──
    paragraphs: List[str] = []          # 文本段落
    content_images: List[Dict] = []     # 内容图片信息
    all_images: List[Dict] = []         # 所有图片信息
    image_counter = 0                    # 内容图计数器
    total_images = 0                     # 总图片计数器

    def should_skip(tag: Tag) -> bool:
        """判断是否跳过该标签及其子节点。"""
        if tag.name in skip_tags:
            return True
        cls = " ".join(tag.get("class", []))
        for sc in skip_classes:
            if sc in cls.lower():
                return True
        # 跳过隐藏元素
        style = tag.get("style", "")
        if "display:none" in style or "visibility:hidden" in style:
            return True
        return False

    def walk_node(node, current_paragraph: List[str]):
        """递归遍历 DOM，收集文本和图片。"""
        nonlocal image_counter, total_images

        if isinstance(node, NavigableString):
            text = str(node).strip()
            if text:
                current_paragraph.append(text)
            return

        if not isinstance(node, Tag):
            return

        if should_skip(node):
            return

        # 遇到图片
        if node.name == "img":
            total_images += 1
            is_content, reason = _is_likely_content_image(node)
            src = node.get("data-src") or node.get("src") or ""
            caption = _extract_image_caption(node) if is_content else None

            all_images.append({
                "total_index": total_images - 1,
                "is_content": is_content,
                "reason": reason,
                "src": src[:120],
                "caption": caption,
            })

            if is_content:
                # 将当前积累的段落文本合并为一段，然后插入图片标记
                if current_paragraph:
                    para_text = " ".join(current_paragraph).strip()
                    if para_text:
                        paragraphs.append(para_text)
                    current_paragraph.clear()

                image_counter += 1
                paragraphs.append(f"<图片{image_counter}>")

                content_images.append({
                    "index": total_images - 1,  # 在所有图片中的位置
                    "is_content": True,
                    "caption": caption,
                })
            return

        # 遇到块级元素：段落结束
        if node.name in ("p", "div", "section", "h1", "h2", "h3", "h4", "h5", "h6",
                          "blockquote", "li", "br", "hr"):
            if current_paragraph:
                para_text = " ".join(current_paragraph).strip()
                if para_text:
                    paragraphs.append(para_text)
                current_paragraph.clear()

        # 递归处理子节点
        for child in node.children:
            walk_node(child, current_paragraph)

        # 块级元素结束后也换段
        if node.name in ("p", "div", "section", "h1", "h2", "h3", "h4", "h5", "h6",
                          "blockquote", "li"):
            if current_paragraph:
                para_text = " ".join(current_paragraph).strip()
                if para_text:
                    paragraphs.append(para_text)
                current_paragraph.clear()

    # 开始遍历
    current_para: List[str] = []
    for child in content_div.children:
        walk_node(child, current_para)
    # 收集剩余文本
    if current_para:
        para_text = " ".join(current_para).strip()
        if para_text:
            paragraphs.append(para_text)

    # ── 5. 组装输出 ──
    clean_text = "\n".join(paragraphs)

    # 清洗残留噪声
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    clean_text = re.sub(r" {2,}", " ", clean_text)
    clean_text = clean_text.strip()

    # 构建 media_enrichments（对齐外部 image_urls 的顺序）
    # all_images 按 DOM 顺序排列，与 image_urls 顺序一致
    media_enrichments = []
    for img in all_images:
        media_enrichments.append({
            "index": img["total_index"],
            "is_content": img["is_content"],
            "caption": img["caption"],
        })

    # 判定是否需要复核
    needs_review = False
    review_reasons = []
    decoration_count = sum(1 for img in all_images if not img["is_content"])
    content_count = sum(1 for img in all_images if img["is_content"])

    if content_count == 0 and total_images > 0:
        needs_review = True
        review_reasons.append("所有图片被判为装饰图，可能有误判")
    if content_count > 30:
        needs_review = True
        review_reasons.append(f"内容图片较多 ({content_count})，建议抽查")

    notes = f"BS4模式: {total_images}张图, {content_count}内容+{decoration_count}装饰"
    if review_reasons:
        notes += "; " + "; ".join(review_reasons)

    return {
        "title": title,
        "clean_text": clean_text,
        "media_enrichments": media_enrichments,
        "confidence": 0.85,  # 固定值：规则置信度
        "needs_review": needs_review,
        "notes": notes,
        "_method": "bs4_dom_walk",
    }


# ═══════════════════════════════════════════════════════════════
# 命令行测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="BS4 HTML 结构提取器（测试）")
    parser.add_argument("--html-file", help="HTML 文件路径")
    parser.add_argument("--html-text", help="HTML 文本")
    args = parser.parse_args()

    if args.html_file:
        html = Path(args.html_file).read_text(encoding="utf-8")
    elif args.html_text:
        html = args.html_text
    else:
        print("请提供 --html-file 或 --html-text")
        raise SystemExit(1)

    result = extract_from_html(html)
    print(json.dumps({
        "title": result["title"],
        "clean_text": result["clean_text"][:500] + "..." if len(result.get("clean_text", "")) > 500 else result.get("clean_text", ""),
        "media_count": len(result["media_enrichments"]),
        "content_images": sum(1 for m in result["media_enrichments"] if m["is_content"]),
        "decoration_images": sum(1 for m in result["media_enrichments"] if not m["is_content"]),
        "confidence": result["confidence"],
        "needs_review": result["needs_review"],
        "notes": result["notes"],
    }, ensure_ascii=False, indent=2))

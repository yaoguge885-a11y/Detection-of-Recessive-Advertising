#!/usr/bin/env python3
"""
小红书 (Xiaohongshu) 系统爬虫 —— 从作者主页抓取笔记（图文/视频）。

用法:
  python data-tooling/crawler/xiaohongshu_crawler.py \
    --url "https://www.xiaohongshu.com/user/profile/{user_id}" \
    --max-items 100 \
    --cookies cookies.json \
    --collector D

输出: 自动创建 data/run_outputs/xiaohongshu_{timestamp}/ 目录，
      包含 urls.txt, anonymized_posts.jsonl, media/

特性:
  - 通过 Playwright 真实浏览器环境绕过签名校验
  - 解析 SSR __INITIAL_STATE__ JSON 提取结构化数据
  - 笔记图片 + 评论图片下载
  - <图片N> 标记插入正文
  - Cookie 持久化支持
  - 反爬延迟 2-5s/条
"""
from __future__ import annotations

import argparse
import json
import os
import math
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

import requests

# 项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# ═══════════════════════════════════════════════════════════════
# Cookie 管理
# ═══════════════════════════════════════════════════════════════

def load_cookies_for_playwright(cookies_arg: str) -> List[Dict]:
    """加载cookies并转为Playwright格式 [{name,value,domain,path},...]"""
    from crawler_utils import parse_cookies

    raw = parse_cookies(cookies_arg)
    pw_cookies = []
    for name, value in raw.items():
        pw_cookies.append({
            "name": name,
            "value": value,
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
    return pw_cookies


def _open_page(p, cookies: Optional[List[Dict]], cdp_url: Optional[str]):
    """Return browser, context, page, and whether this process owns the browser."""
    if cdp_url:
        browser = p.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise RuntimeError("CDP Chrome has no browser context")
        context = browser.contexts[0]
        return browser, context, context.new_page(), False

    try:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
    except Exception:
        chrome = next((Path(path) for path in (
            os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        ) if Path(path).is_file()), None)
        if not chrome:
            raise
        browser = p.chromium.launch(executable_path=str(chrome), headless=True)

    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    if cookies:
        context.add_cookies(cookies)
    return browser, context, context.new_page(), True


def _read_stable_page_content(page) -> str:
    """CDP pages can be mid-navigation; retry instead of accepting a blank DOM."""
    last_html = ""
    for _ in range(5):
        try:
            html = page.content()
            if "__INITIAL_STATE__" in html or "noteDetailMap" in html:
                return html
            last_html = html
        except Exception:
            pass
        page.wait_for_timeout(400)
    return last_html


def _note_url(note_id: str, token: Optional[str] = None) -> str:
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if token:
        return f"{url}?xsec_token={quote(token, safe='')}&xsec_source=pc_search"
    return url


# ═══════════════════════════════════════════════════════════════
# URL 发现 (Playwright)
# ═══════════════════════════════════════════════════════════════

def discover_xhs_notes(
    profile_url: str,
    max_items: int = 100,
    cookies: Optional[List[Dict]] = None,
    cdp_url: Optional[str] = None,
) -> List[Dict]:
    """通过 Playwright 滚动用户主页，监听 XHR 获取笔记列表。

    Returns:
        [{note_id, title, type, published_at, author_name, author_id, like_count}, ...]
    """
    from playwright.sync_api import sync_playwright

    # 提取 user_id
    m = re.search(r"/user/profile/([a-zA-Z0-9]+)", profile_url)
    if not m:
        raise ValueError(f"无法从URL提取 user_id: {profile_url}")
    user_id = m.group(1)

    notes = []
    collected_note_ids = set()

    with sync_playwright() as p:
        browser, _context, page, owns_browser = _open_page(p, cookies, cdp_url)

        # 拦截 XHR 响应收集笔记数据
        captured_responses = []

        def handle_response(response):
            url = response.url
            if "/web_api/sns/v1/user/notes" in url or "/api/sns/web/v1/user_posted" in url:
                try:
                    body = response.json()
                    captured_responses.append(body)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            print(f"  打开用户主页: {profile_url}")
            try:
                page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                print(f"    页面加载超时，继续读取已收到内容: {exc}")
            page.wait_for_timeout(3000)

            # 滚动加载
            for scroll_round in range(8):
                if len(notes) >= max_items:
                    break
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2500)
                print(f"    滚动 {scroll_round + 1}/8, 已收集 {len(notes)} 条")

            # 也从 __INITIAL_STATE__ 提取
            try:
                html = _read_stable_page_content(page)
                notes_from_html = _extract_notes_from_profile_html(html, user_id)
                for n in notes_from_html:
                    if n["note_id"] not in collected_note_ids:
                        collected_note_ids.add(n["note_id"])
                        notes.append(n)
            except Exception:
                pass

        except Exception as e:
            print(f"    主页加载失败: {e}")
        finally:
            page.close()
            if owns_browser:
                browser.close()

    # 从拦截的响应中提取笔记
    for resp_body in captured_responses:
        try:
            data_list = (
                resp_body.get("data", {}).get("notes") or
                resp_body.get("data", {}).get("items") or
                resp_body.get("data", [])
            )
            for note_data in data_list:
                note_id = str(note_data.get("noteId") or note_data.get("note_id") or note_data.get("id", ""))
                if note_id and note_id not in collected_note_ids:
                    collected_note_ids.add(note_id)
                    notes.append({
                        "note_id": note_id,
                        "title": note_data.get("displayTitle") or note_data.get("title") or "",
                        "type": note_data.get("type") or note_data.get("noteType") or "normal",
                        "published_at": None,
                        "author_name": note_data.get("user", {}).get("nickname") or "",
                        "author_id": str(note_data.get("user", {}).get("userId") or user_id),
                        "like_count": int(note_data.get("interactInfo", {}).get("likedCount") or 0),
                    })
        except Exception:
            pass

    notes = notes[:max_items]
    author_name = notes[0]["author_name"] if notes else ""
    print(f"  ✓ 发现 {len(notes)} 条笔记 (作者: {author_name})")
    return notes


def _extract_notes_from_profile_html(html: str, user_id: str) -> List[Dict]:
    """从主页 __INITIAL_STATE__ HTML 提取初始笔记列表。"""
    notes = []
    try:
        m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*\n", html, re.DOTALL)
        if not m:
            m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?})\s*</script>', html, re.DOTALL)
        if not m:
            return notes

        state = json.loads(m.group(1).replace("undefined", "null"))
        user_root = state.get("user", {}) or {}
        user_data = user_root.get("userPageData", {}) or state.get("userPageData", {}) or user_root
        notes_data = (user_data.get("notes") or user_data.get("noteList") or
                      user_root.get("notes") or [])

        for n in notes_data:
            note_id = str(n.get("noteId") or n.get("note_id") or n.get("id", ""))
            if note_id:
                notes.append({
                    "note_id": note_id,
                    "title": n.get("displayTitle") or n.get("title") or "",
                    "type": n.get("type") or "normal",
                    "published_at": None,
                    "author_name": user_data.get("nickname") or "",
                    "author_id": str(user_data.get("userId") or user_id),
                    "like_count": int(n.get("interactInfo", {}).get("likedCount") or 0),
                })
    except Exception:
        pass
    return notes


def read_note_urls(input_path: str, max_items: int) -> List[Dict]:
    """Read public note URLs, preserving their search navigation token when present."""
    notes = []
    for raw in Path(input_path).read_text(encoding="utf-8").splitlines():
        url = raw.strip()
        if not url or url.startswith("#"):
            continue
        parsed = urlparse(url)
        match = re.search(r"/(?:explore|discovery/item)/([A-Za-z0-9]+)", parsed.path)
        if not match:
            print(f"  跳过非笔记链接: {url}")
            continue
        notes.append({"note_id": match.group(1), "url": url, "title": "", "type": "normal"})
        if len(notes) >= max_items:
            break
    return notes


def discover_xhs_search_notes(
    query: str, max_items: int, cdp_url: str,
) -> List[Dict]:
    """Observe normal browser search responses and retain the detail-page token."""
    from playwright.sync_api import sync_playwright

    items: List[Dict] = []
    seen = set()
    with sync_playwright() as p:
        browser, _context, page, _owns_browser = _open_page(p, None, cdp_url)

        def handle_response(response):
            if "/api/sns/web/v2/search/notes" not in response.url:
                return
            try:
                payload = response.json()
                data = payload.get("data", {}) or {}
                candidates = data.get("items") or data.get("notes") or []
                for item in candidates:
                    card = item.get("noteCard") or item.get("note_card") or item
                    note_id = str(card.get("noteId") or card.get("id") or item.get("id") or "")
                    token = item.get("xsec_token") or item.get("xsecToken") or card.get("xsec_token")
                    if not note_id or not token or note_id in seen:
                        continue
                    seen.add(note_id)
                    user = card.get("user") or {}
                    items.append({
                        "note_id": note_id,
                        "url": _note_url(note_id, str(token)),
                        "title": card.get("displayTitle") or card.get("title") or "",
                        "type": card.get("type") or "normal",
                        "author_name": user.get("nickname") or "",
                        "author_id": str(user.get("userId") or ""),
                    })
            except Exception:
                pass

        page.on("response", handle_response)
        try:
            page.goto(
                "https://www.xiaohongshu.com/search_result?keyword=" + quote(query),
                wait_until="domcontentloaded", timeout=30000,
            )
            page.wait_for_timeout(3500)
        finally:
            page.close()
    return items[:max_items]


# ═══════════════════════════════════════════════════════════════
# 单条笔记抓取
# ═══════════════════════════════════════════════════════════════

def fetch_xhs_note_html(
    note_id: str,
    note_url: Optional[str] = None,
    cookies: Optional[List[Dict]] = None,
    cdp_url: Optional[str] = None,
    collect_comments: bool = True,
) -> str:
    """Playwright 获取单个笔记页面 HTML (SSR)。"""
    from playwright.sync_api import sync_playwright

    url = note_url or _note_url(note_id)
    with sync_playwright() as p:
        browser, _context, page, owns_browser = _open_page(p, cookies, cdp_url)

        # 拦截评论 API 响应
        comment_responses = []

        def _handle_response(response):
            if "comment" in response.url.lower() and response.url.startswith("http"):
                try:
                    comment_responses.append(response.json())
                except Exception:
                    pass

        if collect_comments:
            page.on("response", _handle_response)
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                print(f"    页面加载超时，继续读取已收到内容: {exc}")
            page.wait_for_timeout(2000)
            if collect_comments:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
            html = _read_stable_page_content(page)
        finally:
            page.close()
            if owns_browser:
                browser.close()

        # 将评论数据注入 HTML（作为 script 标签附加）
        if comment_responses:
            comments_json = json.dumps(comment_responses, ensure_ascii=False)
            # 简单附加到 HTML 末尾
            html += f'\n<!--XHS_COMMENTS:{comments_json}-->'

    return html


def crawl_one_xhs_note(
    note_info: Dict,
    media_base_dir: Path,
    salt: str,
    collector: str,
    session: requests.Session,
    cookies: Optional[List[Dict]] = None,
    cdp_url: Optional[str] = None,
    max_comments: int = 50,
    download_media: bool = True,
    terms_checked_at: Optional[str] = None,
) -> Optional[Dict]:
    """抓取单条小红书笔记，构建标准化记录。"""
    from xiaohongshu_html_extractor import extract_xhs_note
    from crawler_utils import (
        build_post_record, download_images, download_comment_images,
        stable_hash,
    )

    note_id = note_info["note_id"]
    url = note_info.get("url") or _note_url(note_id)
    author_name = note_info.get("author_name", "")
    author_id = note_info.get("author_id", "")

    print(f"  [笔记] {note_id} {note_info.get('title','')[:50]}...")

    # ── 1. 获取页面 ──
    try:
        html = fetch_xhs_note_html(note_id, url, cookies, cdp_url, collect_comments=max_comments > 0)
    except Exception as e:
        print(f"    ✗ 页面获取失败: {e}")
        return None

    # ── 2. 提取内容 ──
    try:
        extracted = extract_xhs_note(html)
    except Exception as e:
        print(f"    ✗ 提取失败: {e}")
        return None

    if not extracted.get("note_id"):
        print("    提取结果没有笔记 ID，跳过空记录")
        return None

    title = extracted.get("title") or note_info.get("title") or ""
    clean_text = extracted.get("clean_text", "")
    image_urls = extracted.get("image_urls", [])
    published_at = extracted.get("published_at")
    if not author_name:
        author_name = extracted.get("author_name") or ""
    if not author_id:
        author_id = str(extracted.get("author_id") or "")

    # ── 3. 图片下载 ──
    media_records = []
    if extracted.get("note_type") == "video":
        media_records = [{"ref": None, "source_url": url, "_media_type": "video"}]
    elif image_urls and download_media:
        try:
            post_id_short = stable_hash(url, salt, length=16)
            media_records = download_images(
                image_urls, post_id_short, media_base_dir,
                session=session, referer="https://www.xiaohongshu.com",
            )
            print(f"    图片: {len(media_records)} 下载")
        except Exception as e:
            print(f"    图片下载失败: {e}")

    # ── 4. 评论处理 ──
    comments = []
    comments_raw = extracted.get("comments_raw", [])
    for rc in comments_raw[:max_comments]:
        comment_text = rc.get("text") or ""
        comment_pics = rc.get("picture_urls", [])
        if comment_pics:
            markers = "".join(f"<图片{i+1}>" for i in range(len(comment_pics)))
            comment_text = comment_text + " " + markers
            comment_id = stable_hash(rc.get("comment_id", note_id), salt, length=16)
            download_comment_images(
                comment_pics, comment_id, media_base_dir,
                session=session, referer="https://www.xiaohongshu.com",
            )
        comments.append({
            "comment_id": stable_hash(rc.get("comment_id", note_id), salt, length=16),
            "author_id": stable_hash(rc.get("author_id", ""), salt, length=24),
            "text": comment_text,
            "like_count": rc.get("like_count", 0),
            "is_pinned": rc.get("is_pinned", False),
        })
    if comments:
        print(f"    评论: {len(comments)} 条")

    # ── 5. 构建记录 ──
    record = build_post_record(
        url=url,
        publisher_name=author_name,
        publisher_id=author_id,
        title=title,
        body_text=clean_text,
        media_records=media_records,
        published_at=published_at,
        history_post_ids=[],
        salt=salt,
        collector=collector,
        terms_checked_at=terms_checked_at,
        comments=comments,
    )
    return record


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="小红书爬虫 — 采集少量公开笔记")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="小红书用户主页 URL")
    source.add_argument("--input", help="UTF-8 笔记 URL 清单，每行一个")
    source.add_argument("--query", action="append", help="浏览器搜索关键词；可重复指定")
    parser.add_argument("--max-items", type=int, default=100, help="最大抓取条数")
    parser.add_argument("--max-comments-per-post", type=int, default=50, help="每条笔记最大评论数")
    parser.add_argument("--output-dir", default="data/run_outputs", help="输出根目录")
    parser.add_argument("--output", default=None, help="指定输出JSONL文件路径")
    parser.add_argument("--media-dir", default=None, help="指定媒体目录")
    parser.add_argument("--cookies", default="", help="Cookie文件路径或字符串")
    parser.add_argument("--cdp-url", default=None, help="已登录专用 Chrome 的 CDP 地址")
    parser.add_argument("--collector", default="D", help="采集者标识")
    parser.add_argument("--no-images", action="store_true", help="跳过图片下载")
    parser.add_argument("--no-comments", action="store_true", help="跳过评论抓取")
    parser.add_argument("--terms-checked-at", default=None, help="条款检查日期")
    args = parser.parse_args()
    if args.cdp_url and args.cookies:
        parser.error("--cdp-url 和 --cookies 不能同时使用")

    from dotenv import load_dotenv
    load_dotenv()

    from crawler_utils import get_salt

    salt = get_salt()

    # ── 自动生成输出路径 ──
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    platform = "xiaohongshu"
    if args.output:
        output_path = Path(args.output)
        run_dir = output_path.parent
    else:
        run_dir = Path(args.output_dir) / f"{platform}_{ts_str}"
        output_path = run_dir / "anonymized_posts.jsonl"

    if args.media_dir:
        media_base_dir = Path(args.media_dir)
    else:
        media_base_dir = run_dir / "media"

    run_dir.mkdir(parents=True, exist_ok=True)
    media_base_dir.mkdir(parents=True, exist_ok=True)
    print(f"运行目录: {run_dir}")
    print(f"媒体目录: {media_base_dir}")

    # ── Cookies ──
    pw_cookies = load_cookies_for_playwright(args.cookies) if args.cookies else None
    if pw_cookies:
        print(f"已加载 {len(pw_cookies)} 个 cookies")

    # ── 1. URL 发现 ──
    session = requests.Session()
    if args.input:
        notes = read_note_urls(args.input, args.max_items)
    elif args.query:
        if not args.cdp_url:
            parser.error("--query 需要 --cdp-url，以使用已登录的专用 Chrome")
        per_query = max(1, math.ceil(args.max_items / len(args.query)))
        notes = []
        for query in args.query:
            found = discover_xhs_search_notes(query, per_query, args.cdp_url)
            print(f"查询 {query!r}: 发现 {len(found)} 条")
            notes.extend(found)
        notes = notes[:args.max_items]
    else:
        print(f"\n发现笔记: {args.url}")
        notes = discover_xhs_notes(
            args.url, max_items=args.max_items, cookies=pw_cookies, cdp_url=args.cdp_url,
        )
    if not notes:
        print("未发现任何笔记，退出。")
        return 1

    # 保存 URL 列表
    urls_file = run_dir / "urls.txt"
    with urls_file.open("w", encoding="utf-8") as f:
        for n in notes:
            note_url = f"https://www.xiaohongshu.com/explore/{n['note_id']}"
            f.write(f"{note_url}\t{n.get('title','')}\t{n.get('author_name','')}\n")
    print(f"URL 列表: {urls_file} ({len(notes)} 条)")

    # ── 2. 逐条抓取 ──
    print(f"\n开始抓取 {len(notes)} 条笔记...")
    records_written = 0

    for i, note_info in enumerate(notes, 1):
        print(f"\n--- [{i}/{len(notes)}] ---")
        try:
            record = crawl_one_xhs_note(
                note_info, media_base_dir, salt, args.collector, session,
                cookies=pw_cookies,
                cdp_url=args.cdp_url,
                max_comments=0 if args.no_comments else args.max_comments_per_post,
                download_media=not args.no_images,
                terms_checked_at=args.terms_checked_at,
            )
            if record is None:
                continue
            with output_path.open("a", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, separators=(",", ":"))
                f.write("\n")
            records_written += 1
            print(f"  已保存 ({records_written})")
        except Exception as e:
            print(f"  ✗ 失败: {e}")

        # 小红书反爬延迟 (2-5s)
        if i < len(notes):
            time.sleep(random.uniform(2.0, 5.0))

    print(f"\n{'='*60}")
    print(f"完成: {records_written} 条 -> {output_path}")
    print(f"  运行目录: {run_dir}")

    return 0 if records_written else 2


if __name__ == "__main__":
    raise SystemExit(main())

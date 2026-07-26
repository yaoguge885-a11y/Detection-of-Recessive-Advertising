#!/usr/bin/env python3
"""
B站 (Bilibili) 系统爬虫 —— 从作者主页抓取视频/图文动态/专栏文章。

用法:
  python data-tooling/crawler/bilibili_crawler.py \
    --url "https://space.bilibili.com/{mid}" \
    --max-items 80 \
    --collector D

输出: 自动创建 data/run_outputs/bilibili_{timestamp}/ 目录，
      包含 urls.txt, anonymized_posts.jsonl, media/

特性:
  - wbi 签名实现（B站公开前端算法）
  - Playwright 渲染页面 + 反检测
  - 三种内容类型：视频(video) / 图文动态(opus) / 专栏(article)
  - 视频不下载封面/视频文件（media.type="video", ref=null）
  - 评论抓取（含评论中的图片）
  - BS4 DOM 提取正文 + <图片N> 标记
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests

# 项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# 动态导入共享模块（避免循环依赖）
_crawler_dir = Path(__file__).resolve().parent
if str(_crawler_dir) not in sys.path:
    sys.path.insert(0, str(_crawler_dir))

# ═══════════════════════════════════════════════════════════════
# wbi 签名
# ═══════════════════════════════════════════════════════════════

_wbi_cache: Dict = {"img_key": "", "sub_key": "", "expires": 0}


def _fetch_wbi_keys(session: requests.Session) -> tuple:
    """获取 wbi 签名所需的 img_key 和 sub_key，缓存 30 分钟。"""
    now = time.time()
    if _wbi_cache["img_key"] and _wbi_cache["expires"] > now:
        return _wbi_cache["img_key"], _wbi_cache["sub_key"]

    try:
        resp = session.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"},
            timeout=10,
        )
        data = resp.json().get("data", {})
        wbi_img = data.get("wbi_img", {})
        img_key = wbi_img.get("img_key", "")
        sub_key = wbi_img.get("sub_key", "")
        if img_key:
            _wbi_cache["img_key"] = img_key.split("/")[-1].split(".")[0]
        if sub_key:
            _wbi_cache["sub_key"] = sub_key.split("/")[-1].split(".")[0]
        _wbi_cache["expires"] = now + 1800
    except Exception as e:
        print(f"  [wbi] nav 接口失败: {e}")

    return _wbi_cache["img_key"], _wbi_cache["sub_key"]


def _mixin_key(raw_key: str) -> str:
    """B站 mixin key 切片算法。"""
    order = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45,
             35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13]
    return "".join(raw_key[i] for i in order if i < len(raw_key))


def bilibili_wbi_sign(params: dict, session: requests.Session) -> dict:
    """对请求参数添加 wbi 签名 (w_rid, wts)。

    返回添加签名后的新参数字典。
    """
    img_key, sub_key = _fetch_wbi_keys(session)
    if not img_key or not sub_key:
        return params  # 签名不可用时原样返回

    mixin = _mixin_key(img_key + sub_key)
    wts = int(time.time())
    signed = dict(params)
    signed["wts"] = wts

    # 排序后拼接 + mixin_key → MD5
    sorted_str = "&".join(f"{k}={v}" for k, v in sorted(signed.items()))
    w_rid = hashlib.md5((sorted_str + mixin).encode()).hexdigest()
    signed["w_rid"] = w_rid

    return signed


# ═══════════════════════════════════════════════════════════════
# URL 发现
# ═══════════════════════════════════════════════════════════════

def discover_bilibili_posts(
    space_url: str,
    max_items: int = 80,
    session: Optional[requests.Session] = None,
) -> List[Dict]:
    """从 B站作者空间页发现内容列表。

    返回: [{url, title, content_type, published_at, author_name, author_mid}, ...]
    """
    if session is None:
        session = requests.Session()

    # 解析 mid
    mid = _extract_mid_from_url(space_url)
    if not mid:
        raise ValueError(f"无法从URL提取 mid: {space_url}")

    all_items: List[Dict] = []

    # ── 1. 视频列表 ──
    print(f"  发现视频列表 (mid={mid})...")
    for page in range(1, 6):
        params = {"mid": mid, "ps": 50, "pn": page, "order": "pubdate"}
        signed = bilibili_wbi_sign(params, session)
        try:
            resp = session.get(
                "https://api.bilibili.com/x/space/wbi/arc/search",
                params=signed,
                headers={"User-Agent": USER_AGENT, "Referer": f"https://space.bilibili.com/{mid}"},
                timeout=15,
            )
            data = resp.json()
            vlist = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break
            for v in vlist:
                bvid = v.get("bvid", "")
                if bvid:
                    all_items.append({
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "title": v.get("title", ""),
                        "content_type": "video",
                        "published_at": _ts_to_iso(v.get("created", 0)),
                        "author_name": v.get("author", ""),
                        "author_mid": str(v.get("mid", mid)),
                        "aid": v.get("aid"),
                        "bvid": bvid,
                    })
        except Exception as e:
            print(f"    视频API page {page} 失败: {e}")
            break
        time.sleep(0.5)

    # ── 2. 专栏列表 ──
    print(f"  发现专栏列表...")
    for page in range(1, 5):
        try:
            resp = session.get(
                "https://api.bilibili.com/x/space/article",
                params={"mid": mid, "pn": page, "ps": 30, "sort": "publish_time"},
                headers={"User-Agent": USER_AGENT, "Referer": f"https://space.bilibili.com/{mid}"},
                timeout=15,
            )
            data = resp.json()
            articles = data.get("data", {}).get("articles", [])
            if not articles:
                break
            for art in articles:
                cv_id = art.get("id")
                if cv_id:
                    all_items.append({
                        "url": f"https://www.bilibili.com/read/cv{cv_id}",
                        "title": art.get("title", ""),
                        "content_type": "article",
                        "published_at": _ts_to_iso(art.get("publish_time", 0)),
                        "author_name": art.get("author_name", ""),
                        "author_mid": str(art.get("author", {}).get("mid", mid)),
                        "cv_id": cv_id,
                    })
        except Exception as e:
            print(f"    专栏API page {page} 失败: {e}")
            break
        time.sleep(0.5)

    # ── 3. 动态列表 (Playwright) ──
    print(f"  发现动态列表 (Playwright)...")
    try:
        dynamic_items = _discover_dynamics_playwright(mid, max_items=min(max_items, 60))
        all_items.extend(dynamic_items)
    except Exception as e:
        print(f"    动态列表失败: {e}")

    # ── 去重、排序、截取 ──
    seen = set()
    unique = []
    for item in all_items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    unique.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    result = unique[:max_items]

    author_name = result[0]["author_name"] if result else ""
    print(f"  ✓ 总计发现 {len(unique)} 条（去重），截取 {len(result)} 条 (作者: {author_name})")
    return result


def _extract_mid_from_url(url: str) -> Optional[str]:
    """从B站空间URL提取mid。"""
    m = re.search(r"space\.bilibili\.com/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"mid=(\d+)", url)
    if m:
        return m.group(1)
    return None


def _ts_to_iso(ts) -> Optional[str]:
    """Unix时间戳 → ISO格式。"""
    if not ts or ts == 0:
        return None
    try:
        from datetime import datetime, timezone, timedelta
        CST = timezone(timedelta(hours=8))
        dt = datetime.fromtimestamp(int(ts), tz=CST)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    except Exception:
        return str(ts)


def _discover_dynamics_playwright(mid: str, max_items: int = 60) -> List[Dict]:
    """通过Playwright获取B站动态列表。"""
    from playwright.sync_api import sync_playwright

    items = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
        )
        page = context.new_page()
        page.set_extra_http_headers({"Referer": "https://space.bilibili.com"})

        try:
            page.goto(f"https://space.bilibili.com/{mid}/dynamic", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # 滚动加载更多
            for _ in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            content = page.content()
            soup = __import__("bs4", fromlist=["BeautifulSoup"]).BeautifulSoup(content, "html.parser")

            # 查找动态卡片链接
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "t.bilibili.com/" in href:
                    dyn_id = re.search(r"t\.bilibili\.com/(\d+)", href)
                    if dyn_id:
                        dynamic_id = dyn_id.group(1)
                        url = f"https://t.bilibili.com/{dynamic_id}"
                        if url not in {i["url"] for i in items}:
                            items.append({
                                "url": url,
                                "title": link.get_text(strip=True)[:80],
                                "content_type": "opus",
                                "published_at": None,
                                "author_name": "",
                                "author_mid": mid,
                                "dynamic_id": dynamic_id,
                            })
        except Exception as e:
            print(f"    [Playwright动态] {e}")
        finally:
            browser.close()

    return items[:max_items]


# ═══════════════════════════════════════════════════════════════
# 评论抓取
# ═══════════════════════════════════════════════════════════════

def fetch_bilibili_comments(
    oid: str,
    comment_type: int,
    session: requests.Session,
    max_comments: int = 50,
) -> List[Dict]:
    """抓取B站评论。

    Args:
        oid: 内容ID（aid / cv_id / dynamic_id）
        comment_type: 1=视频, 12=专栏, 17=动态
        session: requests会话
        max_comments: 最大评论数

    Returns:
        标准化评论列表 [{comment_id, author_name, author_id, text, picture_urls, like_count, is_pinned}]
    """
    comments = []
    page = 1

    while len(comments) < max_comments:
        try:
            resp = session.get(
                "https://api.bilibili.com/x/v2/reply",
                params={"type": comment_type, "oid": oid, "pn": page, "ps": 50, "sort": 1},
                headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"},
                timeout=15,
            )
            data = resp.json()
            replies = data.get("data", {}).get("replies", [])
            if not replies:
                break

            for reply in replies:
                if len(comments) >= max_comments:
                    break
                member = reply.get("member", {})
                content = reply.get("content", {})
                picture_urls = []

                # 评论中的图片
                pictures = content.get("pictures", [])
                for pic in pictures:
                    img_url = pic.get("img_src") or pic.get("img_url") or ""
                    if img_url:
                        # 去掉尺寸限制后缀获取原图
                        img_url = re.sub(r"@\d+w_\d+h", "", img_url)
                        picture_urls.append(img_url)

                comments.append({
                    "comment_id": str(reply.get("rpid", "")),
                    "author_name": member.get("uname", ""),
                    "author_id": str(member.get("mid", "")),
                    "text": (content.get("message") or "").strip(),
                    "picture_urls": picture_urls,
                    "like_count": int(reply.get("like", 0)),
                    "is_pinned": bool(reply.get("is_pinned", False)),
                    "created_at": _ts_to_iso(reply.get("ctime", 0)),
                })

            page += 1
            if page > 3:  # 最多3页
                break
            time.sleep(0.3)

        except Exception as e:
            print(f"    评论获取失败: {e}")
            break

    return comments


# ═══════════════════════════════════════════════════════════════
# 单条内容抓取
# ═══════════════════════════════════════════════════════════════

def crawl_one_bilibili_post(
    item: Dict,
    media_base_dir: Path,
    salt: str,
    collector: str,
    session: requests.Session,
    max_comments: int = 50,
) -> Dict:
    """抓取单条B站内容，构建标准化记录。

    Returns:
        标准 post record dict（与 crawl_public_posts.py 输出格式一致）
    """
    from bilibili_html_extractor import extract_from_bilibili_html
    from crawler_utils import (
        build_post_record, download_images, download_comment_images,
        stable_hash, platform_from_url,
    )

    url = item["url"]
    content_type = item.get("content_type", "video")
    author_name = item.get("author_name", "")
    author_mid = item.get("author_mid", "")

    print(f"  [{content_type}] {item.get('title', url)[:60]}...")

    # ── 1. 获取页面 ──
    try:
        html = _fetch_page_playwright(url)
    except Exception as e:
        print(f"    ✗ 页面获取失败: {e}")
        return _error_record(url, author_name, author_mid, str(e), salt, collector)

    # ── 2. BS4 提取 ──
    try:
        extracted = extract_from_bilibili_html(html, content_type)
    except Exception as e:
        print(f"    ✗ BS4提取失败: {e}")
        return _error_record(url, author_name, author_mid, str(e), salt, collector)

    title = extracted.get("title") or item.get("title") or ""
    clean_text = extracted.get("clean_text", "")
    image_urls = extracted.get("image_urls", [])
    published_at = extracted.get("published_at") or item.get("published_at")
    if not author_name:
        author_name = extracted.get("author_name") or ""

    # ── 3. 图片下载 ──
    media_records = []
    if content_type == "video":
        # 视频: 仅记录不下载
        media_records = [{
            "ref": None,
            "source_url": url,
            "_media_type": "video",
        }]
    elif image_urls:
        try:
            post_id_short = stable_hash(url, salt, length=16)
            media_records = download_images(
                image_urls, post_id_short, media_base_dir,
                session=session, referer="https://www.bilibili.com",
            )
            print(f"    图片: {len(media_records)} 下载")
        except Exception as e:
            print(f"    图片下载失败: {e}")

    # ── 4. 评论抓取 ──
    comments = []
    comment_type = _get_comment_type(content_type)
    oid = _get_oid(item, extracted, content_type)
    if oid and comment_type:
        try:
            raw_comments = fetch_bilibili_comments(str(oid), comment_type, session, max_comments)
            for rc in raw_comments:
                # 标准化评论
                comment_text = rc["text"]
                comment_pic_urls = rc.get("picture_urls", [])
                if comment_pic_urls:
                    markers = "".join(f"<图片{i+1}>" for i in range(len(comment_pic_urls)))
                    comment_text = comment_text + " " + markers
                    # 下载评论图片
                    comment_id = stable_hash(rc["comment_id"], salt, length=16)
                    download_comment_images(
                        comment_pic_urls, comment_id, media_base_dir,
                        session=session, referer="https://www.bilibili.com",
                    )

                comments.append({
                    "comment_id": stable_hash(rc["comment_id"], salt, length=16),
                    "author_id": stable_hash(rc["author_id"], salt, length=24),
                    "text": comment_text,
                    "like_count": rc["like_count"],
                    "is_pinned": rc["is_pinned"],
                })
            print(f"    评论: {len(comments)} 条")
        except Exception as e:
            print(f"    评论抓取失败: {e}")

    # ── 5. 构建记录 ──
    record = build_post_record(
        url=url,
        publisher_name=author_name,
        publisher_id=author_mid,
        title=title,
        body_text=clean_text,
        media_records=media_records,
        published_at=published_at,
        history_post_ids=[],
        salt=salt,
        collector=collector,
        terms_checked_at=None,
        comments=comments,
    )

    return record


def _get_comment_type(content_type: str) -> Optional[int]:
    return {"video": 1, "article": 12, "opus": 17}.get(content_type)


def _get_oid(item: Dict, extracted: Dict, content_type: str) -> Optional[str]:
    """获取评论API所需的oid。"""
    if content_type == "video":
        return str(extracted.get("aid") or item.get("aid") or "")
    elif content_type == "article":
        return str(extracted.get("cv_id") or item.get("cv_id") or "")
    elif content_type == "opus":
        return str(extracted.get("dynamic_id") or item.get("dynamic_id") or "")
    return None


def _fetch_page_playwright(url: str, timeout: int = 30000) -> str:
    """Playwright获取页面HTML。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        page = context.new_page()
        page.set_extra_http_headers({"Referer": "https://www.bilibili.com"})

        page.goto(url, wait_until="load", timeout=timeout)
        page.wait_for_timeout(random.randint(800, 2000))
        content = page.content()
        browser.close()
    return content


def _error_record(url: str, author_name: str, author_id: str, error: str,
                  salt: str, collector: str) -> Dict:
    """生成错误记录。"""
    from crawler_utils import build_post_record
    return build_post_record(
        url=url, publisher_name=author_name, publisher_id=author_id,
        title=f"[ERROR] {error[:80]}", body_text="",
        media_records=[], published_at=None, history_post_ids=[],
        salt=salt, collector=collector, terms_checked_at=None,
    )


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="B站爬虫 — 抓取作者全部内容")
    parser.add_argument("--url", required=True, help="B站作者空间URL (space.bilibili.com/{mid})")
    parser.add_argument("--max-items", type=int, default=80, help="最大抓取条数 (50-100)")
    parser.add_argument("--max-comments-per-post", type=int, default=50, help="每条帖子最大评论数")
    parser.add_argument("--output-dir", default="data/run_outputs", help="输出根目录")
    parser.add_argument("--output", default=None, help="指定输出JSONL文件路径（覆盖自动生成）")
    parser.add_argument("--media-dir", default=None, help="指定媒体目录（覆盖自动生成）")
    parser.add_argument("--collector", default="D", help="采集者标识")
    parser.add_argument("--no-images", action="store_true", help="跳过图片下载")
    parser.add_argument("--no-comments", action="store_true", help="跳过评论抓取")
    parser.add_argument("--terms-checked-at", default=None, help="条款检查日期")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    from crawler_utils import get_salt, stable_hash, DEFAULT_OUTPUT_ROOT

    salt = get_salt()

    # ── 自动生成输出路径 ──
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    platform = "bilibili"
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
    print(f"📁 运行目录: {run_dir}")
    print(f"📁 媒体目录: {media_base_dir}")

    # ── 1. URL 发现 ──
    session = requests.Session()
    print(f"\n🔍 发现内容: {args.url}")
    items = discover_bilibili_posts(args.url, max_items=args.max_items, session=session)
    if not items:
        print("未发现任何内容，退出。")
        return 1

    # 保存 URL 列表
    urls_file = run_dir / "urls.txt"
    with urls_file.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(f"{it['url']}\t{it.get('title','')}\t{it.get('author_name','')}\n")
    print(f"📋 URL列表: {urls_file} ({len(items)} 条)")

    # ── 2. 逐条抓取 ──
    print(f"\n📥 开始抓取 {len(items)} 条内容...")
    records_written = 0

    for i, item in enumerate(items, 1):
        print(f"\n--- [{i}/{len(items)}] ---")
        try:
            record = crawl_one_bilibili_post(
                item, media_base_dir, salt, args.collector, session,
                max_comments=0 if args.no_comments else args.max_comments_per_post,
            )
            with output_path.open("a", encoding="utf-8") as f:
                if records_written > 0:
                    f.write("\n")
                json.dump(record, f, ensure_ascii=False, indent=2)
                f.write("\n")
            records_written += 1
            print(f"  ✓ 已保存 ({records_written})")
        except Exception as e:
            print(f"  ✗ 失败: {e}")

        # 礼貌延迟
        delay = random.uniform(1.0, 3.0)
        time.sleep(delay)

    print(f"\n{'='*60}")
    print(f"✅ 完成: {records_written} 条 → {output_path}")
    print(f"  运行目录: {run_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import math
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

# ═══════════════════════════════════════════════════════════════
# 模拟真人：UA 池 + 浏览器指纹 + 人类行为 + Cookie 预热
# ═══════════════════════════════════════════════════════════════

# 真实 Chrome 版本池（随机轮换避免单一 UA 被识别）
CHROME_VERSIONS = ["123", "124", "125", "126"]


def _pick_browser_profile() -> Dict:
    """随机选一组真实 Chrome 指纹参数（UA + Client Hints 版本一致）。"""
    ver = random.choice(CHROME_VERSIONS)
    major = ver.split(".")[0]
    ua = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          f"(KHTML, like Gecko) Chrome/{ver}.0.0.0 Safari/537.36")
    sec_ch_ua = f'"Chromium";v="{major}", "Not/A=Brand";v="24", "Google Chrome";v="{major}"'
    return {"ua": ua, "sec_ch_ua": sec_ch_ua, "major": major}


def _browser_extra_headers(profile: Dict) -> Dict:
    """真实浏览器请求头（含 sec-ch-ua Client Hints）。"""
    return {
        "Referer": "https://www.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Sec-CH-UA": profile["sec_ch_ua"],
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-CH-UA-Mobile": "?0",
    }


def _build_fingerprint_script(profile: Dict) -> str:
    """生成完整浏览器指纹伪造脚本（B 层）：补齐 userAgentData/deviceMemory/Canvas 等。"""
    major = profile["major"]
    return (
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        "Object.defineProperty(navigator, 'userAgentData', {get: () => ({"
        f"brands: [{{brand:'Chromium',version:'{major}'}},{{brand:'Not/A=Brand',version:'24'}},"
        f"{{brand:'Google Chrome',version:'{major}'}}],"
        "mobile: false, platform: 'Windows'}));"
        "Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});"
        "Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});"
        "Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});"
        "Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});"
        "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});"
        "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
        "delete window.__playwright__binding__; delete window.__pwInitScripts;"
        "window.chrome = {runtime: {}};"
        "const _oq = window.navigator.permissions.query;"
        "window.navigator.permissions.query = (p) => (p.name==='notifications' "
        "? Promise.resolve({state: Notification.permission}) : _oq(p));"
        "Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth + 16});"
        "Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 90});"
        "const _oc = HTMLCanvasElement.prototype.toDataURL;"
        "HTMLCanvasElement.prototype.toDataURL = function(){ "
        "if(Math.random()<0.1){ return _oc.apply(this,arguments).replace(/[0-9a-f]{5}/,'0ffff'); } "
        "return _oc.apply(this,arguments); };"
    )


def _human_delay(min_ms: float, max_ms: float) -> float:
    """随机人类延迟（毫秒 → 秒）。"""
    return random.uniform(min_ms, max_ms) / 1000.0


def _human_scroll(page, target_steps: int = 8, base_step: int = 300,
                  min_delay: float = 350, max_delay: float = 1100):
    """模拟人类滚动（C 层）：随机步长、忽快忽慢、小幅回滚、阅读暂停、PageDown 混合。"""
    done = 0
    while done < target_steps:
        step = int(base_step * random.uniform(0.5, 1.6))
        try:
            page.evaluate(f"window.scrollBy(0, {step})")
        except Exception:
            return
        time.sleep(_human_delay(min_delay, max_delay))
        done += 1
        if random.random() < 0.22:  # 偶尔小幅回滚
            try:
                page.evaluate(f"window.scrollBy(0, -{int(base_step * random.uniform(0.1, 0.3))})")
            except Exception:
                pass
            time.sleep(_human_delay(150, 450))
        if random.random() < 0.15:  # 偶尔阅读暂停
            time.sleep(_human_delay(1200, 3000))
        if random.random() < 0.15:  # 偶尔键盘 PageDown
            try:
                page.keyboard.press("PageDown")
            except Exception:
                pass
            time.sleep(_human_delay(300, 800))


def _human_mouse_activity(page, width: int, height: int):
    """随机鼠标移动（缓动轨迹）+ 悬停（C 层）。"""
    try:
        sx = width * random.uniform(0.3, 0.7)
        sy = height * random.uniform(0.3, 0.7)
        ex = width * random.uniform(0.2, 0.9)
        ey = height * random.uniform(0.2, 0.9)
        page.mouse.move(sx, sy)
        time.sleep(_human_delay(120, 400))
        steps = random.randint(6, 14)
        for i in range(1, steps + 1):
            t = i / steps
            eased = t * t * (3 - 2 * t)  # smoothstep
            x = sx + (ex - sx) * eased
            y = sy + (ey - sy) * eased + math.sin(t * math.pi) * random.uniform(-8, 8)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.012, 0.045))
    except Exception:
        pass


def _human_think(min_s: float = 0.8, max_s: float = 2.5):
    """动作前随机思考停顿（C 层）。"""
    time.sleep(random.uniform(min_s, max_s))


def prewarm_bilibili_cookie(proxy: Optional[str] = None,
                            profile: Optional[Dict] = None) -> Dict:
    """浏览器提前访问 B 站官网，自动获取 buvid3/b_nut 等 Cookie（A 层）。

    仅用真实浏览器环境自然访问 B 站主页建立身份，不注入本机 Cookie。
    返回可复用的 storage_state（cookies + origins）。
    """
    from playwright.sync_api import sync_playwright
    profile = profile or _pick_browser_profile()
    print("[PREWARM] 预热: 访问 bilibili.com 主页获取 Cookie...")
    state: Dict = {"cookies": [], "origins": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(**_build_launch_args(proxy))
        vw, vh = random.randint(1360, 1600), random.randint(760, 900)
        context = browser.new_context(
            user_agent=profile["ua"],
            viewport={"width": vw, "height": vh},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        context.add_init_script(_build_fingerprint_script(profile))
        page = context.new_page()
        page.set_extra_http_headers(_browser_extra_headers(profile))
        try:
            page.goto("https://www.bilibili.com", wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(random.randint(2500, 4500))
            _human_mouse_activity(page, vw, vh)
            _human_scroll(page, target_steps=random.randint(2, 4), base_step=200)
            page.wait_for_timeout(random.randint(1500, 3000))
        except Exception as e:
            print(f"  [PREWARM] 预热访问异常: {e}")
        state = context.storage_state()
        browser.close()
    n_cookies = len(state.get("cookies", []))
    has_buvid = any("buvid" in c.get("name", "") for c in state.get("cookies", []))
    print(f"  [PREWARM] 完成: {n_cookies} 个 Cookie (buvid={has_buvid})")
    return state


# 动态导入共享模块（避免循环依赖）
_crawler_dir = Path(__file__).resolve().parent
if str(_crawler_dir) not in sys.path:
    sys.path.insert(0, str(_crawler_dir))


# ═══════════════════════════════════════════════════════════════
# 浏览器启动辅助
# ═══════════════════════════════════════════════════════════════

def _build_launch_args(proxy: Optional[str] = None) -> dict:
    """构建 Playwright chromium.launch 参数，可选代理。"""
    args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
    if proxy:
        args.append(f"--proxy-server={proxy}")
    return {"headless": True, "args": args}


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
        # 字段名是 img_url / sub_url（非 img_key / sub_key）
        img_url = wbi_img.get("img_url", "") or wbi_img.get("img_key", "")
        sub_url = wbi_img.get("sub_url", "") or wbi_img.get("sub_key", "")
        if img_url:
            _wbi_cache["img_key"] = img_url.split("/")[-1].split(".")[0]
        if sub_url:
            _wbi_cache["sub_key"] = sub_url.split("/")[-1].split(".")[0]
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
    proxy: Optional[str] = None,
    content_types: Optional[List[str]] = None,
    storage_state: Optional[Dict] = None,
    profile: Optional[Dict] = None,
) -> List[Dict]:
    """从 B站作者空间发现内容列表。

    核心策略：通过 Playwright 加载 B站空间子页面（/video, /article, /dynamic），
    拦截前端自动发起的 API 响应获取内容列表。利用真实浏览器环境稳定绕过风控。

    Args:
        space_url: 作者空间 URL
        max_items: 最大条数
        proxy: 可选代理
        content_types: 内容类型过滤，如 ["opus"] 只返回动态；None 返回全部
        storage_state: 预热获得的 Cookie（cookies+origins），复用身份
        profile: 随机浏览器指纹参数（UA/sec-ch-ua）

    Returns: [{url, title, content_type, published_at, author_name, author_mid}, ...]
    """
    from playwright.sync_api import sync_playwright

    profile = profile or _pick_browser_profile()

    mid = _extract_mid_from_url(space_url)
    if not mid:
        raise ValueError(f"无法从URL提取 mid: {space_url}")

    all_items: List[Dict] = []
    author_name = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(**_build_launch_args(proxy))
        # 随机视口尺寸模拟不同设备
        vw = random.randint(1200, 1500)
        vh = random.randint(700, 900)
        context = browser.new_context(
            user_agent=profile["ua"],
            viewport={"width": vw, "height": vh},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            storage_state=storage_state,
        )
        # 强化反检测：完整指纹伪造（B 层）
        context.add_init_script(_build_fingerprint_script(profile))
        page = context.new_page()
        page.set_extra_http_headers(_browser_extra_headers(profile))

        # 注册全局响应拦截
        video_items = []
        article_items = []
        _api_call_count = 0

        dynamic_items = []  # opus/动态

        def _on_resp(resp):
            nonlocal _api_call_count
            url = resp.url
            if "api.bilibili.com" in url:
                _api_call_count += 1
            if "api.bilibili.com/x/space/wbi/arc/search" in url:
                try:
                    body = resp.json()
                    code = body.get("code", -1)
                    if code == 0:
                        vlist = body.get("data", {}).get("list", {}).get("vlist", [])
                        print(f"    [API] video code=0, {len(vlist)} items")
                        for v in vlist:
                            video_items.append(v)
                    else:
                        print(f"    [API] video code={code} msg={body.get('message','')[:60]}")
                except Exception:
                    # 打印原始响应帮助诊断
                    raw = (resp.text() or "")[:200]
                    print(f"    [API] video status={resp.status} body={repr(raw)}")
            elif "api.bilibili.com/x/space/article" in url:
                try:
                    body = resp.json()
                    code = body.get("code", -1)
                    if code == 0:
                        arts = body.get("data", {}).get("articles", [])
                        print(f"    [API] article code=0, {len(arts)} items")
                        for a in arts:
                            article_items.append(a)
                    else:
                        print(f"    [API] article code={code} msg={body.get('message','')[:60]}")
                except Exception as ex:
                    print(f"    [API] article parse err: {ex}")
            elif "polymer/web-dynamic/v1/feed/space" in url:
                try:
                    body = resp.json()
                    code = body.get("code", -1)
                    if code == 0:
                        items = body.get("data", {}).get("items", [])
                        offset = body.get("data", {}).get("offset", "")
                        if items:
                            print(f"    [API] dynamic +{len(items)} (offset={str(offset)[:16]})")
                            for it in items:
                                dynamic_items.append(it)
                except Exception:
                    pass

        page.on("response", _on_resp)

        # ── 人类滚动/鼠标（C 层）：随机步长、回滚、阅读暂停、鼠标轨迹 ──
        def _slow_scroll(page, steps=8, step_px=300, delay_ms=600):
            """模拟人类滚动，触发B站懒加载。"""
            _human_mouse_activity(page, vw, vh)
            _human_scroll(page, target_steps=steps, base_step=step_px,
                          min_delay=delay_ms * 0.6, max_delay=delay_ms * 1.2)

        # ── 1. 视频列表：渐进式重试 + DOM回退 ──
        print("  发现视频列表...")
        # 渐进式重试间隔（秒）：逐步加长等待模拟真人
        retry_delays = [2, 5, 8, 12]
        # 多种视频页入口切换
        video_urls = [
            f"https://space.bilibili.com/{mid}/video?tid=0&pn=1&keyword=&order=pubdate",
            f"https://space.bilibili.com/{mid}/video",
            f"https://space.bilibili.com/{mid}?from=video",  # 从主页触发
        ]

        for attempt in range(len(retry_delays) + 1):
            if content_types and "video" not in content_types:
                break  # 只抓其他类型时跳过视频发现
            if len(video_items) >= 5:
                break
            url_idx = attempt % len(video_urls)
            v_url = video_urls[url_idx]
            try:
                if attempt > 0:
                    wait = retry_delays[attempt - 1] + random.uniform(0, 3)
                    print(f"    重试 {attempt+1}/{len(retry_delays)+1}, 等待 {wait:.0f}s... ({v_url.split('/')[-1][:30]})")
                    time.sleep(wait)

                page.goto(v_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                _slow_scroll(page, steps=10, step_px=500, delay_ms=800)
                page.wait_for_timeout(2000)

                page_title = page.title()
                print(f"    页面: {page_title[:50]}, API: {_api_call_count}次, 视频: {len(video_items)}")
            except Exception as e:
                print(f"    视频页异常: {e}")

        # DOM回退：API全封时从HTML提取（保底至少得5-10条）
        if not (content_types and "video" not in content_types) and len(video_items) < 5:
            print(f"    API仅获{len(video_items)}条，启动 DOM 深度回退...")
            try:
                from bs4 import BeautifulSoup
                page.goto(f"https://space.bilibili.com/{mid}/video", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                # 深度滚动多次
                for _ in range(12):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(800)
                page.wait_for_timeout(2000)

                soup = BeautifulSoup(page.content(), "html.parser")
                seen_bv = set()
                for a in soup.select('a[href*="/video/BV"]'):
                    href = a.get("href", "")
                    m = re.search(r'/video/(BV[a-zA-Z0-9]+)', href)
                    if m:
                        bvid = m.group(1)
                        if bvid not in seen_bv:
                            seen_bv.add(bvid)
                            video_items.append({
                                "bvid": bvid,
                                "title": a.get("title") or a.get_text(strip=True)[:80],
                                "aid": None, "author": "", "mid": mid, "created": 0,
                            })
                print(f"    DOM回退: {len(video_items)} 条视频")
            except Exception as e:
                print(f"    DOM回退失败: {e}")

        print(f"    视频总计: {len(video_items)} 条")

        # ── 2. 专栏列表：渐进式重试 + DOM回退 ──
        print("  发现专栏列表...")
        article_retry_delays = [2, 4, 7]
        for attempt in range(len(article_retry_delays) + 1):
            if content_types and "article" not in content_types:
                break  # 只抓其他类型时跳过专栏发现
            if len(article_items) >= 3:
                break
            try:
                if attempt > 0:
                    w = article_retry_delays[attempt - 1] + random.uniform(0, 2)
                    print(f"    专栏重试 {attempt+1}, 等待 {w:.0f}s...")
                    time.sleep(w)
                page.goto(f"https://space.bilibili.com/{mid}/article",
                          wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                _slow_scroll(page, steps=8, step_px=400, delay_ms=700)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"    专栏页异常: {e}")
        print(f"    专栏API: {len(article_items)} 条")

        # DOM回退专栏
        if not (content_types and "article" not in content_types) and len(article_items) < 3:
            print("    尝试 DOM 回退提取专栏...")
            try:
                from bs4 import BeautifulSoup
                page.goto(f"https://space.bilibili.com/{mid}/article", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                for _ in range(10):
                    page.evaluate("window.scrollBy(0, 500)")
                    page.wait_for_timeout(700)
                soup = BeautifulSoup(page.content(), "html.parser")
                seen_cv = set()
                for a in soup.select('a[href*="/read/cv"]'):
                    href = a.get("href", "")
                    m = re.search(r'/read/cv(\d+)', href)
                    if m:
                        cv_id = m.group(1)
                        if cv_id not in seen_cv:
                            seen_cv.add(cv_id)
                            article_items.append({"id": cv_id, "title": a.get_text(strip=True)[:80], "author_name": "", "publish_time": 0})
                print(f"    DOM回退: {len(article_items)} 条专栏")
            except Exception as e:
                print(f"    DOM回退失败: {e}")
        print(f"    专栏总计: {len(article_items)} 条")

        # 构建视频条目
        for v in video_items:
            bvid = v.get("bvid", "")
            if bvid:
                all_items.append({
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "title": v.get("title", ""),
                    "content_type": "video",
                    "published_at": _ts_to_iso(v.get("created", 0)),
                    "author_name": v.get("author", "") or author_name,
                    "author_mid": str(v.get("mid", mid)),
                    "aid": v.get("aid"), "bvid": bvid,
                })

        # 构建专栏条目
        for art in article_items:
            cv_id = art.get("id")
            if cv_id:
                all_items.append({
                    "url": f"https://www.bilibili.com/read/cv{cv_id}",
                    "title": art.get("title", ""),
                    "content_type": "article",
                    "published_at": _ts_to_iso(art.get("publish_time", 0)),
                    "author_name": art.get("author_name", "") or author_name,
                    "author_mid": str(art.get("author", {}).get("mid", mid)),
                    "cv_id": cv_id,
                })

        # ── 3. 动态/opus列表：渐进式重试 + DOM回退 ──
        print("  发现动态列表...")
        dyn_retry_delays = [2, 5, 8, 12, 20]
        dyn_urls = [
            f"https://space.bilibili.com/{mid}/dynamic",
            f"https://space.bilibili.com/{mid}?from=dynamic",
        ]
        for attempt in range(len(dyn_retry_delays) + 1):
            if len(dynamic_items) >= max(max_items // 2, 10):
                break
            url_idx = attempt % len(dyn_urls)
            try:
                if attempt > 0:
                    w = dyn_retry_delays[attempt - 1] + random.uniform(0, 3)
                    print(f"    动态重试 {attempt+1}, 等待 {w:.0f}s...")
                    time.sleep(w)
                page.goto(dyn_urls[url_idx], wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                for s in range(20):
                    page.evaluate("window.scrollBy(0, 600)")
                    page.wait_for_timeout(800 + random.randint(0, 300))
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"    动态页异常: {e}")
        print(f"    动态API: {len(dynamic_items)} 条")

        # DOM回退动态
        if len(dynamic_items) < 3:
            print("    尝试 DOM 回退提取动态...")
            try:
                from bs4 import BeautifulSoup
                page.goto(f"https://space.bilibili.com/{mid}/dynamic", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                for _ in range(15):
                    page.evaluate("window.scrollBy(0, 500)")
                    page.wait_for_timeout(800)
                soup = BeautifulSoup(page.content(), "html.parser")
                seen_opus = set()
                for a in soup.select('a[href*="/opus/"]'):
                    href = a.get("href", "")
                    m = re.search(r'/opus/(\d+)', href)
                    if m:
                        oid = m.group(1)
                        if oid not in seen_opus:
                            seen_opus.add(oid)
                            dynamic_items.append({"id_str": oid, "modules": {"module_author": {"name": ""}, "module_dynamic": {"desc": {"text": a.get_text(strip=True)[:80]}}}})
                print(f"    DOM回退: {len(dynamic_items)} 条")
            except Exception as e:
                print(f"    DOM回退失败: {e}")

        # 构建动态条目（API + DOM 结果统一处理）
        for dyn in dynamic_items:
            modules = dyn.get("modules", {})
            module_author = modules.get("module_author", {})
            module_dynamic = modules.get("module_dynamic", {})
            author_name_dyn = module_author.get("name", "") or author_name
            desc = module_dynamic.get("desc", {})
            text = (desc.get("text", "") if isinstance(desc, dict) else str(desc))[:80]
            id_str = dyn.get("id_str", "") or dyn.get("extend", {}).get("id_str", "") or str(dyn.get("id", ""))
            if id_str:
                url_opus = f"https://www.bilibili.com/opus/{id_str}" if not id_str.startswith("http") else id_str
                all_items.append({
                    "url": url_opus, "title": text, "content_type": "opus",
                    "published_at": None, "author_name": author_name_dyn or author_name,
                    "author_mid": mid, "dynamic_id": id_str,
                })
        print(f"    动态总计: {len(dynamic_items)} 条")

        browser.close()

    # ── 去重 ──
    seen = set()
    unique = []
    for item in all_items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    # ── 内容类型过滤（如只抓动态） ──
    if content_types:
        ct_set = set(content_types)
        unique = [x for x in unique if x.get("content_type") in ct_set]

    # ── 优先级截取：动态占 1/2，其余视频+专栏填满 ──
    opus_items = [x for x in unique if x.get("content_type") == "opus"]
    other_items = [x for x in unique if x.get("content_type") != "opus"]
    opus_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    other_items.sort(key=lambda x: x.get("published_at") or "", reverse=True)

    opus_target = max(max_items // 2, min(len(opus_items), max_items))
    other_target = max_items - opus_target

    result = opus_items[:opus_target] + other_items[:other_target]
    # 按时间重新排序保持一致性
    result.sort(key=lambda x: x.get("published_at") or "", reverse=True)

    opus_got = sum(1 for x in result if x.get("content_type") == "opus")
    print(f"  [OK] 总计 {len(unique)} 条 (视频{len(other_items)} + 动态{len(opus_items)}), 截取 {len(result)} 条 (动态{opus_got}/{opus_target}) (作者: {author_name})")
    return result


def _normalize_bilibili_url(url: str) -> str:
    """规范化 B 站 URL：去除跟踪参数、统一 opus 格式，用于跨批次对比去重。"""
    u = (url or "").strip()
    if "?" in u:
        u = u.split("?", 1)[0]
    u = u.rstrip("/")
    # 旧版动态链接 t.bilibili.com/{id} → 统一为 /opus/{id}
    m = re.search(r"t\.bilibili\.com/(\d+)", u)
    if m:
        return f"https://www.bilibili.com/opus/{m.group(1)}"
    return u


def _extract_mid_from_url(url: str) -> Optional[str]:
    """从B站空间URL提取mid。"""
    m = re.search(r"space\.bilibili\.com/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"mid=(\d+)", url)
    if m:
        return m.group(1)
    return None


def _detect_content_type(url: str) -> str:
    """从URL判断B站内容类型。"""
    if "/video/" in url or "bilibili.com/video/" in url:
        return "video"
    if "/opus/" in url or "t.bilibili.com/" in url:
        return "opus"
    if "/read/cv" in url:
        return "article"
    return "video"


def _extract_bvid(url: str) -> Optional[str]:
    """从B站视频URL提取bvid。"""
    m = re.search(r"/video/(BV[a-zA-Z0-9]+)", url)
    return m.group(1) if m else None


def _extract_dynamic_id(url: str) -> Optional[str]:
    """从B站动态/opus URL提取dynamic_id。"""
    m = re.search(r"t\.bilibili\.com/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/opus/(\d+)", url)
    return m.group(1) if m else None


def _extract_cv_id(url: str) -> Optional[str]:
    """从B站专栏URL提取cv_id。"""
    m = re.search(r"/read/cv(\d+)", url)
    return m.group(1) if m else None


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

def fetch_opus_comments(
    opus_id: str,
    max_comments: int = 50,
) -> List[Dict]:
    """抓取 B站 opus/动态 的评论（含子评论）。

    opus 评论使用 x/polymer/web-dynamic/v1/detail API，
    需要 Playwright 浏览器环境绕过风控。

    Returns:
        标准化评论列表 [{comment_id, author_name, author_id, text, picture_urls, like_count, is_pinned, sub_replies}]
    """
    from playwright.sync_api import sync_playwright

    comments = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**_build_launch_args())
            ctx = browser.new_context(
                user_agent=USER_AGENT, viewport={"width": 1366, "height": 768}, locale="zh-CN")
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            # 加载 opus 页面触发 detail API
            captured_data = []

            def _on_resp(resp):
                if "polymer/web-dynamic/v1/detail" in resp.url:
                    try:
                        body = resp.json()
                        if body.get("code") == 0:
                            captured_data.append(body.get("data", {}))
                    except Exception:
                        pass

            page.on("response", _on_resp)
            page.goto(f"https://www.bilibili.com/opus/{opus_id}", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            browser.close()

            # 从 detail 数据中提取评论
            for data in captured_data:
                card = data.get("card", data)
                replies = card.get("replies", [])
                for reply in replies[:max_comments]:
                    member = reply.get("member", {})
                    content = reply.get("content", {})
                    picture_urls = []
                    for pic in content.get("pictures", []):
                        img = pic.get("img_src") or pic.get("img_url") or ""
                        if img:
                            img = re.sub(r"@\d+w_\d+h", "", img)
                            picture_urls.append(img)

                    # 子评论
                    sub_replies_raw = reply.get("replies", [])
                    sub_comments = []
                    for sr in sub_replies_raw[:10]:
                        sr_member = sr.get("member", {})
                        sr_content = sr.get("content", {})
                        sub_comments.append({
                            "author_name": sr_member.get("uname", ""),
                            "author_id": str(sr_member.get("mid", "")),
                            "text": (sr_content.get("message") or "").strip(),
                        })

                    comments.append({
                        "comment_id": str(reply.get("rpid", "")),
                        "author_name": member.get("uname", ""),
                        "author_id": str(member.get("mid", "")),
                        "text": (content.get("message") or "").strip(),
                        "picture_urls": picture_urls,
                        "like_count": int(reply.get("like", 0)),
                        "is_pinned": bool(reply.get("is_pinned", False)),
                        "created_at": _ts_to_iso(reply.get("ctime", 0)),
                        "sub_replies": sub_comments,
                    })
    except Exception as e:
        print(f"    opus评论获取失败: {e}")

    return comments


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
                params={"type": comment_type, "oid": oid, "pn": page, "ps": 20, "sort": 1},
                headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"},
                timeout=15,
            )
            data = resp.json()
            code = data.get("code", -1)
            if code != 0:
                print(f"    [comment-api] code={code} msg={data.get('message','')}")
                break
            replies = data.get("data", {}).get("replies", [])
            if not replies:
                print(f"    [comment-api] 0 replies at page {page} (total={len(comments)})")
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

class BilibiliGarbagePageError(ValueError):
    """页面异常（登录墙 / 页面源码 / 空内容），不应写入数据集。"""


def crawl_one_bilibili_post(
    item: Dict,
    media_base_dir: Path,
    salt: str,
    collector: str,
    session: requests.Session,
    max_comments: int = 50,
    proxy: Optional[str] = None,
    storage_state: Optional[Dict] = None,
    profile: Optional[Dict] = None,
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

    profile = profile or _pick_browser_profile()

    url = item["url"]
    content_type = item.get("content_type", "video")
    author_name = item.get("author_name", "")
    author_mid = item.get("author_mid", "")

    print(f"  [{content_type}] {item.get('title', url)[:60]}...")

    # ── 1. 获取页面（opus 同时拦截评论数据）──
    opus_detail_data = None
    html = ""  # 初始化
    if content_type == "opus":
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**_build_launch_args(proxy))
                ctx = browser.new_context(
                    user_agent=profile["ua"],
                    viewport={"width": random.randint(1360, 1560), "height": random.randint(760, 900)},
                    locale="zh-CN", timezone_id="Asia/Shanghai",
                    storage_state=storage_state,
                )
                ctx.add_init_script(_build_fingerprint_script(profile))
                page = ctx.new_page()
                page.set_extra_http_headers(_browser_extra_headers(profile))

                def _on_opus_resp(resp):
                    nonlocal opus_detail_data
                    url_l = resp.url
                    # opus 评论来自 x/v2/reply/wbi/main 端点
                    if "x/v2/reply/wbi/main" in url_l or "polymer/web-dynamic/v1/detail" in url_l:
                        try:
                            body = resp.json()
                            if body.get("code") == 0:
                                opus_detail_data = body.get("data", {})
                                print(f"    [opus-api] code=0 replies={len(opus_detail_data.get('replies',[]))}")
                        except Exception:
                            pass
                page.on("response", _on_opus_resp)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                _human_think()
                _human_mouse_activity(page, 1400, 800)
                _human_scroll(page, target_steps=random.randint(2, 4), base_step=250)
                page.wait_for_timeout(random.randint(1000, 2500))
                html = page.content()
                browser.close()
        except Exception as e:
            print(f"    [ERR] 页面获取失败: {e}")
            return _error_record(url, author_name, author_mid, str(e), salt, collector)
    else:
        try:
            html = _fetch_page_playwright(url, proxy=proxy, storage_state=storage_state, profile=profile)
        except Exception as e:
            print(f"    [ERR] 页面获取失败: {e}")
            return _error_record(url, author_name, author_mid, str(e), salt, collector)

    # ── 2. BS4 提取 ──
    title = item.get("title") or ""
    clean_text = ""
    image_urls = []
    published_at = item.get("published_at")
    if not author_name:
        author_name = item.get("author_name") or ""

    try:
        extracted = extract_from_bilibili_html(html, content_type)
        if extracted:
            title = extracted.get("title") or title
            clean_text = extracted.get("clean_text", "") or clean_text
            image_urls = extracted.get("image_urls", []) or image_urls
            published_at = extracted.get("published_at") or published_at
            if not author_name:
                author_name = extracted.get("author_name") or ""
    except Exception as e:
        print(f"    [ERR] BS4提取失败: {e}")

    # ── 2.5 异常格式检测：登录墙 / 页面源码 / 空内容 → 跳过不保存 ──
    if extracted and extracted.get("is_garbage"):
        reason = extracted.get("garbage_reason", "unknown")
        print(f"    [GARBAGE] 页面异常({reason})，跳过: {url}")
        raise BilibiliGarbagePageError(f"页面异常({reason}): {url}")

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
    if content_type == "opus":
        # opus: 从页面加载时已拦截的 detail API 数据提取评论+子评论
        if opus_detail_data:
            replies = opus_detail_data.get("replies", [])
            for reply in replies[:max_comments]:
                member = reply.get("member") or {}
                content = reply.get("content") or {}
                comment_text = (content.get("message") or "").strip()
                sub_replies = reply.get("replies") or []
                for sub in sub_replies[:10]:
                    sub_member = sub.get("member") or {}
                    sub_content = sub.get("content") or {}
                    sub_text = (sub_content.get("message") or "").strip()
                    if sub_text:
                        comment_text += "\n  L [" + str(sub_member.get("uname", "")) + "]: " + sub_text
                comments.append({
                    "comment_id": stable_hash(str(reply.get("rpid", "")), salt, length=16),
                    "author_id": stable_hash(str(member.get("mid", "")), salt, length=24),
                    "text": comment_text,
                    "like_count": int(reply.get("like", 0)),
                    "is_pinned": bool(reply.get("is_pinned", False)),
                })
            print(f"    评论: {len(comments)} 条 (含子评论)")
        else:
            print(f"    未拦截到评论数据")
    else:
        # 视频/专栏使用 x/v2/reply API
        comment_type = _get_comment_type(content_type)
        oid = _get_oid(item, extracted, content_type, session)
        if oid and comment_type:
            print(f"    [comment] type={comment_type} oid={oid}")
            try:
                raw_comments = fetch_bilibili_comments(str(oid), comment_type, session, max_comments)
                for rc in raw_comments:
                    comment_text = rc["text"]
                    comment_pic_urls = rc.get("picture_urls", [])
                    if comment_pic_urls:
                        markers = "".join(f"<图片{i+1}>" for i in range(len(comment_pic_urls)))
                        comment_text = comment_text + " " + markers
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


def _get_oid(item: Dict, extracted: Dict, content_type: str, session: requests.Session) -> Optional[str]:
    """获取评论API所需的oid。视频用aid，专栏用cv_id，动态用dynamic_id。"""
    if content_type == "video":
        oid = extracted.get("aid") or item.get("aid") or ""
        # 如果 aid 缺失，通过 bvid 从 view API 获取
        if not oid:
            bvid = extracted.get("bvid") or item.get("bvid") or ""
            if bvid:
                try:
                    resp = session.get(
                        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                        headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"},
                        timeout=10)
                    data = resp.json()
                    oid = str(data.get("data", {}).get("aid") or "")
                    if oid:
                        print(f"    [aid] bvid={bvid} -> aid={oid}")
                except Exception:
                    pass
        return oid
    elif content_type == "article":
        return str(extracted.get("cv_id") or item.get("cv_id") or "")
    elif content_type == "opus":
        return str(extracted.get("dynamic_id") or item.get("dynamic_id") or "")
    return None


def _fetch_page_playwright(url: str, timeout: int = 30000,
                           proxy: Optional[str] = None,
                           storage_state: Optional[Dict] = None,
                           profile: Optional[Dict] = None) -> str:
    """Playwright获取页面HTML（含模拟真人：指纹+代理+Cookie+人类行为）。"""
    from playwright.sync_api import sync_playwright

    profile = profile or _pick_browser_profile()

    with sync_playwright() as p:
        browser = p.chromium.launch(**_build_launch_args(proxy))
        vw, vh = random.randint(1360, 1560), random.randint(760, 900)
        context = browser.new_context(
            user_agent=profile["ua"],
            viewport={"width": vw, "height": vh},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            storage_state=storage_state,
        )
        context.add_init_script(_build_fingerprint_script(profile))
        page = context.new_page()
        page.set_extra_http_headers(_browser_extra_headers(profile))

        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        _human_think(0.8, 2.2)
        _human_mouse_activity(page, vw, vh)
        _human_scroll(page, target_steps=random.randint(1, 3), base_step=200)
        page.wait_for_timeout(random.randint(600, 1800))
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
    parser = argparse.ArgumentParser(description="B站爬虫 — 抓取作者全部内容或指定URL列表")
    parser.add_argument("--url", default=None, help="B站作者空间URL 或 单条内容URL（与--input二选一）")
    parser.add_argument("--input", default=None, help="URL列表文件（每行一条），直接批量抓取")
    parser.add_argument("--max-items", type=int, default=80, help="最大抓取条数 (50-100)")
    parser.add_argument("--max-comments-per-post", type=int, default=50, help="每条帖子最大评论数")
    parser.add_argument("--output-dir", default="data/run_outputs", help="输出根目录")
    parser.add_argument("--output", default=None, help="指定输出JSONL文件路径（覆盖自动生成）")
    parser.add_argument("--media-dir", default=None, help="指定媒体目录（覆盖自动生成）")
    parser.add_argument("--collector", default="D", help="采集者标识")
    parser.add_argument("--no-images", action="store_true", help="跳过图片下载")
    parser.add_argument("--no-comments", action="store_true", help="跳过评论抓取")
    parser.add_argument("--terms-checked-at", default=None, help="条款检查日期")
    parser.add_argument("--proxy", default=None, help="HTTP/HTTPS代理地址 (如 http://127.0.0.1:7890)")
    parser.add_argument("--content-type", default=None,
                        help="只抓指定内容类型，逗号分隔，如 opus 只抓动态（video/article/opus）")
    parser.add_argument("--skip-existing", default=None,
                        help="现有数据集 JSONL 路径；已存在于其中的 URL（按 _collected.source_url 对比）不再抓取")
    parser.add_argument("--delay-min", type=float, default=2.0, help="抓取间隔最小秒数 (默认2.0)")
    parser.add_argument("--delay-max", type=float, default=5.0, help="抓取间隔最大秒数 (默认5.0)")
    parser.add_argument("--retry-rounds", type=int, default=3, help="失败重试轮数 (默认3轮)")
    parser.add_argument("--no-prewarm", action="store_true",
                        help="跳过 Cookie 预热（默认抓取前访问 bilibili 官网自动获取 Cookie）")
    args = parser.parse_args()

    if not args.url and not args.input:
        parser.error("必须提供 --url 或 --input")

    from dotenv import load_dotenv
    load_dotenv()

    from crawler_utils import get_salt, stable_hash, DEFAULT_OUTPUT_ROOT

    salt = get_salt()

    # ── 模拟真人：选随机指纹 + Cookie 预热（A 层，仅访问 B 站官网自动获取，不用本机 Cookie）──
    profile = _pick_browser_profile()
    storage_state = None
    if not args.no_prewarm:
        storage_state = prewarm_bilibili_cookie(proxy=args.proxy, profile=profile)

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
    print(f"[RUN DIR] {run_dir}")
    print(f"[MEDIA]   {media_base_dir}")

    # ── 构建 items 列表（记录空间页便于重试）──
    space_urls = []  # 空间页URL列表
    single_items = []

    if args.input:
        input_path = Path(args.input)
        urls_raw = [l.strip() for l in input_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        for u in urls_raw:
            if "space.bilibili.com" in u:
                space_urls.append(u)
            else:
                ct = _detect_content_type(u)
                single_items.append({
                    "url": u, "title": "", "content_type": ct,
                    "author_name": "", "author_mid": "",
                    "bvid": _extract_bvid(u) if ct == "video" else None,
                    "dynamic_id": _extract_dynamic_id(u) if ct == "opus" else None,
                    "cv_id": _extract_cv_id(u) if ct == "article" else None,
                })
        print(f"[INPUT] {len(space_urls)} 个空间页 + {len(single_items)} 条单URL")
    elif not ("space.bilibili.com" in args.url or "/space" in args.url):
        ct = _detect_content_type(args.url)
        single_items = [{"url": args.url, "title": "", "content_type": ct, "author_name": "", "author_mid": "",
                          "bvid": _extract_bvid(args.url) if ct == "video" else None,
                          "dynamic_id": _extract_dynamic_id(args.url) if ct == "opus" else None,
                          "cv_id": _extract_cv_id(args.url) if ct == "article" else None}]
        print(f"[SINGLE] {ct} | {args.url}")
    else:
        space_urls = [args.url]

    # ── 展开空间页（支持多轮重试）──
    content_types = None
    if args.content_type:
        content_types = [c.strip() for c in args.content_type.split(",") if c.strip()]
        print(f"[FILTER] 仅抓取内容类型: {content_types}")

    def expand_spaces(urls, round_label=""):
        items = []
        for u in urls:
            print(f"  [EXPAND{round_label}] {u}")
            try:
                expanded = discover_bilibili_posts(
                    u, max_items=args.max_items, proxy=args.proxy,
                    content_types=content_types,
                    storage_state=storage_state, profile=profile,
                )
                items.extend(expanded)
                print(f"    -> {len(expanded)} 条")
            except Exception as e:
                print(f"    -> 失败: {e}")
        return items

    items = expand_spaces(space_urls) + single_items

    # ── 增量去重：跳过已在现有数据集中的 URL（按 _collected.source_url 对比）──
    if args.skip_existing:
        existing_path = Path(args.skip_existing)
        if existing_path.exists():
            try:
                import json as _json
                _dec = _json.JSONDecoder()
                _raw = existing_path.read_text(encoding="utf-8-sig")
                _pos = 0
                existing_urls = set()
                while _pos < len(_raw):
                    while _pos < len(_raw) and _raw[_pos].isspace():
                        _pos += 1
                    if _pos >= len(_raw):
                        break
                    _obj, _pos = _dec.raw_decode(_raw, _pos)
                    _su = (_obj.get("_collected") or {}).get("source_url")
                    if _su:
                        existing_urls.add(_normalize_bilibili_url(str(_su)))
                before = len(items)
                items = [it for it in items
                         if _normalize_bilibili_url(it["url"]) not in existing_urls]
                print(f"[SKIP-EXISTING] 数据集 {len(existing_urls)} 个 URL；"
                      f"发现 {before} -> 过滤后 {len(items)} 条待抓")
            except Exception as e:
                print(f"[SKIP-EXISTING] 读取数据集失败（不启用跳过）: {e}")
        else:
            print(f"[SKIP-EXISTING] 数据集不存在，跳过去重: {existing_path}")

    if not items:
        print("未发现任何内容，退出。")
        return 1

    session = requests.Session()

    # 保存 URL 列表
    urls_file = run_dir / "urls.txt"
    with urls_file.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(f"{it['url']}\t{it.get('title','')}\t{it.get('author_name','')}\n")
    print(f"[URLS] {urls_file} ({len(items)} 条)")

    # ── 2. 多轮抓取：失败的重试 ──
    total_items = len(items)
    records_written = 0
    failed_items = list(items)  # 初始所有待抓（dict列表）
    skipped_garbage = []        # 页面异常跳过（登录墙/页面源码/空内容）
    seen_urls = set()

    for round_num in range(1, args.retry_rounds + 1):
        if not failed_items:
            break
        remaining = [it for it in failed_items if it["url"] not in seen_urls]
        if not remaining:
            break
        print(f"\n=== 第 {round_num}/{args.retry_rounds} 轮: 待抓取 {len(remaining)} 条 ===")

        new_failed = []
        for idx, item in enumerate(remaining, 1):
            # 已成功的跳过
            if item["url"] in seen_urls:
                continue

            url_short = item["url"].split("bilibili.com/")[-1][:50]
            print(f"\n--- [轮{round_num} {idx}/{len(remaining)}] {url_short} ---")
            try:
                record = crawl_one_bilibili_post(
                    item, media_base_dir, salt, args.collector, session,
                    max_comments=0 if args.no_comments else args.max_comments_per_post,
                    proxy=args.proxy, storage_state=storage_state, profile=profile,
                )
                with output_path.open("a", encoding="utf-8") as f:
                    if records_written > 0:
                        f.write("\n")
                    json.dump(record, f, ensure_ascii=False, indent=2)
                    f.write("\n")
                records_written += 1
                seen_urls.add(item["url"])
                print(f"  [OK] 已保存 (总{records_written})")
            except BilibiliGarbagePageError as ge:
                # 页面异常（登录墙/页面源码/空内容）：跳过，不再重试
                skipped_garbage.append(item)
                seen_urls.add(item["url"])
                print(f"  [SKIP] {str(ge)[:80]}")
            except Exception as e:
                new_failed.append(item)
                print(f"  [ERR] {str(e)[:80]}")

            delay = random.uniform(args.delay_min, args.delay_max)
            print(f"    等待 {delay:.1f}s...")
            time.sleep(delay)

        failed_items = new_failed

        # ── 空间页重展开：产出不足的账号重新发现 ──
        if space_urls and round_num < args.retry_rounds:
            space_counts = {u: 0 for u in space_urls}
            for it in items:
                mid = it.get("author_mid", "")
                if mid:
                    for su in space_urls:
                        if _extract_mid_from_url(su) == mid:
                            space_counts[su] += 1
                            break
            deficient = [su for su, cnt in space_counts.items() if cnt < 3]
            if deficient:
                print(f"\n  产出不足的空间页 ({len(deficient)}个)，重新展开...")
                new_expanded = expand_spaces(deficient, round_label=f" R{round_num}")
                if new_expanded:
                    existing_urls = seen_urls | {it["url"] for it in items}
                    new_count = 0
                    for ne in new_expanded:
                        if ne["url"] not in existing_urls:
                            failed_items.append(ne)
                            items.append(ne)
                            new_count += 1
                    print(f"    -> 新增 {new_count} 条")
                    total_items = len(items)  # 更新总数

        if failed_items and round_num < args.retry_rounds:
            wait = random.uniform(5, 15)
            print(f"\n  本轮 {len(failed_items)} 条失败，{wait:.0f}s 后重试...")
            time.sleep(wait)

    error_count = len(failed_items)
    print(f"\n{'='*60}")
    print(f"[DONE] 成功: {records_written}, 失败: {error_count}, 总计: {total_items}")
    if skipped_garbage:
        print(f"[GARBAGE] 页面异常跳过: {len(skipped_garbage)} 条（登录墙/页面源码/空内容）")
        garbage_urls = run_dir / "skipped_garbage_urls.txt"
        with garbage_urls.open("w", encoding="utf-8") as gf:
            for it in skipped_garbage:
                gf.write(f"{it['url']}\t{it.get('title', '')}\n")
        print(f"  已记录跳过清单: {garbage_urls}")
    print(f"  输出: {output_path}")
    print(f"  运行目录: {run_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

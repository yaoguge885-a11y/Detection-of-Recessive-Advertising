#!/usr/bin/env python3
"""修复爬虫产出的异常 JSON 数据。

处理已知的爬虫 bug：
  1. text 字段后 stray "],"   → 移除多余的 ]
  2. orphan media 片段缺失闭合 ]} → 补全并独立为合法 JSON 对象
  3. media 片段自动合并回所属帖子

用法：
  python data-tooling/annotation/repair_jsonl.py \
    --input data/run_outputs/bilibili_20260727_162733/anonymized_posts.jsonl \
    --output data/run_outputs/bilibili_20260727_162733/anonymized_posts_repaired.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List


def repair_and_load(input_path: Path) -> List[Dict]:
    """修复并加载 JSONL 文件。"""
    raw = input_path.read_text(encoding="utf-8-sig")

    # ── Fix 1: 移除 text 字段后的 stray ], ──
    raw = re.sub(r',\s*\n\s*\],\s*\n(\s*)"comments"', r',\n\1"comments"', raw)

    # ── Fix 2: orphan media 片段缺少闭合 ]} → 补全 ──
    raw = re.sub(
        r'(\{\s*"media":\s*\[.*?\})\s*\n(\s*"schema_version")',
        r'\1\n  ]\n}\n\n{\n\2',
        raw, flags=re.DOTALL
    )

    # ── 检测垃圾文本（抓取失败的页面源码/登录墙/乱码）──
    def _is_garbage(text: str) -> bool:
        if not text or len(text.strip()) < 10:
            return True
        mojibake = ["锟斤拷", "烫烫烫", "屯屯屯", "\ufffd"]
        if any(m in (text or "") for m in mojibake):
            return True
        js_html = ["window.__MIRROR_CONFIG__", "window.reportConfig",
                    "window.reportMsgObj", "vue-ssr-outlet",
                    "<!DOCTYPE html", "<html", "</script>", "</div>",
                    "function(", "=> {", "const ", "export default"]
        login = ["扫描二维码登录", "请使用\n哔哩哔哩客户端", "立即登录",
                  "忘记密码", "首次使用", "点我注册", "短信登录",
                  "密码登录", "扫码登录", "验证码", "滑块验证"]
        js_hits = sum(1 for m in js_html if m in (text or ""))
        login_hits = sum(1 for m in login if m in (text or ""))
        if js_hits + login_hits >= 2:
            return True
        if js_hits >= 3 or login_hits >= 3:
            return True
        stripped = re.sub(r'https?://\S+', '', text or "")
        stripped = re.sub(r'[\d,.\s]+', '', stripped)
        if len(stripped) < 20 and len(text or "") > 200:
            return True
        return False

    # ── Parse ──
    records = []
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    parse_errors = 0
    while idx < n:
        while idx < n and raw[idx] in " \t\n\r":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
            if isinstance(obj, dict):
                records.append(obj)
            idx = end
        except json.JSONDecodeError:
            parse_errors += 1
            next_brace = raw.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace

    # ── 分离帖子和 orphan media ──
    posts = []
    orphan_media: Dict[str, List[Dict]] = {}
    garbage_count = 0
    for obj in records:
        pid = obj.get("post_id", "")
        if pid:
            if _is_garbage(obj.get("text", "")):
                obj["_garbage_text"] = True
                garbage_count += 1
            posts.append(obj)
        elif "media" in obj and set(obj.keys()) <= {"media"}:
            for m in obj.get("media", []):
                if not isinstance(m, dict):
                    continue
                mid = m.get("media_id", "")
                match = re.match(r"media_(post_[a-f0-9]+)_\d+", mid)
                if match:
                    orphan_media.setdefault(match.group(1), []).append(m)

    # ── 合并 orphan media ──
    merged = 0
    if orphan_media:
        for post in posts:
            pid = post.get("post_id", "")
            if pid in orphan_media:
                existing = post.get("media", [])
                post["media"] = existing + orphan_media[pid]
                merged += 1

    print(f"  解析记录: {len(records)}")
    print(f"  有效帖子: {len(posts)}")
    print(f"  JSON 解析错误(已跳过): {parse_errors}")
    print(f"  Orphan media 合并: {merged} 帖")
    print(f"  垃圾文本检测: {garbage_count} 帖")
    return posts


def main():
    parser = argparse.ArgumentParser(description="修复爬虫产出的异常 JSON 数据")
    parser.add_argument("--input", required=True, help="输入 JSONL 文件")
    parser.add_argument("--output", required=True, help="输出修复后的 JSONL 文件")
    parser.add_argument("--drop-garbage", action="store_true",
                        help="丢弃垃圾文本帖子（默认保留并标记 _garbage_text）")
    args = parser.parse_args()

    ip = Path(args.input)
    op = Path(args.output)
    if not ip.exists():
        print(f"❌ 文件不存在: {ip}")
        sys.exit(1)

    print(f"📂 输入: {ip}")
    posts = repair_and_load(ip)
    print(f"📝 输出: {op}")

    if args.drop_garbage:
        posts = [p for p in posts if not p.get("_garbage_text")]
        print(f"  丢弃垃圾帖子后剩余: {len(posts)}")

    op.parent.mkdir(parents=True, exist_ok=True)
    with op.open("w", encoding="utf-8") as f:
        for post in posts:
            f.write(json.dumps(post, ensure_ascii=False) + "\n")

    print(f"✅ 完成，输出 {len(posts)} 条记录")


if __name__ == "__main__":
    main()

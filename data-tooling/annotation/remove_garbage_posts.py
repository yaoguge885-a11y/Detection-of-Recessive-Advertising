#!/usr/bin/env python3
"""删除抓取失败的异常帖子（页面源码/登录墙，无真实内容）。

判定特征（与 flet_annotator._is_garbage_text 一致）：
  - text 含 B 站页面 JS 源码特征：window.__MIRROR_CONFIG__ / window.reportMsgObj / vue-ssr-outlet
  - 或 text 含登录墙特征：扫描二维码登录 / 立即登录 / 短信登录 / 密码登录 / 点我注册 / 忘记密码 等

用法：
  python data-tooling/annotation/remove_garbage_posts.py \
    --input data/run_outputs/merged_20260728/anonymized_posts.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CST = timezone(timedelta(hours=8))

# 页面源码特征
_JS_MARKERS = [
    "window.__MIRROR_CONFIG__",
    "window.reportMsgObj",
    "window.reportConfig",
    "vue-ssr-outlet",
    "<!DOCTYPE html",
    "<html",
    "</script>",
    "</div>",
]
# 登录墙特征
_LOGIN_MARKERS = [
    "扫描二维码登录",
    "请使用\n哔哩哔哩客户端",
    "立即登录",
    "忘记密码",
    "首次使用",
    "点我注册",
    "短信登录",
    "密码登录",
    "扫码登录",
    "验证码",
    "滑块验证",
]


def is_garbage_text(text: str) -> bool:
    """判定文本是否为抓取失败的 B 站页面源码/登录墙（异常数据）。

    仅使用强特征（页面 JS 源码标记），避免误删正常讨论"登录/验证码"的
    真实文章（例如微信文章提到"密码登录""验证码"会被弱特征误判）。
    登录墙弱特征只在文本极短（<60 字符）时才采信。
    """
    if not text:
        return False
    if "window.__MIRROR_CONFIG__" in text:
        return True
    js_hits = sum(1 for m in _JS_MARKERS if m in text)
    if js_hits >= 2:
        return True
    if len(text.strip()) < 60:
        login_hits = sum(1 for m in _LOGIN_MARKERS if m in text)
        if login_hits >= 2:
            return True
    return False


def load_jsonl(path: Path) -> List[Dict]:
    raw = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    records = []
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
            nxt = raw.find("{", idx + 1)
            idx = nxt if nxt != -1 else n
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="删除抓取失败的异常帖子")
    parser.add_argument("--input", "-i", required=True, help="输入 JSONL 路径")
    parser.add_argument("--output", "-o", default=None, help="输出路径（默认原地写回）")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写回")
    parser.add_argument("--print-removed", action="store_true",
                        help="打印被删除帖子的 post_id（便于核对）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 输入不存在: {input_path}")
        sys.exit(1)

    records = load_jsonl(input_path)
    total = len(records)

    removed: List[Dict] = []
    kept: List[Dict] = []
    for rec in records:
        if is_garbage_text(str(rec.get("text", "") or "")):
            removed.append(rec)
        else:
            kept.append(rec)

    removed_platforms: Dict[str, int] = {}
    for rec in removed:
        plat = str(rec.get("platform", "?"))
        removed_platforms[plat] = removed_platforms.get(plat, 0) + 1

    print(f"📊 总记录: {total}")
    print(f"🗑  异常(抓取失败)帖子: {len(removed)}")
    print(f"  {removed_platforms}")
    print(f"✅ 保留: {len(kept)}")

    if args.print_removed:
        print("\n被删除 post_id:")
        for rec in removed:
            print(f"  {rec.get('post_id', '?')}  {str(rec.get('_collected', {}).get('source_url', ''))[:60]}")

    if args.dry_run:
        print("\n(dry-run，未写回)")
        return

    # 备份
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    backup = input_path.with_name(f"{input_path.name}.bak_garbage_{ts}")
    backup.write_bytes(input_path.read_bytes())
    print(f"\n📦 备份: {backup}")

    output_path = Path(args.output) if args.output else input_path
    with output_path.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"💾 已写回: {output_path}（{len(kept)}/{total} 条）")


if __name__ == "__main__":
    main()

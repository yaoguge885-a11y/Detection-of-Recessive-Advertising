#!/usr/bin/env python3
"""清理自动标注输出中引用已删除异常帖子的记录。

背景：anonymized_posts.jsonl 中删除了 714 条 B 站抓取失败（页面源码/登录墙）记录，
备份在 anonymized_posts.jsonl.bak_garbage_20260803_015119。
本脚本从备份提取这些 post_id，扫描 data/annotations/preannotated 下
auto_*/suggest_*/progress_* 等 jsonl，删除引用这些 post_id 的标注行。

用法：
  python data-tooling/annotation/cleanup_preannotated.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CST = timezone(timedelta(hours=8))

ROOT = Path(r"D:\projectsnew\Detection-of-Recessive-Advertising")
DATA_DIR = ROOT / "data" / "run_outputs" / "merged_20260728"
GARBAGE_BACKUP = DATA_DIR / "anonymized_posts.jsonl.bak_garbage_20260803_015119"
PREANNOTATED_DIR = ROOT / "data" / "annotations" / "preannotated"


def load_jsonl(path: Path) -> List[Dict]:
    raw = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    i = 0
    recs = []
    while i < len(raw):
        while i < len(raw) and raw[i] in " \t\n\r":
            i += 1
        if i >= len(raw):
            break
        try:
            obj, end = decoder.raw_decode(raw, i)
            if isinstance(obj, dict):
                recs.append(obj)
            i = end
        except json.JSONDecodeError:
            nxt = raw.find("{", i + 1)
            i = nxt if nxt != -1 else len(raw)
    return recs


def main() -> None:
    parser = argparse.ArgumentParser(description="清理预标注输出中的异常帖子引用")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写回")
    parser.add_argument("--garbage-backup", default=str(GARBAGE_BACKUP), help="垃圾备份文件")
    parser.add_argument("--dir", default=str(PREANNOTATED_DIR), help="预标注目录")
    args = parser.parse_args()

    backup = Path(args.garbage_backup)
    if not backup.exists():
        print(f"❌ 找不到垃圾备份: {backup}")
        sys.exit(1)

    # 1. 从备份提取被删垃圾帖子的 post_id（该备份是删除前的完整文件）
    garbage_records = load_jsonl(backup)
    garbage_ids = set()
    for rec in garbage_records:
        t = str(rec.get("text", "") or "")
        if "window.__MIRROR_CONFIG__" in t:
            garbage_ids.add(str(rec.get("post_id", "")))
    print(f"🗑  垃圾帖子 post_id 集合: {len(garbage_ids)} 个")

    # 2. 扫描预标注目录
    files = sorted(Path(args.dir).glob("*.jsonl"))
    if not files:
        print("❌ 目录下无 jsonl 文件")
        sys.exit(1)

    total_removed = 0
    for f in files:
        recs = load_jsonl(f)
        kept = []
        removed_ids = []
        for r in recs:
            pid = str(r.get("post_id", ""))
            if pid in garbage_ids:
                removed_ids.append(pid)
            else:
                kept.append(r)
        if removed_ids:
            print(f"\n📄 {f.name}: {len(recs)} 条 -> 命中垃圾 {len(removed_ids)} 条 -> 保留 {len(kept)} 条")
            for pid in removed_ids[:10]:
                print(f"    - {pid}")
            if len(removed_ids) > 10:
                print(f"    ... 等 {len(removed_ids)} 条")
            total_removed += len(removed_ids)
        else:
            print(f"📄 {f.name}: {len(recs)} 条,无垃圾引用")

    print(f"\n总计命中垃圾引用: {total_removed} 条")

    if args.dry_run:
        print("\n(dry-run,未写回)")
        return

    if total_removed == 0:
        print("无需修改")
        return

    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    for f in files:
        recs = load_jsonl(f)
        kept = [r for r in recs if str(r.get("post_id", "")) not in garbage_ids]
        if len(kept) == len(recs):
            continue
        # 备份
        bf = f.with_name(f"{f.name}.bak_garbage_{ts}")
        bf.write_bytes(f.read_bytes())
        # 写回
        with f.open("w", encoding="utf-8") as w:
            for r in kept:
                w.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"💾 {f.name}: 备份 {bf.name},写回 {len(kept)}/{len(recs)} 条")


if __name__ == "__main__":
    main()

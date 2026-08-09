#!/usr/bin/env python3
"""修复 anonymized_posts.json 中的 published_at 和 blogger_history_refs。

两步操作：
1. 从 text 中提取发布时间，补全缺失的 published_at
2. 按 blogger_id 分组、按 published_at 排序后，填入"同作者更早帖子"的 post_id

输出为新的 JSON 文件，不覆盖原始数据。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 日期提取
# ---------------------------------------------------------------------------
# 匹配 text 中常见的日期格式
DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
# 备用：ISO 格式
DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def extract_published_at(text: str) -> str | None:
    """从 text 前 300 字符中提取发布时间，返回 ISO-8601 字符串或 None。"""
    if not text:
        return None
    head = text[:300]

    # 优先匹配中文格式 "2026年04月27日"
    m = DATE_RE.search(head)
    if not m:
        m = DATE_ISO_RE.search(head)
    if not m:
        return None

    y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
    date_str = f"{y}-{mo}-{d}"

    # 尝试提取时间
    after_date = head[m.end() : m.end() + 20]
    tm = TIME_RE.search(after_date)
    if tm:
        hh, mm = tm.group(1).zfill(2), tm.group(2).zfill(2)
        return f"{date_str}T{hh}:{mm}:00+08:00"

    return f"{date_str}T00:00:00+08:00"


# ---------------------------------------------------------------------------
# 时间解析
# ---------------------------------------------------------------------------
def parse_ts(raw: str | None) -> datetime | None:
    """解析 ISO-8601 时间戳。"""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def repair(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """修复 published_at 和 blogger_history_refs。

    返回 (修复后的 records, 统计信息)。
    """
    stats = {
        "total": len(records),
        "published_at_filled_from_text": 0,
        "published_at_still_missing": 0,
        "history_refs_filled": 0,
        "history_refs_still_empty": 0,
    }

    # ---- 步骤 1: 从 text 补全 published_at ----
    for r in records:
        if r.get("published_at"):
            continue
        extracted = extract_published_at(r.get("text", ""))
        if extracted:
            r["published_at"] = extracted
            stats["published_at_filled_from_text"] += 1
        else:
            stats["published_at_still_missing"] += 1

    # ---- 步骤 2: 按 blogger 分组，排序，填入 history_refs ----
    blogger_posts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        bid = r.get("blogger_id", "")
        ts = parse_ts(r.get("published_at"))
        if bid and ts:
            blogger_posts[bid].append(r)

    for bid, posts in blogger_posts.items():
        # 按发布时间排序
        posts.sort(key=lambda p: parse_ts(p["published_at"]) or datetime.min)

        for i, post in enumerate(posts):
            # 新 refs = 所有更早帖子的 post_id
            new_refs = [earlier["post_id"] for earlier in posts[:i]]
            post["blogger_history_refs"] = new_refs
            stats["history_refs_filled"] += 1

    # 统计仍未填充的
    for r in records:
        refs = r.get("blogger_history_refs")
        if not isinstance(refs, list) or len(refs) == 0:
            stats["history_refs_still_empty"] += 1

    return records, stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="修复 published_at 和 blogger_history_refs"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="输入 JSON 文件（默认 data/sheets/anonymized_posts.json）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 JSON 文件（默认 data/sheets/anonymized_posts_repaired.json）",
    )
    args = parser.parse_args()

    # 路径解析
    script_dir = Path(__file__).resolve().parent
    workspace = script_dir.parent
    input_path = args.input or workspace / "data" / "sheets" / "anonymized_posts.json"
    output_path = args.output or workspace / "data" / "sheets" / "anonymized_posts_repaired.json"

    if not input_path.is_file():
        print(f"错误：输入文件不存在 {input_path}", file=sys.stderr)
        return 1

    print(f"读取: {input_path}")
    records = json.loads(input_path.read_text(encoding="utf-8"))
    print(f"  已加载 {len(records)} 条记录")

    repaired, stats = repair(records)

    print()
    print("=== 修复统计 ===")
    print(f"  总帖数: {stats['total']}")
    print(f"  从 text 补全 published_at: {stats['published_at_filled_from_text']}")
    print(f"  仍缺 published_at: {stats['published_at_still_missing']}")
    print(f"  已填入 history_refs: {stats['history_refs_filled']}")
    print(f"  仍无 history_refs: {stats['history_refs_still_empty']}")

    output_path.write_text(
        json.dumps(repaired, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n已写入: {output_path}")
    print(f"文件大小: {output_path.stat().st_size / 1024 / 1024:.1f} MB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

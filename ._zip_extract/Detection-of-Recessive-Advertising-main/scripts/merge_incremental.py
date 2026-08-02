#!/usr/bin/env python3
"""增量合并脚本 —— 将新的采集批次合并进已存在的 merged 数据集。

本脚本【不清空、不重建】目标数据集：
  - 保留目标中已有记录，仅追加来源批次中 post_id 不重复的新记录
  - 只复制目标 media 目录中不存在的来源 media 子目录（跳过已存在）
  - 合并前自动备份目标 anonymized_posts.jsonl

用法：
  python scripts/merge_incremental.py `
    --source data/run_outputs/wechat_20260731_203808 `
    --target data/run_outputs/merged_20260728
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from jsonschema import Draft202012Validator, FormatChecker


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "data" / "schema" / "data_schema_v1_2.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def load_objects(path: Path) -> List[Dict]:
    """解析 JSONL（兼容 pretty 拼接 / 标准单行）。"""
    raw = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    length = len(raw)
    objects: List[Dict] = []
    while idx < length:
        while idx < length and raw[idx] in " \t\n\r":
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(raw, idx)
        objects.append(obj)
        idx = end
    return objects


def upgrade_to_v1_2(record: Dict) -> None:
    """防御性 schema 升级：1.1 -> 1.2（已是 1.2 则跳过）。"""
    if record.get("schema_version") == "1.2":
        return
    if record.get("schema_version") != "1.1":
        raise ValueError(
            f"unsupported schema_version: {record.get('schema_version')!r}"
        )
    record["schema_version"] = "1.2"
    for m in record.get("media", []):
        m.setdefault("source_url", None)
        m.setdefault("caption", None)
    record.setdefault("comments", [])
    record.setdefault("blogger_history_refs", [])


def validate_v1_2_record(record: Dict, *, source: str, index: int) -> None:
    errors = sorted(VALIDATOR.iter_errors(record), key=lambda error: list(error.path))
    if not errors:
        return
    first = errors[0]
    field = ".".join(str(part) for part in first.absolute_path) or "<root>"
    raise ValueError(
        f"{source} record {index} is not valid Schema v1.2 at {field}: "
        f"{first.message}"
    )


def copy_new_media(source_media: Path, target_media: Path) -> tuple[int, int, List[str]]:
    """复制来源 media 中不存在的子目录。返回 (新增, 跳过, 冲突列表)。"""
    if not source_media.is_dir():
        return 0, 0, []
    target_media.mkdir(parents=True, exist_ok=True)
    existing = {d for d in target_media.iterdir() if d.is_dir()}
    existing_names = {d.name for d in existing}

    copied = 0
    skipped = 0
    conflicts: List[str] = []
    for sub in source_media.iterdir():
        if not sub.is_dir():
            continue
        if sub.name in existing_names:
            skipped += 1
            continue
        try:
            shutil.copytree(sub, target_media / sub.name)
            copied += 1
        except Exception as exc:  # noqa: BLE001
            conflicts.append(f"{sub.name}: {exc}")
    return copied, skipped, conflicts


def main() -> int:
    parser = argparse.ArgumentParser(description="增量合并新批次到 merged 数据集")
    parser.add_argument("--source", required=True, action="append",
                        help="来源批次目录（可多次指定）")
    parser.add_argument("--target", required=True, help="目标 merged 目录")
    args = parser.parse_args()

    target = Path(args.target)
    target_jsonl = target / "anonymized_posts.jsonl"
    target_media = target / "media"

    # 1. 读取目标现有 post_id
    existing_ids: Set[str] = set()
    existing_records: List[Dict] = []
    if target_jsonl.exists():
        existing_records = load_objects(target_jsonl)
        existing_ids = {r.get("post_id", "") for r in existing_records}
    print(f"目标现有记录: {len(existing_records)}（唯一 post_id {len(existing_ids)}）")

    # 2. 收集来源新记录
    new_records: List[Dict] = []
    skipped_dupes = 0
    source_platforms: Counter = Counter()
    for src in args.source:
        src_dir = Path(src)
        jsonl_path = src_dir / "anonymized_posts.jsonl"
        if not jsonl_path.exists():
            print(f"[SKIP] {src_dir.name}: 无 anonymized_posts.jsonl")
            continue
        records = load_objects(jsonl_path)
        added = 0
        for index, record in enumerate(records, start=1):
            pid = record.get("post_id", "")
            if pid in existing_ids:
                skipped_dupes += 1
                continue
            upgrade_to_v1_2(record)
            validate_v1_2_record(record, source=src_dir.name, index=index)
            existing_ids.add(pid)
            new_records.append(record)
            source_platforms[record.get("platform", "unknown")] += 1
            added += 1
        print(f"[读取] {src_dir.name}: {len(records)} 条 -> 新增 {added} 条")

    if not new_records:
        print("没有需要合并的新记录。")
        return 0

    target.mkdir(parents=True, exist_ok=True)

    # 3. 备份目标 jsonl
    if target_jsonl.exists():
        backup = target_jsonl.with_name(
            f"anonymized_posts.jsonl.bak_{datetime.now():%Y%m%d_%H%M%S}"
        )
        shutil.copy2(target_jsonl, backup)
        print(f"已备份: {backup}")

    # 4. 追加写入（标准 JSONL）
    with target_jsonl.open("a", encoding="utf-8") as stream:
        for record in new_records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    total = len(existing_records) + len(new_records)
    print(f"追加 {len(new_records)} 条 -> 合并后共 {total} 条")

    # 5. 复制新 media
    for src in args.source:
        media_src = Path(src) / "media"
        copied, skipped, conflicts = copy_new_media(media_src, target_media)
        print(f"media {Path(src).name}: 新增 {copied} 个目录, 跳过 {skipped} 个")
        for c in conflicts[:10]:
            print(f"  [WARN] {c}")

    # 6. 汇总
    print("\n=== 合并完成 ===")
    print(f"合并前: {len(existing_records)} 条")
    print(f"新增:   {len(new_records)} 条（跳过重复 {skipped_dupes}）")
    print(f"合并后: {total} 条")
    for p, c in sorted(source_platforms.items()):
        print(f"  新增 {p}: {c}")
    print(f"输出: {target_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

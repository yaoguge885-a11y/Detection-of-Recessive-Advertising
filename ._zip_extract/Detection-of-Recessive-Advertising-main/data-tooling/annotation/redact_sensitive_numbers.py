#!/usr/bin/env python3
"""掩码替换敏感号码 —— 将已确认的手机号 / QQ 号等替换为部分掩码。

背景：privacy_scan 在 wechat_20260731_203808 批次中发现高风险命中：
  - 17520141361（手机号，2 条记录）
  - 275720377（QQ 群号，1 条记录）
本脚本对这些号码做部分掩码替换（保留首尾、中间打星），
并将命中记录的 privacy.contains_sensitive_data 置为 true，
避免其被 classify_record 误判为 public 层。

用法：
  python data-tooling/annotation/redact_sensitive_numbers.py \
    --input data/run_outputs/wechat_20260731_203808/anonymized_posts.jsonl
  python data-tooling/annotation/redact_sensitive_numbers.py \
    --input data/run_outputs/wechat_20260731_203808/anonymized_posts_dedup.jsonl

说明：
  - 默认内置已确认号码映射；可用 --numbers '{"号码": "掩码"}' 追加。
  - 默认原地写回（--output 可指定新路径）。
  - 兼容 pretty-printed 多行拼接与标准单行 JSONL 两种输入格式。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_MASKS: Dict[str, str] = {
    "17520141361": "175****1361",  # 手机号
    "275720377": "275****377",     # QQ 群号
}

PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")


def mask_phone(match: re.Match) -> str:
    num = match.group(0)
    return num[:3] + "****" + num[-4:]


def load_objects(path: Path) -> Tuple[List[Dict], bool]:
    """解析 JSONL（兼容 pretty 拼接 / 标准单行），返回 (对象列表, 是否 pretty 格式)。"""
    raw = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    length = len(raw)
    objects: List[Dict] = []
    pretty = False
    while idx < length:
        while idx < length and raw[idx] in " \t\n\r":
            idx += 1
        if idx >= length:
            break
        start = idx
        obj, end = decoder.raw_decode(raw, idx)
        objects.append(obj)
        if "\n" in raw[start:end]:
            pretty = True
        idx = end
    return objects, pretty


def apply_masks(text: str, masks: Dict[str, str], generic_phone: bool) -> str:
    for raw_num, masked in masks.items():
        text = text.replace(raw_num, masked)
    if generic_phone:
        text = PHONE_RE.sub(mask_phone, text)
    return text


def process_record(record: Dict, masks: Dict[str, str], generic_phone: bool) -> bool:
    """对单条记录做掩码，返回是否发生替换。"""
    changed = False

    for field in ("text", "title"):
        value = record.get(field)
        if isinstance(value, str) and value:
            new_value = apply_masks(value, masks, generic_phone)
            if new_value != value:
                record[field] = new_value
                changed = True

    for comment in record.get("comments") or []:
        if isinstance(comment, dict):
            value = comment.get("text")
            if isinstance(value, str) and value:
                new_value = apply_masks(value, masks, generic_phone)
                if new_value != value:
                    comment["text"] = new_value
                    changed = True

    for media in record.get("media") or []:
        if isinstance(media, dict):
            value = media.get("ref")
            if isinstance(value, str) and value:
                new_value = apply_masks(value, masks, generic_phone)
                if new_value != value:
                    media["ref"] = new_value
                    changed = True

    if changed:
        privacy = record.setdefault("privacy", {})
        privacy["anonymized"] = True
        privacy["contains_sensitive_data"] = True

    return changed


def write_objects(path: Path, objects: List[Dict], pretty: bool) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for i, obj in enumerate(objects):
            if i:
                stream.write("\n")
            if pretty:
                stream.write(json.dumps(obj, ensure_ascii=False, indent=2))
            else:
                stream.write(json.dumps(obj, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="掩码替换敏感号码（部分掩码）")
    parser.add_argument("--input", required=True, help="输入 JSONL 路径")
    parser.add_argument("--output", default=None, help="输出路径（默认原地覆盖输入）")
    parser.add_argument(
        "--numbers",
        default=None,
        help="附加号码映射 JSON，如 '{\"13800138000\": \"138****8000\"}'",
    )
    parser.add_argument(
        "--generic-phone",
        action="store_true",
        help="同时用正则掩码所有 11 位大陆手机号",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}")
        return 1

    masks = dict(DEFAULT_MASKS)
    if args.numbers:
        try:
            masks.update(json.loads(args.numbers))
        except json.JSONDecodeError as e:
            print(f"ERROR: --numbers 不是合法 JSON: {e}")
            return 1

    objects, pretty = load_objects(input_path)
    changed_ids: List[str] = []
    for record in objects:
        if process_record(record, masks, args.generic_phone):
            changed_ids.append(record.get("post_id", "?"))

    output_path = Path(args.output) if args.output else input_path
    write_objects(output_path, objects, pretty)

    print(f"📊 掩码替换完成:")
    print(f"   总记录:   {len(objects)}")
    print(f"   已掩码:   {len(changed_ids)} 条")
    for pid in changed_ids:
        print(f"     - {pid}")
    print(f"   输出:     {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

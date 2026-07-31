#!/usr/bin/env python3
"""合并数据集 PII 掩码 —— 基于 privacy_scan 发现的 high/critical 命中做类型化掩码。

掩码类型（已人工抽样复核判定）：
  - 手机号 / 邮箱地址 / 微信号 / QQ号 / 联系方式 / 银行卡号（疑似）→ 掩码
  - 物理地址 → 不掩码（抽样显示为 URL/文件路径/工作地点等内容标识，非个人地址）

行为：
  - 备份原文件为 <input>.bak_<时间戳>
  - 原地写回（--output 可指定新路径）
  - 命中记录 privacy.anonymized=True, contains_sensitive_data=True
  - 兼容 pretty 拼接 / 标准单行 JSONL
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# ── Windows GBK 控制台兼容 ──
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from privacy_scan import scan_record  # noqa: E402

CST = timezone(timedelta(hours=8))

# 需要掩码的命中类型（人工复核结论）
MASK_TYPES = {
    "手机号",
    "邮箱地址",
    "微信号",
    "QQ号",
    "联系方式",
    "银行卡号（疑似）",
}

# 保留的隐私字段（与 schema v1.2 privacy 一致）
_PRIVACY_KEYS = ("anonymized", "contains_sensitive_data")


def mask_phone(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) == 11:
        return digits[:3] + "****" + digits[-4:]
    if len(v) <= 6:
        return v[:2] + "***"
    return v[:3] + "***" + v[-3:]


def mask_email(v: str) -> str:
    if "@" in v:
        local, domain = v.rsplit("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "***" if local else "***"
        else:
            masked_local = local[0] + "***" + local[-1]
        return f"{masked_local}@{domain}"
    return mask_phone(v)


def mask_generic(v: str) -> str:
    v = str(v)
    if len(v) <= 4:
        return v[0] + "***"
    if len(v) <= 8:
        return v[:2] + "***" + v[-2:]
    return v[:4] + "****" + v[-4:]


def mask_by_type(v: str, typ: str) -> str:
    if typ == "手机号":
        return mask_phone(v)
    if typ == "邮箱地址":
        return mask_email(v)
    return mask_generic(v)


def _replace_in_text(text: str, old: str, new: str) -> str:
    # 只替换 old 首次出现的原始形态（大小写敏感）
    return text.replace(old, new)


def process_record(record: Dict) -> bool:
    """对单条记录按扫描发现掩码，返回是否变更。"""
    changed = False
    findings = scan_record(record)

    # 按字段分组命中
    by_field: Dict[str, List[Tuple[str, str]]] = {}
    for f in findings:
        if f.get("type") not in MASK_TYPES:
            continue
        if f.get("severity") not in ("high", "critical"):
            continue
        field = f.get("field", "")
        match = str(f.get("match", ""))
        if not match:
            continue
        by_field.setdefault(field, []).append((match, mask_by_type(match, f.get("type", ""))))

    # text / title
    for field in ("text", "title"):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        for old, new in by_field.get(field, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
        if changed and field == "text":
            record["text"] = value
        if field == "title":
            record["title"] = value

    # comments[i].text
    for i, c in enumerate(record.get("comments") or []):
        if not isinstance(c, dict):
            continue
        value = c.get("text")
        if not isinstance(value, str) or not value:
            continue
        fkey = f"comments[{i}].text"
        for old, new in by_field.get(fkey, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
        if changed:
            c["text"] = value

    # media[i].ref
    for i, m in enumerate(record.get("media") or []):
        if not isinstance(m, dict):
            continue
        value = m.get("ref")
        if not isinstance(value, str) or not value:
            continue
        fkey = f"media[{i}].ref"
        for old, new in by_field.get(fkey, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
        if changed:
            m["ref"] = value

    if changed:
        privacy = record.setdefault("privacy", {})
        privacy["anonymized"] = True
        privacy["contains_sensitive_data"] = True
        # 清理可能存在的 schema 不允许的额外字段
        for k in list(privacy.keys()):
            if k not in _PRIVACY_KEYS:
                privacy.pop(k, None)

    return changed


def load_objects(path: Path) -> Tuple[List[Dict], bool]:
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
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            nxt = raw.find("{", idx + 1)
            idx = nxt if nxt != -1 else length
            continue
        objects.append(obj)
        if "\n" in raw[start:end]:
            pretty = True
        idx = end
    return objects, pretty


def write_objects(path: Path, objects: List[Dict], pretty: bool) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for i, obj in enumerate(objects):
            if i:
                stream.write("\n")
            if pretty:
                stream.write(json.dumps(obj, ensure_ascii=False, indent=2))
            else:
                stream.write(json.dumps(obj, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="合并数据集 PII 掩码（基于 privacy_scan）")
    parser.add_argument("--input", required=True, help="输入 JSONL 路径")
    parser.add_argument("--output", default=None, help="输出路径（默认原地写回）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 输入不存在: {input_path}")
        sys.exit(1)

    # 备份
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    backup = input_path.with_name(f"{input_path.name}.bak_pii_{ts}")
    backup.write_bytes(input_path.read_bytes())
    print(f"📦 备份: {backup}")

    objects, pretty = load_objects(input_path)
    total = len(objects)
    changed_records = 0
    total_replaced = 0

    for record in objects:
        before = json.dumps(record, ensure_ascii=False)
        if process_record(record):
            after = json.dumps(record, ensure_ascii=False)
            total_replaced += sum(
                1 for a, b in zip(before, after) if a != b
            ) // 2 if before != after else 0
            changed_records += 1

    print(f"📊 记录总数: {total}")
    print(f"🔧 发生掩码的记录: {changed_records}")

    output_path = Path(args.output) if args.output else input_path
    write_objects(output_path, objects, pretty)
    print(f"💾 已写回: {output_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""合并数据集 PII 掩码 —— 基于 privacy_scan 发现的 high/critical 命中做类型化掩码。

默认掩码类型（已人工抽样复核判定）：
  - 手机号 / 邮箱地址 / 微信号 / QQ号 / 联系方式 / 银行卡号（疑似）→ 掩码
  - 物理地址 → 默认不掩码；提供人工审批文件且记录被判定为 redact 时才掩码

行为：
  - 原地写回时备份原文件为 <input>.bak_<时间戳>
  - 原地写回（--output 可指定新路径）
  - --approval-file 可把处理范围限制为人工审批中的 redact 记录
  - --report 可输出不含敏感明文的逐记录前后扫描摘要
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
    "固定电话",
    "邮箱地址",
    "微信号",
    "QQ号",
    "UID/账号标识",
    "联系方式",
    "银行卡号（疑似）",
}
APPROVAL_MASK_TYPES = MASK_TYPES | {
    "物理地址",
    "Base64 长字符串（疑似密钥）",
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
    if typ == "物理地址":
        return "[PHYSICAL_ADDRESS_REDACTED]"
    if typ == "Base64 长字符串（疑似密钥）":
        return "[SECRET_REDACTED]"
    return mask_generic(v)


def _replace_in_text(text: str, old: str, new: str) -> str:
    # 只替换 old 首次出现的原始形态（大小写敏感）
    return text.replace(old, new)


def process_record(record: Dict, mask_types: set[str] = MASK_TYPES) -> bool:
    """对单条记录按扫描发现掩码，返回是否变更。"""
    changed = False
    findings = scan_record(record)

    # 按字段分组命中
    by_field: Dict[str, List[Tuple[str, str]]] = {}
    for f in findings:
        if f.get("type") not in mask_types:
            continue
        if f.get("severity") not in ("medium", "high", "critical"):
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
        field_changed = False
        for old, new in by_field.get(field, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
                field_changed = True
        if field_changed:
            record[field] = value

    # comments[i].text
    for i, c in enumerate(record.get("comments") or []):
        if not isinstance(c, dict):
            continue
        value = c.get("text")
        if not isinstance(value, str) or not value:
            continue
        fkey = f"comments[{i}].text"
        field_changed = False
        for old, new in by_field.get(fkey, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
                field_changed = True
        if field_changed:
            c["text"] = value

    # media[i].ref
    for i, m in enumerate(record.get("media") or []):
        if not isinstance(m, dict):
            continue
        value = m.get("ref")
        if not isinstance(value, str) or not value:
            continue
        fkey = f"media[{i}].ref"
        field_changed = False
        for old, new in by_field.get(fkey, []):
            if old in value and old != new:
                value = _replace_in_text(value, old, new)
                changed = True
                field_changed = True
        if field_changed:
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


def load_redact_scope(path: Path) -> Dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    excluded = payload.get("excluded", [])
    if not isinstance(excluded, list):
        raise ValueError("approval file field 'excluded' must be a list")
    result: Dict[str, str] = {}
    for item in excluded:
        if not isinstance(item, dict) or item.get("decision") != "redact":
            continue
        post_id = str(item.get("post_id", "")).strip()
        if not post_id:
            raise ValueError("redact entry missing post_id")
        if post_id in result:
            raise ValueError(f"duplicate redact post_id: {post_id}")
        result[post_id] = str(item.get("reason", ""))
    return result


def summarize_findings(findings: List[Dict]) -> List[Dict]:
    """Return an audit-safe summary without cleartext matches."""
    return [
        {
            "field": str(item.get("field", "")),
            "type": str(item.get("type", "")),
            "severity": str(item.get("severity", "")),
            "match_length": len(str(item.get("match", ""))),
        }
        for item in findings
        if item.get("severity") != "low"
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="合并数据集 PII 掩码（基于 privacy_scan）")
    parser.add_argument("--input", required=True, help="输入 JSONL 路径")
    parser.add_argument("--output", default=None, help="输出路径（默认原地写回）")
    parser.add_argument(
        "--approval-file",
        default=None,
        help="人工审批 JSON；提供后仅处理 excluded 中 decision=redact 的 post_id",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="输出不含敏感明文的 JSON 审计摘要",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 输入不存在: {input_path}")
        sys.exit(1)

    output_path = Path(args.output) if args.output else input_path
    if output_path.exists() and output_path.resolve() != input_path.resolve():
        print(f"❌ 拒绝覆盖已存在的输出: {output_path}")
        sys.exit(1)

    redact_scope: Dict[str, str] | None = None
    if args.approval_file:
        approval_path = Path(args.approval_file)
        if not approval_path.exists():
            print(f"❌ 审批文件不存在: {approval_path}")
            sys.exit(1)
        redact_scope = load_redact_scope(approval_path)

    # 仅原地写回时备份；显式输出工作副本时不改动输入目录。
    if output_path.resolve() == input_path.resolve():
        ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
        backup = input_path.with_name(f"{input_path.name}.bak_pii_{ts}")
        backup.write_bytes(input_path.read_bytes())
        print(f"📦 备份: {backup}")

    objects, pretty = load_objects(input_path)
    total = len(objects)
    changed_records = 0
    total_replaced = 0
    seen_ids = set()
    report_rows = []

    for record in objects:
        post_id = str(record.get("post_id", ""))
        if redact_scope is not None and post_id not in redact_scope:
            continue
        seen_ids.add(post_id)
        before_findings = scan_record(record)
        before = json.dumps(record, ensure_ascii=False)
        changed = process_record(
            record,
            APPROVAL_MASK_TYPES if redact_scope is not None else MASK_TYPES,
        )
        if changed:
            after = json.dumps(record, ensure_ascii=False)
            total_replaced += sum(
                1 for a, b in zip(before, after) if a != b
            ) // 2 if before != after else 0
            changed_records += 1
        after_findings = scan_record(record)
        reason = redact_scope.get(post_id, "") if redact_scope is not None else ""
        report_rows.append({
            "post_id": post_id,
            "changed": changed,
            "media_risk": "; media:" in reason,
            "before_non_low": summarize_findings(before_findings),
            "after_non_low": summarize_findings(after_findings),
        })

    if redact_scope is not None:
        missing_ids = sorted(set(redact_scope) - seen_ids)
        if missing_ids:
            print(f"❌ 审批中的 redact post_id 未在输入中找到: {', '.join(missing_ids)}")
            sys.exit(1)

    print(f"📊 记录总数: {total}")
    print(f"🔧 发生掩码的记录: {changed_records}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_objects(output_path, objects, pretty)
    print(f"💾 已写回: {output_path}")

    if args.report:
        report_path = Path(args.report)
        if report_path.exists():
            print(f"❌ 拒绝覆盖已存在的报告: {report_path}")
            sys.exit(1)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        ready_count = sum(
            1 for row in report_rows
            if row["changed"] and not row["media_risk"] and not row["after_non_low"]
        )
        payload = {
            "status": "draft_requires_B_confirmation",
            "input": str(input_path),
            "output": str(output_path),
            "approval_file": str(args.approval_file or ""),
            "target_records": len(report_rows),
            "changed_records": changed_records,
            "ready_for_B_confirmation": ready_count,
            "items": report_rows,
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"🧾 审计摘要: {report_path}")


if __name__ == "__main__":
    main()

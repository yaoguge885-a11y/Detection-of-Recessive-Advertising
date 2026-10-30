#!/usr/bin/env python3
"""Interactive human review for a fixed privacy-boundary sample."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from privacy_scan import scan_record


CST = timezone(timedelta(hours=8))
DECISIONS = {
    "e": "exclude",
    "r": "redact_then_reconsider",
    "f": "false_positive_safe",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            post_id = str(row.get("post_id", ""))
            if not post_id:
                raise ValueError(f"line {line_number}: missing post_id")
            if post_id in rows:
                raise ValueError(f"line {line_number}: duplicate post_id {post_id}")
            rows[post_id] = row
    return rows


def save_review(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_field_text(record: dict[str, Any], field: str) -> str:
    if field in {"text", "title"}:
        return str(record.get(field) or "")
    match = re.fullmatch(r"comments\[(\d+)]\.text", field)
    if match:
        index = int(match.group(1))
        comments = record.get("comments") or []
        if 0 <= index < len(comments) and isinstance(comments[index], dict):
            return str(comments[index].get("text") or "")
    return ""


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def context_for(text: str, match_text: str, radius: int = 90) -> str:
    normalized = compact(text)
    needle = compact(match_text)
    if not normalized:
        return "（字段为空）"
    index = normalized.lower().find(needle.lower()) if needle else -1
    if index < 0:
        return normalized[: radius * 2]
    start = max(0, index - radius)
    end = min(len(normalized), index + len(needle) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized) else ""
    return prefix + normalized[start:index] + "【" + normalized[index:index + len(needle)] + "】" + normalized[index + len(needle):end] + suffix


def finding_digest(finding: dict[str, Any]) -> str:
    return hashlib.sha256(str(finding.get("match", "")).encode("utf-8")).hexdigest()


def review_reason(decision: str) -> str:
    if decision == "exclude":
        prompt = "补充原因（直接回车=确认保守排除）："
        return input(prompt).strip() or "确认保守排除"
    if decision == "redact_then_reconsider":
        while True:
            reason = input("请说明需要脱敏的内容：").strip()
            if reason:
                return reason
    while True:
        reason = input("请说明为什么是误报且可以放行：").strip()
        if reason:
            return reason


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reviewer", default="A")
    parser.add_argument("--check", action="store_true", help="只检查输入，不进入交互")
    args = parser.parse_args()

    rows = load_jsonl_by_id(args.dataset.resolve())
    sample_payload = load_json(args.sample.resolve())
    sample_ids = [str(post_id) for post_id in sample_payload.get("post_ids", [])]
    missing = [post_id for post_id in sample_ids if post_id not in rows]
    if missing:
        raise ValueError(f"sample contains missing post_ids: {missing[:5]}")

    if args.check:
        print(json.dumps({
            "dataset_records": len(rows),
            "sample_records": len(sample_ids),
            "records_with_findings": sum(bool(scan_record(rows[post_id])) for post_id in sample_ids),
            "status": "ready",
        }, ensure_ascii=False, indent=2))
        return 0

    if args.output.exists():
        result = load_json(args.output)
        if str(result.get("reviewer")) != args.reviewer:
            raise ValueError("existing review belongs to a different reviewer")
    else:
        result = {
            "status": "in_progress",
            "reviewer": args.reviewer,
            "scope": "M1 privacy boundary sample human review",
            "started_at": datetime.now(CST).isoformat(),
            "completed_at": None,
            "sample_size": len(sample_ids),
            "decisions": [],
        }

    completed = {str(item["post_id"]) for item in result.get("decisions", [])}
    pending = [post_id for post_id in sample_ids if post_id not in completed]

    print("=" * 72)
    print("M1 隐私边界样本：A 人工复核")
    print(f"总计 {len(sample_ids)} 条；已完成 {len(completed)}；待复核 {len(pending)}")
    print("选择：[e] 保守排除（建议） / [r] 脱敏后再评估 / [f] 确认误报可放行")
    print("      [s] 暂时跳过 / [q] 保存退出")
    print("复核结果只保存 post_id、判断、理由和命中哈希，不保存明文上下文。")
    print("=" * 72)

    for post_id in pending:
        record = rows[post_id]
        findings = scan_record(record)
        position = sample_ids.index(post_id) + 1
        print("\n" + "-" * 72)
        print(f"[{position}/{len(sample_ids)}] {post_id}")
        print(f"平台：{record.get('platform')}  标题：{compact(str(record.get('title') or '（无标题）'))[:140]}")
        print(f"原始敏感标记：{(record.get('privacy') or {}).get('contains_sensitive_data')}")
        if not findings:
            print("规则命中：无；本条因原始 privacy 标记进入边界样本。")
            print("正文预览：" + compact(str(record.get("text") or ""))[:220])
        else:
            print(f"规则命中：{len(findings)} 处")
            for number, finding in enumerate(findings, 1):
                field = str(finding.get("field", ""))
                print(
                    f"  {number}. [{finding.get('severity')}] {finding.get('type')} "
                    f"字段={field}"
                )
                print("     上下文：" + context_for(get_field_text(record, field), str(finding.get("match", ""))))

        while True:
            choice = input("\n你的判断 [e/r/f/s/q]：").strip().lower()
            if choice in {*DECISIONS, "s", "q"}:
                break
            print("请输入 e、r、f、s 或 q。")
        if choice == "q":
            save_review(args.output, result)
            print(f"已保存：{args.output.resolve()}")
            return 0
        if choice == "s":
            print("本条暂时跳过。")
            continue

        decision = DECISIONS[choice]
        reason = review_reason(decision)
        result["decisions"].append(
            {
                "post_id": post_id,
                "decision": decision,
                "reason": reason,
                "finding_types": sorted({str(item.get("type")) for item in findings}),
                "finding_hashes": [finding_digest(item) for item in findings],
                "reviewed_at": datetime.now(CST).isoformat(),
            }
        )
        save_review(args.output, result)
        print("✓ 已记录并自动保存")

    completed = {str(item["post_id"]) for item in result.get("decisions", [])}
    if len(completed) == len(sample_ids):
        result["status"] = "completed"
        result["completed_at"] = datetime.now(CST).isoformat()
        save_review(args.output, result)
        print("\n✅ A 的 30 条隐私边界样本已全部复核完成。")
    else:
        save_review(args.output, result)
        print(f"\n仍有 {len(sample_ids) - len(completed)} 条未完成，可重新运行继续。")
    print(f"结果：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

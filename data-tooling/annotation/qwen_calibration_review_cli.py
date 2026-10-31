#!/usr/bin/env python3
"""Interactive human reasonableness review for the fixed Qwen calibration sample."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CST = timezone(timedelta(hours=8))
LABELS = ("明广", "暗广", "非广", "out_of_scope")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def ask_note(prompt: str, required: bool) -> str:
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("该项需要填写简短原因。")


def ask_corrected_label() -> str:
    print("修正后的标签：")
    for index, label in enumerate(LABELS):
        print(f"  [{index}] {label}")
    while True:
        value = input("输入编号 0-3：").strip()
        if value.isdigit() and 0 <= int(value) < len(LABELS):
            return LABELS[int(value)]
        print("请输入 0、1、2 或 3。")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    source = load_json(args.input.resolve())
    items = list(source.get("items") or [])
    if source.get("model") != "qwen3.5:9b-q4_K_M":
        raise ValueError("calibration sample does not use the required model tag")
    if len(items) != 20:
        raise ValueError(f"expected 20 review items, got {len(items)}")
    post_ids = [str(item.get("post_id")) for item in items]
    if len(set(post_ids)) != len(post_ids) or any(not item for item in post_ids):
        raise ValueError("review sample contains missing or duplicate post_id")

    if args.check:
        print(json.dumps({
            "status": "ready",
            "model": source.get("model"),
            "sample_size": len(items),
            "reviewer": args.reviewer,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.output.exists():
        result = load_json(args.output.resolve())
        if result.get("reviewer") != args.reviewer:
            raise ValueError("existing output belongs to another reviewer")
    else:
        result = {
            "status": "in_progress",
            "reviewer": args.reviewer,
            "model": source.get("model"),
            "scope": "M1 Qwen calibration human reasonableness review",
            "started_at": datetime.now(CST).isoformat(),
            "completed_at": None,
            "sample_size": len(items),
            "decisions": [],
        }

    completed = {str(item["post_id"]) for item in result.get("decisions", [])}
    pending = [item for item in items if str(item["post_id"]) not in completed]

    print("=" * 76)
    print("M1 Qwen 9B 校准：20 条人工合理性抽查")
    print(f"复核人：{args.reviewer}；已完成 {len(completed)}；待复核 {len(pending)}")
    print("[y] 建议合理  [n] 建议不合理  [u] 无法判断  [s] 跳过  [q] 保存退出")
    print("本复核不产生 Gold 标签，也不用于正式 κ。")
    print("=" * 76)

    for item in pending:
        post = item.get("post") or {}
        suggestion = item.get("model_output") or {}
        index = int(item.get("index") or 0)
        print("\n" + "-" * 76)
        print(f"[{index}/20] {item['post_id']}  tier={item.get('tier')}")
        print(f"平台：{post.get('platform')}")
        print("标题：" + compact(post.get("title"))[:240])
        print("正文：" + compact(post.get("text"))[:1800])
        comments = post.get("comments") or []
        if comments:
            preview = " / ".join(compact(comment.get("text"))[:180] for comment in comments[:3])
            print("评论：" + preview)
        print("\nQwen 建议：")
        print(f"  标签={suggestion.get('label')}  置信度={suggestion.get('confidence')}")
        print("  证据代码=" + ",".join(suggestion.get("evidence_codes") or []))
        for evidence in suggestion.get("evidence") or []:
            print("  - " + compact(evidence)[:300])
        print("  理由：" + compact(suggestion.get("reasoning"))[:500])

        while True:
            choice = input("\n你的判断 [y/n/u/s/q]：").strip().lower()
            if choice in {"y", "n", "u", "s", "q"}:
                break
            print("请输入 y、n、u、s 或 q。")
        if choice == "q":
            save_json(args.output, result)
            print(f"已保存：{args.output.resolve()}")
            return 0
        if choice == "s":
            print("本条暂时跳过。")
            continue

        decision: dict[str, Any] = {
            "post_id": item["post_id"],
            "model_label": suggestion.get("label"),
            "model_confidence": suggestion.get("confidence"),
            "reviewed_at": datetime.now(CST).isoformat(),
        }
        if choice == "y":
            decision.update({
                "reasonable": True,
                "corrected_label": None,
                "notes": ask_note("补充说明（可直接回车）：", required=False),
            })
        elif choice == "n":
            decision.update({
                "reasonable": False,
                "corrected_label": ask_corrected_label(),
                "notes": ask_note("请简述不合理原因：", required=True),
            })
        else:
            decision.update({
                "reasonable": None,
                "corrected_label": None,
                "notes": ask_note("请简述无法判断的原因：", required=True),
            })
        result["decisions"].append(decision)
        save_json(args.output, result)
        print("✓ 已记录并自动保存")

    completed = {str(item["post_id"]) for item in result.get("decisions", [])}
    if len(completed) == len(items):
        result["status"] = "completed"
        result["completed_at"] = datetime.now(CST).isoformat()
        save_json(args.output, result)
        print("\n✅ 20 条 Qwen 合理性抽查已全部完成。")
    else:
        save_json(args.output, result)
        print(f"\n仍有 {len(items) - len(completed)} 条未完成，可重新运行继续。")
    print(f"结果：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

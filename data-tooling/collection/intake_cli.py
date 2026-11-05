#!/usr/bin/env python3
"""标注前置采集：人工在平台上观察并录入 intake 记录。

流程倒置问题的修法：先由人在平台上亲眼判断，再让爬虫回填元数据。
人的判定不再依赖爬虫是否成功。

用法：
    python data-tooling/collection/intake_cli.py --out data/collection/intake.jsonl

每条记录的关键字段：
    intake.viewed_media       是否真看完视频/图片（full / partial / none）
    intake.disclosure_status  亲眼确认的披露状态（present / absent_complete / missing）
    intake.disclosure_note    在哪看的、看到什么

post_id 由 URL 派生（与 crawler_utils.stable_hash 同款），因此无需先跑爬虫即可
生成稳定 ID，回填时能精确对齐。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.3"
CST = timezone(timedelta(hours=8))

PLATFORM_PATTERNS = (
    ("bilibili", r"bilibili\.com|b23\.tv"),
    ("wechat_official_account", r"mp\.weixin\.qq\.com"),
    ("xiaohongshu", r"xiaohongshu\.com|xhslink\.com"),
    ("douyin", r"douyin\.com"),
    ("weibo", r"weibo\.com|weibo\.cn"),
)

LABEL_CHOICES = ("明广", "暗广", "非广", "out_of_scope", "uncertain")
VIEWED_CHOICES = ("full", "partial", "none")
DISCLOSURE_CHOICES = ("present", "absent_complete", "missing")


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def get_salt() -> str:
    """与 crawler_utils.get_salt 保持一致，确保 post_id 可对齐。"""
    salt = os.getenv("ANONYMIZATION_SALT")
    if not salt:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                # .env 中键名可能带尾随空格（如 "ANONYMIZATION_SALT "）
                if key.strip() == "ANONYMIZATION_SALT":
                    salt = value.strip().strip('"').strip("'")
                    break
    if not salt:
        raise SystemExit(
            "缺少 ANONYMIZATION_SALT。请在环境变量或项目根目录 .env 中设置，"
            "否则 post_id 无法与既有候选池对齐。"
        )
    return salt


def stable_hash(value: str, salt: str, length: int = 16) -> str:
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:length]


def derive_post_id(url: str, salt: str) -> str:
    return "post_" + stable_hash(url.strip(), salt, length=32)


def detect_platform(url: str) -> str:
    lowered = url.lower()
    for name, pattern in PLATFORM_PATTERNS:
        if re.search(pattern, lowered):
            return name
    return "other"


def derive_collection_complete(viewed_media: str, backfill_status: str) -> str:
    """采集完整性由人工观察与回填结果共同推导，不让爬虫单方面声明。"""
    if viewed_media == "full" and backfill_status == "ok":
        return "complete"
    if viewed_media in ("full", "partial"):
        return "incomplete"
    return "unknown"


def build_record(
    *,
    url: str,
    viewed_media: str,
    disclosure_status: str,
    disclosure_note: Optional[str],
    draft_label: Optional[str],
    draft_confidence: Optional[float],
    draft_evidence: Optional[str],
    annotator_id: str,
    title: Optional[str] = None,
    text: Optional[str] = None,
    salt: str,
) -> Dict[str, Any]:
    post_id = derive_post_id(url, salt)
    platform = detect_platform(url)
    intake_at = now_iso()
    backfill_status = "pending"
    return {
        "schema_version": SCHEMA_VERSION,
        "post_id": post_id,
        "platform": platform,
        "source_type": "manual_public_collection",
        "blogger_id": None,
        "published_at": None,
        "title": title,
        "content_group_id": None,
        "text": text or "",
        "media": [],
        "comments": [],
        "blogger_history_refs": [],
        "collection_complete": derive_collection_complete(viewed_media, backfill_status),
        "disclosure_status": disclosure_status,
        "intake": {
            "source_url": url.strip(),
            "viewed_media": viewed_media,
            "disclosure_status": disclosure_status,
            "disclosure_note": disclosure_note,
            "draft_label": draft_label,
            "draft_confidence": draft_confidence,
            "draft_evidence": draft_evidence,
            "annotator_id": annotator_id,
            "intake_at": intake_at,
        },
        "backfill": {
            "status": backfill_status,
            "attempted_at": intake_at,
            "error": None,
            "fields_filled": [],
        },
        "provenance": {
            "source_ref_hash": stable_hash(url.strip(), salt, length=32),
            "collected_at": intake_at,
            "collector": annotator_id,
            "terms_checked_at": None,
            "llm_mode": None,
            "llm_confidence": None,
            "llm_needs_review": False,
            "llm_notes": "标注前置采集：人工在平台观察后录入",
        },
        "privacy": {"anonymized": True, "contains_sensitive_data": False},
        "_collected": {
            "source_ref_hash": stable_hash(url.strip(), salt, length=32),
            "collected_at": intake_at,
            "collector": annotator_id,
            "terms_checked_at": None,
            "source_url": url.strip(),
        },
    }


def ask(prompt: str, *, default: str = "", required: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            value = input(f"{prompt}{suffix}: ").strip()
        except EOFError:
            raise SystemExit("\n输入已结束，退出。")
        if not value and default:
            return default
        if value or not required:
            return value
        print("  必填，请重新输入。")


def ask_choice(
    prompt: str,
    choices: tuple,
    *,
    default: str = "",
    allow_empty: bool = False,
) -> str:
    menu = " / ".join(choices)
    hint = "，直接回车跳过" if allow_empty and not default else ""
    while True:
        value = ask(f"{prompt}{hint} ({menu})", default=default, required=not allow_empty)
        if not value and allow_empty:
            return ""
        if value in choices:
            return value
        print(f"  只能是 {menu} 之一。")


def ask_optional_confidence() -> Optional[float]:
    while True:
        raw = ask("置信度 0-1（可空）", required=False)
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            print("  请输入数字，例如 0.85。")
            continue
        if 0.0 <= value <= 1.0:
            return value
        print("  需在 0 到 1 之间。")


def existing_ids(path: Path) -> Dict[str, int]:
    """返回已存在的 post_id → 行号，用于去重提示。"""
    seen: Dict[str, int] = {}
    if not path.exists():
        return seen
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            post_id = record.get("post_id")
            if post_id:
                seen[post_id] = lineno
    return seen


def append_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def print_reminder(record: Dict[str, Any]) -> None:
    intake = record["intake"]
    viewed = intake["viewed_media"]
    disclosure = intake["disclosure_status"]
    print("\n--- 已记录 ---")
    print(f"  post_id : {record['post_id']}")
    print(f"  平台    : {record['platform']}")
    print(f"  看过媒体: {viewed}")
    print(f"  披露状态: {disclosure}")
    print(f"  完整性  : {record['collection_complete']}（回填成功后重算）")
    if disclosure == "absent_complete" and viewed != "full":
        print("  ⚠ 声明「披露区域完整且无披露」但未完整观看媒体，暗广判定依据不足。")
    if intake["draft_label"] == "暗广" and disclosure != "absent_complete":
        print("  ⚠ 初判暗广但披露状态不是 absent_complete，记录后需复核。")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="标注前置采集：人工在平台观察后录入 intake 记录"
    )
    parser.add_argument("--out", required=True, help="intake JSONL 输出路径")
    parser.add_argument("--annotator", default="A", help="录入人标识，默认 A")
    parser.add_argument("--batch", type=int, default=0, help="每录入 N 条后暂停，0 表示不暂停")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    salt = get_salt()
    seen = existing_ids(out_path)

    print(f"输出: {out_path}")
    print(f"录入人: {args.annotator}")
    print(f"已有记录: {len(seen)} 条")
    print("输入 q 退出。\n" if not args.batch else f"每 {args.batch} 条暂停。输入 q 退出。\n")

    count = 0
    while True:
        if args.batch and count and count % args.batch == 0:
            if ask("暂停。回车继续，q 退出", required=False).lower() == "q":
                break

        url = ask("链接（q 退出）", required=False)
        if not url:
            break
        if url.lower() == "q":
            break
        if not re.match(r"^https?://", url, re.IGNORECASE):
            print("  需要以 http:// 或 https:// 开头。")
            continue

        post_id = derive_post_id(url, salt)
        if post_id in seen:
            print(f"  该链接已录入（第 {seen[post_id]} 行，post_id={post_id}），跳过。")
            continue

        print(f"  post_id: {post_id}  平台: {detect_platform(url)}")
        title = ask("标题（可空）", required=False)
        text = ask("正文摘要（可空，但判暗广必须能说清推广结构）", required=False)
        viewed = ask_choice("是否看完视频/图片", VIEWED_CHOICES, default="full")
        disclosure = ask_choice(
            "披露状态（absent_complete = 已完整查看且未发现披露）",
            DISCLOSURE_CHOICES,
            default="absent_complete",
        )
        note = ask("披露判断依据：在哪看的、看到什么", required=False)
        label = ask_choice(
            "初判（可空）", LABEL_CHOICES, allow_empty=True
        )
        confidence = ask_optional_confidence() if label else None
        evidence = ask("初判理由（一句话，可空）", required=False) if label else None

        record = build_record(
            url=url,
            viewed_media=viewed,
            disclosure_status=disclosure,
            disclosure_note=note or None,
            draft_label=label or None,
            draft_confidence=confidence,
            draft_evidence=evidence or None,
            annotator_id=args.annotator,
            title=title or None,
            text=text or None,
            salt=salt,
        )
        append_record(out_path, record)
        seen[post_id] = len(seen) + 1
        count += 1
        print_reminder(record)

    print(f"\n本次录入 {count} 条，累计 {len(seen)} 条 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

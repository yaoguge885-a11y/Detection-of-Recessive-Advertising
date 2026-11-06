#!/usr/bin/env python3
"""人工采集 + 标注一次完成。

适用场景：标注者直接在平台上打开帖子，把标题、简介、tag、评论区抄录进来，
同一次交互里给出最终标签。不经过爬虫，不需要回填。

为什么这样做：
  - 披露判定（是否看完、披露区是否完整）只有人在平台上能确认，机器无从得知；
  - 人工采集时 collection_complete 天然为 complete，判定前提首次可审计；
  - 判定所需的全部证据（标题/简介/tag/评论）与标签同时落盘，不会因为
    爬虫失败或链接失效而变成不可复核的记录。

输出为 schema v1.4 的 content_record，内嵌 annotation。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.4"
GUIDE_VERSION = "1.0"
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
EVIDENCE_CODES = ("D", "C", "P", "A", "V", "M", "B")


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def get_salt() -> str:
    salt = os.getenv("ANONYMIZATION_SALT")
    if not salt:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "ANONYMIZATION_SALT":
                    salt = value.strip().strip('"').strip("'")
                    break
    if not salt:
        raise SystemExit("缺少 ANONYMIZATION_SALT，无法生成稳定 post_id。")
    return salt


def stable_hash(value: str, salt: str, length: int = 16) -> str:
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:length]


def derive_post_id(url: str, salt: str) -> str:
    return "post_" + stable_hash(url.strip(), salt, length=32)


def derive_blogger_id(creator_key: str, salt: str) -> Optional[str]:
    key = (creator_key or "").strip()
    if not key:
        return None
    return "blogger_" + stable_hash(key, salt, length=24)


def detect_platform(url: str) -> str:
    lowered = url.lower()
    for name, pattern in PLATFORM_PATTERNS:
        if re.search(pattern, lowered):
            return name
    return "other"


def parse_tags(raw: str) -> List[str]:
    """接受中英文逗号、顿号、空格、# 分隔。"""
    if not raw.strip():
        return []
    parts = re.split(r"[,，、;；#\s]+", raw)
    seen: List[str] = []
    for part in parts:
        tag = part.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def parse_comments(raw_lines: List[str]) -> List[Dict[str, Any]]:
    """把人工抄录的评论转成 comment_item。

    约定：行首写 [新] / [热] / [新热] 标明来自哪个排序，允许连写如 [新][热]；
    不写则视为未标注排序。行尾可写 "| 赞数"。
    """
    comments: List[Dict[str, Any]] = []
    for index, raw in enumerate(raw_lines):
        line = raw.strip()
        if not line:
            continue
        sources: List[str] = []
        while True:
            match = re.match(r"^\[(新|热|新热|最新|最热)\]\s*", line)
            if not match:
                break
            marker = match.group(1)
            if marker in ("新", "最新"):
                picked = ["latest"]
            elif marker in ("热", "最热"):
                picked = ["hot"]
            else:
                picked = ["latest", "hot"]
            for source in picked:
                if source not in sources:
                    sources.append(source)
            line = line[match.end() :].strip()
        like = 0
        if "|" in line:
            head, _, tail = line.rpartition("|")
            tail = tail.strip()
            if tail.isdigit():
                like = int(tail)
                line = head.strip()
        if not line:
            continue
        comments.append({
            "comment_id": f"manual_{index:03d}",
            "author_id": "",
            "text": line,
            "like_count": like,
            "is_pinned": False,
            "created_at": None,
            "sort_source": sources,
            "is_deleted": False,
        })
    return comments


def derive_collection_complete(viewed_media: str) -> str:
    """人工采集时由标注者自述；看全即 complete。"""
    if viewed_media == "full":
        return "complete"
    if viewed_media == "partial":
        return "incomplete"
    return "unknown"


def build_record(
    *,
    url: str,
    platform: str,
    title: Optional[str],
    desc: Optional[str],
    text: str,
    tags: List[str],
    comments: List[Dict[str, Any]],
    creator_key: str,
    viewed_media: str,
    disclosure_status: str,
    disclosure_note: Optional[str],
    label: str,
    confidence: float,
    evidence_codes: List[str],
    evidence_text: str,
    uncertain_reason: Optional[str],
    annotator_id: str,
    salt: str,
    reviewed_all_comments: bool,
) -> Dict[str, Any]:
    post_id = derive_post_id(url, salt)
    ts = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "post_id": post_id,
        "platform": platform,
        "source_type": "manual_public_collection",
        "blogger_id": derive_blogger_id(creator_key, salt),
        "published_at": None,
        "title": title,
        "desc": desc,
        "text": text,
        "tags": tags,
        "stats": None,
        "media": [],
        "comments": comments,
        "comments_meta": {
            "target_n": len(comments),
            "sorts_used": sorted({s for c in comments for s in c.get("sort_source") or []}),
            "total_available": None,
            "exhausted": reviewed_all_comments,
            "returned": len(comments),
            "requests_made": 0,
            "degraded": False,
            "degraded_reason": None,
            "collected_at": ts,
        },
        "blogger_history_refs": [],
        "collection_complete": derive_collection_complete(viewed_media),
        "disclosure_status": disclosure_status,
        "intake": {
            "source_url": url.strip(),
            "viewed_media": viewed_media,
            "disclosure_status": disclosure_status,
            "disclosure_note": disclosure_note,
            "draft_label": None,
            "draft_confidence": None,
            "draft_evidence": None,
            "annotator_id": annotator_id,
            "intake_at": ts,
        },
        "backfill": {
            "status": "ok",
            "attempted_at": ts,
            "error": None,
            "fields_filled": ["title", "desc", "text", "tags", "comments"],
        },
        "annotation_method": "human",
        "provenance": {
            "source_ref_hash": stable_hash(url.strip(), salt, length=32),
            "collected_at": ts,
            "collector": annotator_id,
            "terms_checked_at": None,
            "llm_mode": None,
            "llm_confidence": None,
            "llm_needs_review": False,
            "llm_notes": "人工在平台采集并同期标注",
        },
        "privacy": {"anonymized": True, "contains_sensitive_data": False},
        "_collected": {
            "source_ref_hash": stable_hash(url.strip(), salt, length=32),
            "collected_at": ts,
            "collector": annotator_id,
            "terms_checked_at": None,
            "source_url": url.strip(),
        },
        "annotation": {
            "post_id": post_id,
            "annotator_id": annotator_id,
            "guide_version": GUIDE_VERSION,
            "label": label,
            "confidence": confidence,
            "evidence_codes": evidence_codes,
            "evidence": [e for e in [evidence_text] if e],
            "uncertain_reason": uncertain_reason,
            "annotated_at": ts,
            "annotation_method": "human",
            "collection_mode": "manual_platform",
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
        print("  必填。")


def ask_choice(prompt: str, choices: tuple, *, default: str = "", allow_empty: bool = False) -> str:
    menu = " / ".join(choices)
    hint = "，回车跳过" if allow_empty and not default else ""
    while True:
        value = ask(f"{prompt}{hint} ({menu})", default=default, required=not allow_empty)
        if not value and allow_empty:
            return ""
        if value in choices:
            return value
        print(f"  只能是 {menu} 之一。")


def ask_multiline(prompt: str, *, required_ok_empty: bool = True) -> str:
    print(f"{prompt}（单行输入，空行结束；空行直接结束表示无内容）")
    lines: List[str] = []
    while True:
        try:
            line = input("  > ").rstrip()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def ask_comments() -> List[str]:
    print("评论区抄录（每行一条，空行结束）")
    print("  行首可写 [新] / [热] / [新热] 标明来自最新还是最热排序")
    print("  可在行尾写 | 赞数")
    lines: List[str] = []
    while True:
        try:
            line = input("  > ").rstrip()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return lines


def ask_confidence() -> float:
    while True:
        raw = ask("置信度 0-1", default="0.8")
        try:
            value = float(raw)
        except ValueError:
            print("  请输入数字。")
            continue
        if 0.0 <= value <= 1.0:
            return value
        print("  需在 0 到 1 之间。")


def ask_evidence_codes() -> List[str]:
    print(f"  可用证据码：{', '.join(EVIDENCE_CODES)}")
    raw = ask("证据码（逗号分隔，可空）", required=False)
    if not raw:
        return []
    codes: List[str] = []
    for part in re.split(r"[,，、\s]+", raw):
        code = part.strip().upper()
        if not code:
            continue
        if code not in EVIDENCE_CODES:
            print(f"  忽略未知证据码 {code}")
            continue
        if code not in codes:
            codes.append(code)
    return codes


def existing_ids(path: Path) -> Dict[str, int]:
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


def print_summary(record: Dict[str, Any]) -> None:
    ann = record["annotation"]
    print("\n--- 已保存 ---")
    print(f"  post_id   : {record['post_id']}")
    print(f"  平台      : {record['platform']}")
    print(f"  标签      : {ann['label']}  ({ann['confidence']})")
    print(f"  证据码    : {', '.join(ann['evidence_codes']) or '无'}")
    print(f"  tag       : {len(record['tags'])} 个")
    print(f"  评论      : {len(record['comments'])} 条")
    print(f"  采集完整性: {record['collection_complete']}")
    print(f"  披露状态  : {record['disclosure_status']}")

    warns: List[str] = []
    if ann["label"] == "暗广" and record["disclosure_status"] != "absent_complete":
        warns.append("判暗广但披露状态不是 absent_complete —— 暗广前提不成立，请复核")
    if ann["label"] == "暗广" and record["intake"]["viewed_media"] != "full":
        warns.append("判暗广但未完整观看媒体 —— 披露区完整性存疑")
    if ann["label"] in ("明广", "暗广") and not ann["evidence_codes"]:
        warns.append("判广但未记任何证据码")
    if ann["label"] == "uncertain" and not ann.get("uncertain_reason"):
        warns.append("判 uncertain 但未写原因")
    for warning in warns:
        print(f"  ⚠ {warning}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="人工采集 + 标注一次完成")
    parser.add_argument("--out", required=True, help="输出 JSONL 路径")
    parser.add_argument("--annotator", default="A", help="标注者标识")
    parser.add_argument("--batch", type=int, default=0, help="每 N 条暂停，0 不暂停")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    salt = get_salt()
    seen = existing_ids(out_path)

    print(f"输出  : {out_path}")
    print(f"标注者: {args.annotator}")
    print(f"已有  : {len(seen)} 条")
    print("空行结束当前字段的多行输入；输入 q 结束本轮。\n")

    saved = 0
    while True:
        if args.batch and saved and saved % args.batch == 0:
            if ask("暂停，回车继续，q 结束", required=False).lower() == "q":
                break

        print("=" * 60)
        url = ask("链接（q 结束）", required=False)
        if not url or url.lower() == "q":
            break
        if not re.match(r"^https?://", url, re.IGNORECASE):
            print("  需要 http:// 或 https:// 开头。")
            continue

        post_id = derive_post_id(url, salt)
        if post_id in seen:
            print(f"  已录入（第 {seen[post_id]} 行），跳过。")
            continue

        platform = detect_platform(url)
        print(f"  post_id : {post_id}")
        print(f"  平台    : {platform}")

        creator_key = ask("作者/博主 ID 或昵称（用于 creator_id）", required=False)
        title = ask_multiline("标题（可空）").strip() or None
        desc = ask_multiline("简介/描述（可空）").strip() or None
        text = ask_multiline("正文（B站视频可留空，只填简介）")
        tags = parse_tags(ask("tag（逗号分隔，可空）", required=False))
        comment_lines = ask_comments()
        comments = parse_comments(comment_lines)
        reviewed_all = ask("评论是否已全部看（y/n）", default="y").lower().startswith("y")

        print("\n-- 判定依据 --")
        viewed = ask_choice("是否看完视频/图片", VIEWED_CHOICES, default="full")
        disclosure = ask_choice(
            "披露状态（absent_complete = 已完整查看且未见披露）",
            DISCLOSURE_CHOICES,
            default="absent_complete",
        )
        note = ask("披露判断依据（在哪看的、看到什么）", required=False)

        print("\n-- 标注 --")
        label = ask_choice("标签", LABEL_CHOICES)
        confidence = ask_confidence()
        codes = ask_evidence_codes()
        evidence = ask("判定理由", required=False)
        uncertain_reason = None
        if label == "uncertain":
            uncertain_reason = ask("uncertain 原因")

        record = build_record(
            url=url,
            platform=platform,
            title=title,
            desc=desc,
            text=text,
            tags=tags,
            comments=comments,
            creator_key=creator_key,
            viewed_media=viewed,
            disclosure_status=disclosure,
            disclosure_note=note or None,
            label=label,
            confidence=confidence,
            evidence_codes=codes,
            evidence_text=evidence,
            uncertain_reason=uncertain_reason,
            annotator_id=args.annotator,
            salt=salt,
            reviewed_all_comments=reviewed_all,
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        seen[post_id] = len(seen) + 1
        saved += 1
        print_summary(record)

    print(f"\n本轮保存 {saved} 条，累计 {len(seen)} 条 → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

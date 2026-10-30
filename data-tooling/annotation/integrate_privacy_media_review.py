#!/usr/bin/env python3
"""Merge B's exported media-review JSON into the M1 privacy review packet."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HEADING_RE = re.compile(r"^### ([MS]-\d{3}) `(post_[0-9a-f]{32})`$", re.MULTILINE)
DRAFT_RE = re.compile(r"^- AI draft: \*\*(allow|redact|exclude)\*\*", re.MULTILINE)
MEDIA_LINE_RE = re.compile(r"^- Media:.*$", re.MULTILINE)
COMBINED_HEADER_RE = re.compile(r"^- Combined preliminary after B media review:.*$\n", re.MULTILINE)
MEDIA_REVIEW_LINE = "- B media review:"
COMBINED_LINE = "- Combined preliminary:"


def load_media_review(path: Path) -> dict[str, dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Media review must be a JSON object containing an items list.")
    review: dict[str, dict[str, str]] = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Media review items must be objects.")
        post_id = str(item.get("post_id") or "")
        status = str(item.get("status") or "")
        if not re.fullmatch(r"post_[0-9a-f]{32}", post_id):
            raise ValueError(f"Invalid post_id in media review: {post_id!r}")
        if status not in {"clean", "risk"}:
            raise ValueError(f"Unsupported media status for {post_id}: {status!r}")
        if post_id in review:
            raise ValueError(f"Duplicate post_id in media review: {post_id}")
        note = " ".join(str(item.get("note") or "").split())
        review[post_id] = {"status": status, "note": note}
    return review


def safe_note(note: str) -> str:
    return note.replace("`", "'").replace("|", "/")


def update_block(block: str, media_review: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    heading = HEADING_RE.search(block)
    if heading is None:
        return block, {}
    item, post_id = heading.groups()
    draft_match = DRAFT_RE.search(block)
    if draft_match is None:
        raise ValueError(f"Missing AI draft for {post_id}")
    text_draft = draft_match.group(1)
    media_line = MEDIA_LINE_RE.search(block)
    if media_line is None:
        raise ValueError(f"Missing Media line for {post_id}")

    lines = [
        line
        for line in block.splitlines()
        if not line.startswith(MEDIA_REVIEW_LINE)
        and not line.startswith(COMBINED_LINE)
    ]
    media_index = next(
        index for index, line in enumerate(lines) if line.startswith("- Media:")
    )
    media = media_review.get(post_id)
    if media is None:
        media_lines = ["- B media review: not applicable — no associated media item."]
        combined = text_draft
    elif media["status"] == "clean":
        media_lines = [
            "- B media review: **clean** — B reviewed all available media and recorded no privacy risk."
        ]
        combined = text_draft
    else:
        note = safe_note(media["note"]) or "B recorded a media privacy risk."
        media_lines = [f"- B media review: **risk** — {note}"]
        combined = "redact" if text_draft == "allow" else text_draft
    if combined == text_draft:
        combined_reason = "text and media review do not add a stricter action"
    else:
        combined_reason = "B media review adds a privacy risk that requires media masking or removal"
    media_lines.append(
        f"- Combined preliminary: **{combined}** — {combined_reason}."
    )
    lines[media_index + 1:media_index + 1] = media_lines
    return "\n".join(lines) + "\n", {
        "item": item,
        "post_id": post_id,
        "text_draft": text_draft,
        "media_status": media["status"] if media else "not_applicable",
        "media_note": media["note"] if media else "",
        "combined": combined,
    }


def merge_review_document(path: Path, media_review: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], Counter[str]]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"(?=^### [MS]-\d{3} `post_[0-9a-f]{32}`$)", text, flags=re.MULTILINE)
    merged: list[str] = []
    rows: list[dict[str, str]] = []
    for block in blocks:
        if HEADING_RE.search(block):
            updated, row = update_block(block, media_review)
            merged.append(updated)
            rows.append(row)
        else:
            merged.append(block)
    review_ids = {row["post_id"] for row in rows}
    unknown_ids = set(media_review) - review_ids
    if unknown_ids:
        raise ValueError(f"Media review contains unknown post_ids: {sorted(unknown_ids)[:3]}")
    counts = Counter(row["combined"] for row in rows)
    updated_text = "".join(merged)
    summary = (
        f"- Combined preliminary after B media review: `allow {counts['allow']}`、"
        f"`redact {counts['redact']}`、`exclude {counts['exclude']}`。\n"
    )
    updated_text = COMBINED_HEADER_RE.sub("", updated_text)
    anchor = "- 修订后 AI 建议："
    lines = updated_text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(anchor):
            lines.insert(index + 1, summary)
            break
    else:
        raise ValueError("Could not find review-document header anchor.")
    path.write_text("".join(lines), encoding="utf-8")
    return rows, counts


def write_summary(path: Path, rows: list[dict[str, str]], counts: Counter[str]) -> None:
    risks = [row for row in rows if row["media_status"] == "risk"]
    lines = [
        "# B 组员媒体审核合并摘要",
        "",
        f"- 导入时间（UTC）：{datetime.now(timezone.utc).isoformat()}",
        f"- 合并范围：{len(rows)} 条文本审核记录；其中 {len(rows) - len([row for row in rows if row['media_status'] == 'not_applicable'])} 条有 B 媒体审核结论。",
        f"- 媒体结论：clean {len([row for row in rows if row['media_status'] == 'clean'])}，risk {len(risks)}，无媒体 {len([row for row in rows if row['media_status'] == 'not_applicable'])}。",
        f"- 合并初判：allow {counts['allow']}，redact {counts['redact']}，exclude {counts['exclude']}。",
        "- 说明：这是“文本 AI 初审 + B 媒体审核”的合并初判；它不替代 B 对文本部分的最终勾选和正式 `privacy_approval.json`。",
        "",
        "## 媒体风险项（7 条）",
        "",
        "| 条目 | post_id | 文本初判 | 媒体备注 | 合并初判 |",
        "|---|---|---|---|---|",
    ]
    for row in sorted(risks, key=lambda item: item["item"]):
        lines.append(
            f"| {row['item']} | `{row['post_id']}` | {row['text_draft']} | "
            f"{safe_note(row['media_note'])} | {row['combined']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-review", type=Path, required=True)
    parser.add_argument("--review-document", type=Path, required=True)
    parser.add_argument("--media-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    media_review = load_media_review(args.media_review)
    rows, counts = merge_review_document(args.review_document, media_review)
    args.media_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.media_review, args.media_output)
    write_summary(args.summary_output, rows, counts)
    print(
        json.dumps(
            {
                "records": len(rows),
                "media_reviewed": len(media_review),
                "combined": dict(counts),
                "media_output": str(args.media_output),
                "summary_output": str(args.summary_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

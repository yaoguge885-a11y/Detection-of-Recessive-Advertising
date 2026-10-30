#!/usr/bin/env python3
"""Build B's formal privacy approval JSON from a fully confirmed review packet."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


HEADING_RE = re.compile(r"^### ([MS]-\d{3}) `(post_[0-9a-f]{32})`$", re.MULTILINE)
DECISION_RE = re.compile(
    r"^- Combined preliminary: \*\*(allow|redact|exclude)\*\*", re.MULTILINE
)
SOURCE_STATE_RE = re.compile(r"^- Source state: \*\*([^*]+)\*\*", re.MULTILINE)
FINDINGS_RE = re.compile(r"^- Findings: (.+)$", re.MULTILINE)
MEDIA_RISK_RE = re.compile(r"^- B media review: \*\*risk\*\* — (.+)$", re.MULTILINE)
AGREE_RE = re.compile(r"^\s*- \[x\] agree", re.MULTILINE)
DISAGREE_RE = re.compile(r"^\s*- \[x\] disagree", re.MULTILINE)
CHANGE_RE = re.compile(r"^- If disagree: change_to:\s*([^;\r\n]+)", re.MULTILINE)


def parse_review(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(
        r"(?=^### [MS]-\d{3} `post_[0-9a-f]{32}`\r?$)", text, flags=re.MULTILINE
    )
    rows: list[dict[str, str]] = []
    for block in blocks:
        heading = HEADING_RE.search(block)
        if heading is None:
            continue
        item, post_id = heading.groups()
        agrees = bool(AGREE_RE.search(block))
        disagrees = bool(DISAGREE_RE.search(block))
        if agrees == disagrees:
            raise ValueError(
                f"{item} ({post_id}) must have exactly one B confirmation checkbox selected."
            )
        decision_match = DECISION_RE.search(block)
        if decision_match is None:
            raise ValueError(f"{item} ({post_id}) has no combined preliminary decision.")
        decision = decision_match.group(1)
        if disagrees:
            change_match = CHANGE_RE.search(block)
            if change_match is None or change_match.group(1).strip() not in {
                "allow",
                "redact",
                "exclude",
            }:
                raise ValueError(
                    f"{item} ({post_id}) disagrees but has no valid change_to decision."
                )
            decision = change_match.group(1).strip()
        source_state = SOURCE_STATE_RE.search(block)
        findings = FINDINGS_RE.search(block)
        media_risk = MEDIA_RISK_RE.search(block)
        reason_parts = ["B confirmed the reviewed text/comment and media outcome"]
        if source_state:
            reason_parts.append(f"source state: {source_state.group(1).strip()}")
        if findings and findings.group(1).strip() != "none":
            reason_parts.append(f"findings: {findings.group(1).strip()}")
        if media_risk:
            reason_parts.append(f"media: {media_risk.group(1).strip()}")
        rows.append(
            {
                "item": item,
                "post_id": post_id,
                "decision": decision,
                "reason": "; ".join(reason_parts),
            }
        )
    if not rows:
        raise ValueError("No review records found.")
    if len({row["post_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate post_id in review document.")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-document", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", default="data/run_outputs/merged_20260728/anonymized_posts.jsonl")
    parser.add_argument(
        "--dataset-fingerprint",
        default="e9ccada23f8a09ad85dc7d99e097e717c2a9d12ab3ad0a228493460d3f79009c",
    )
    args = parser.parse_args()

    rows = parse_review(args.review_document)
    approved = [row["post_id"] for row in rows if row["decision"] == "allow"]
    excluded = [
        {"post_id": row["post_id"], "decision": row["decision"], "reason": row["reason"]}
        for row in rows
        if row["decision"] in {"redact", "exclude"}
    ]
    payload = {
        "reviewer": "B",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "M1 mandatory privacy review plus 10% low-risk sample (541 records)",
        "review_basis": {
            "dataset": args.dataset,
            "dataset_fingerprint_sha256": args.dataset_fingerprint,
            "review_document": "data/reports/m1/privacy/privacy_AI_pre_review_B.md",
            "media_review": "data/reports/m1/privacy/privacy_media_review_B.json",
            "reviewed_records": len(rows),
            "manual_confirmation": "B confirmed exactly one final checkbox for every reviewed record.",
        },
        "post_ids": approved,
        "excluded": excluded,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "records": len(rows),
                "approved": len(approved),
                "redact": sum(row["decision"] == "redact" for row in rows),
                "exclude": sum(row["decision"] == "exclude" for row in rows),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

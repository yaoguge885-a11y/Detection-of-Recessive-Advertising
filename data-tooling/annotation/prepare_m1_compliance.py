#!/usr/bin/env python3
"""Prepare immutable M1 terms and privacy-review working artifacts.

The command never edits the source dataset. It writes a terms-stamped working
copy, a redacted privacy review queue, and draft approval/spot-check lists.
Human reviewer fields deliberately remain pending until a person confirms them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from privacy_scan import redact_finding, scan_record


CST = timezone(timedelta(hours=8))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            post_id = str(row.get("post_id", ""))
            if not post_id:
                raise ValueError(f"line {line_number}: missing post_id")
            if post_id in seen:
                raise ValueError(f"line {line_number}: duplicate post_id {post_id}")
            seen.add(post_id)
            rows.append(row)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def severity_rank(findings: list[dict[str, Any]]) -> int:
    ranks = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return min((ranks.get(str(item.get("severity")), 4) for item in findings), default=4)


def has_empty_referenced_media(row: dict[str, Any], media_root: Path) -> bool:
    for media in row.get("media") or []:
        if not isinstance(media, dict) or not media.get("ref"):
            continue
        path = media_root / Path(str(media["ref"]))
        if path.is_file() and path.stat().st_size == 0:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--terms-output", required=True, type=Path)
    parser.add_argument("--terms-report", required=True, type=Path)
    parser.add_argument("--terms-date", required=True)
    parser.add_argument("--verified-platform", action="append", required=True)
    parser.add_argument("--privacy-draft", required=True, type=Path)
    parser.add_argument("--review-queue", required=True, type=Path)
    parser.add_argument("--safe-spotcheck", required=True, type=Path)
    parser.add_argument("--a-boundary-sample", required=True, type=Path)
    parser.add_argument("--formal-pool-draft", required=True, type=Path)
    parser.add_argument("--media-root", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260810)
    args = parser.parse_args()

    rows = load_jsonl(args.input.resolve())
    platforms = set(args.verified_platform)
    stamped = 0
    for row in rows:
        if str(row.get("platform")) not in platforms:
            continue
        provenance = row.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError(f"{row['post_id']}: missing provenance object")
        provenance["terms_checked_at"] = args.terms_date
        collected = row.get("_collected")
        if isinstance(collected, dict):
            collected["terms_checked_at"] = args.terms_date
        stamped += 1

    write_jsonl(args.terms_output, rows)
    terms_report = {
        "generated_at": datetime.now(CST).isoformat(),
        "source_file": str(args.input.resolve()),
        "source_sha256": sha256(args.input.resolve()),
        "working_file": str(args.terms_output.resolve()),
        "working_sha256": sha256(args.terms_output.resolve()),
        "terms_checked_at": args.terms_date,
        "verified_platforms": sorted(platforms),
        "records": len(rows),
        "records_stamped": stamped,
        "platform_counts": dict(Counter(str(row.get("platform")) for row in rows)),
        "notice": (
            "terms_checked_at records the review date only; it does not assert "
            "platform permission or authorization for redistribution"
        ),
    }
    write_json(args.terms_report, terms_report)

    review_queue: list[dict[str, Any]] = []
    safe_ids: list[str] = []
    excluded: list[dict[str, str]] = []
    boundary_candidates: list[tuple[int, str]] = []
    rows_by_id = {str(row["post_id"]): row for row in rows}

    for row in rows:
        post_id = str(row["post_id"])
        findings = scan_record(row)
        privacy = row.get("privacy") or {}
        reasons: list[str] = []
        if findings:
            types = sorted({str(item.get("type")) for item in findings})
            reasons.append("scanner findings: " + ", ".join(types))
            review_queue.append(
                {
                    "post_id": post_id,
                    "platform": row.get("platform"),
                    "decision": "exclude_pending_redaction_or_human_review",
                    "findings": [redact_finding(item) for item in findings],
                }
            )
            boundary_candidates.append((severity_rank(findings), post_id))
        if privacy.get("anonymized") is not True:
            reasons.append("privacy.anonymized is not true")
        if privacy.get("contains_sensitive_data") is not False:
            reasons.append("privacy.contains_sensitive_data is not false")
            boundary_candidates.append((1, post_id))

        if reasons:
            excluded.append(
                {
                    "post_id": post_id,
                    "decision": "exclude",
                    "reason": "; ".join(dict.fromkeys(reasons)),
                }
            )
        else:
            safe_ids.append(post_id)

    review_queue.sort(
        key=lambda item: (
            severity_rank(item["findings"]),
            str(item["platform"]),
            str(item["post_id"]),
        )
    )
    excluded.sort(key=lambda item: item["post_id"])
    safe_ids.sort()

    approval_draft = {
        "status": "draft_pending_human_B_confirmation",
        "reviewer": "PENDING_HUMAN_B",
        "prepared_by": "automated rules and AI-assisted triage; not a human approval",
        "prepared_at": datetime.now(CST).isoformat(),
        "reviewed_at": None,
        "scope": "M1 formal kappa, Gold and release splits",
        "dataset_sha256": sha256(args.terms_output.resolve()),
        "post_ids": safe_ids,
        "excluded": excluded,
    }
    write_json(args.privacy_draft, approval_draft)
    write_json(
        args.review_queue,
        {
            "status": "pending_human_review",
            "dataset_sha256": approval_draft["dataset_sha256"],
            "total_records_with_scanner_findings": len(review_queue),
            "records": review_queue,
        },
    )

    rng = random.Random(args.seed)
    spotcheck_size = math.ceil(len(safe_ids) * 0.10)
    spotcheck = sorted(rng.sample(safe_ids, spotcheck_size))
    write_json(
        args.safe_spotcheck,
        {
            "status": "pending_human_B_review",
            "seed": args.seed,
            "population": len(safe_ids),
            "sample_size": len(spotcheck),
            "post_ids": spotcheck,
        },
    )

    boundary_ids: list[str] = []
    for _, post_id in sorted(set(boundary_candidates)):
        if post_id not in boundary_ids:
            boundary_ids.append(post_id)
        if len(boundary_ids) == 30:
            break
    write_json(
        args.a_boundary_sample,
        {
            "status": "pending_human_A_review",
            "sample_size": len(boundary_ids),
            "post_ids": boundary_ids,
        },
    )

    media_root = args.media_root.resolve()
    formal_ids = [
        post_id
        for post_id in safe_ids
        if not has_empty_referenced_media(rows_by_id[post_id], media_root)
    ]
    write_json(
        args.formal_pool_draft,
        {
            "status": "draft_pending_human_privacy_confirmation",
            "dataset_sha256": approval_draft["dataset_sha256"],
            "privacy_safe_count": len(safe_ids),
            "excluded_for_empty_referenced_media": len(safe_ids) - len(formal_ids),
            "formal_sampling_pool_count": len(formal_ids),
            "post_ids": formal_ids,
        },
    )

    print(json.dumps({
        "records": len(rows),
        "terms_stamped": stamped,
        "privacy_safe_draft": len(safe_ids),
        "privacy_excluded_draft": len(excluded),
        "scanner_review_queue": len(review_queue),
        "safe_spotcheck": len(spotcheck),
        "a_boundary_sample": len(boundary_ids),
        "formal_sampling_pool_draft": len(formal_ids),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

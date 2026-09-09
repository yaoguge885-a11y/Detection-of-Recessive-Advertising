#!/usr/bin/env python3
"""Finalize already-approved text redactions in a separate candidate copy.

This script does not make privacy decisions. It only promotes records for which:
1. the signed approval already says ``decision=redact``;
2. the redaction audit says text changed and has no residual non-low finding;
3. the audit says no media risk remains.

The source dataset and source approval are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mask_sensitive_pii import load_objects, write_objects  # noqa: E402


CST = timezone(timedelta(hours=8))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refuse_existing(*paths: Path) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite: " + ", ".join(existing))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize B-approved text redactions in a separate candidate copy"
    )
    parser.add_argument("--input", required=True, help="redacted draft JSONL")
    parser.add_argument("--approval-file", required=True, help="signed B approval JSON")
    parser.add_argument("--redaction-report", required=True, help="audit-safe redaction report")
    parser.add_argument("--output", required=True, help="candidate JSONL output")
    parser.add_argument("--updated-approval", required=True, help="derived approval JSON output")
    parser.add_argument("--report", required=True, help="finalization report output")
    args = parser.parse_args()

    input_path = Path(args.input)
    approval_path = Path(args.approval_file)
    redaction_report_path = Path(args.redaction_report)
    output_path = Path(args.output)
    updated_approval_path = Path(args.updated_approval)
    report_path = Path(args.report)

    for path in (input_path, approval_path, redaction_report_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    refuse_existing(output_path, updated_approval_path, report_path)

    approval = json.loads(approval_path.read_text(encoding="utf-8-sig"))
    redaction_report = json.loads(
        redaction_report_path.read_text(encoding="utf-8-sig")
    )
    excluded = approval.get("excluded", [])
    if not isinstance(excluded, list):
        raise ValueError("approval excluded must be a list")
    approved_redact_ids = {
        str(item.get("post_id", ""))
        for item in excluded
        if isinstance(item, dict) and item.get("decision") == "redact"
    }

    ready_ids = {
        str(item.get("post_id", ""))
        for item in redaction_report.get("items", [])
        if item.get("changed")
        and not item.get("media_risk")
        and not item.get("after_non_low")
    }
    if not ready_ids:
        raise ValueError("redaction report contains no promotable records")
    unexpected = sorted(ready_ids - approved_redact_ids)
    if unexpected:
        raise ValueError(
            "report promotes records without signed redact decision: "
            + ", ".join(unexpected)
        )

    records, pretty = load_objects(input_path)
    seen: set[str] = set()
    finalized = 0
    for record in records:
        post_id = str(record.get("post_id", ""))
        if post_id in seen:
            raise ValueError(f"duplicate post_id in dataset: {post_id}")
        seen.add(post_id)
        if post_id not in ready_ids:
            continue
        privacy = record.setdefault("privacy", {})
        privacy["anonymized"] = True
        privacy["contains_sensitive_data"] = False
        finalized += 1

    missing = sorted(ready_ids - seen)
    if missing:
        raise ValueError("ready post_id missing from dataset: " + ", ".join(missing))
    if finalized != len(ready_ids):
        raise ValueError("finalized count does not match ready count")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_objects(output_path, records, pretty)

    updated_approval = deepcopy(approval)
    existing_post_ids = [str(value) for value in approval.get("post_ids", [])]
    if len(existing_post_ids) != len(set(existing_post_ids)):
        raise ValueError("approval post_ids contains duplicates")
    updated_approval["post_ids"] = existing_post_ids + sorted(
        ready_ids - set(existing_post_ids)
    )
    updated_approval["excluded"] = [
        item for item in excluded if str(item.get("post_id", "")) not in ready_ids
    ]
    updated_approval["redaction_applied_at"] = datetime.now(CST).isoformat()
    updated_approval["redaction_report"] = str(redaction_report_path)
    updated_approval["text_redactions_applied"] = len(ready_ids)

    updated_approval_path.parent.mkdir(parents=True, exist_ok=True)
    updated_approval_path.write_text(
        json.dumps(updated_approval, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    payload = {
        "status": "completed_from_signed_B_redact_decisions",
        "source_dataset": str(input_path),
        "source_approval": str(approval_path),
        "redaction_report": str(redaction_report_path),
        "output_dataset": str(output_path),
        "updated_approval": str(updated_approval_path),
        "finalized_text_redactions": len(ready_ids),
        "remaining_excluded": len(updated_approval["excluded"]),
        "output_dataset_sha256": sha256(output_path),
        "updated_approval_sha256": sha256(updated_approval_path),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Finalized text redactions: {len(ready_ids)}")
    print(f"Remaining excluded: {len(updated_approval['excluded'])}")
    print(f"Candidate dataset: {output_path}")
    print(f"Derived approval: {updated_approval_path}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a deterministic low-risk manifest for supplemental B privacy review.

The manifest is only a review queue. It never changes the signed approval and
never treats scanner output as a human privacy decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lock_annotation_batch import _creator_key, _media_state, choose_sample  # noqa: E402
from mask_sensitive_pii import load_objects  # noqa: E402
from privacy_scan import scan_record  # noqa: E402


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build supplemental low-risk B privacy review manifest"
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--approval-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=1700)
    parser.add_argument("--seed", type=int, default=505)
    parser.add_argument(
        "--exclude-manifest",
        action="append",
        default=[],
        help="Exclude every post_id listed by an existing manifest (repeatable).",
    )
    parser.add_argument(
        "--exclude-remote-video-only",
        action="store_true",
        help="Exclude records whose only reviewable media is a remote video link.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    approval_path = Path(args.approval_file)
    output_path = Path(args.output)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite: {output_path}")
    if args.count <= 0:
        raise ValueError("count must be positive")

    approval = json.loads(approval_path.read_text(encoding="utf-8-sig"))
    approved_ids = {str(value) for value in approval.get("post_ids", [])}
    excluded_ids = {
        str(item.get("post_id", ""))
        for item in approval.get("excluded", [])
        if isinstance(item, dict)
    }
    if approved_ids & excluded_ids:
        raise ValueError("approval post_ids and excluded overlap")
    manifest_excluded_ids: set[str] = set()
    for value in args.exclude_manifest:
        payload = json.loads(Path(value).read_text(encoding="utf-8-sig"))
        manifest_excluded_ids.update(str(post_id) for post_id in payload.get("post_ids", []))

    def is_remote_video_only(record: dict) -> bool:
        media = [item for item in (record.get("media") or []) if isinstance(item, dict)]
        return bool(media) and all(
            item.get("type") == "video"
            and not item.get("ref")
            and item.get("source_url")
            for item in media
        )

    records, _ = load_objects(dataset_path)
    eligible = []
    for record in records:
        post_id = str(record.get("post_id", ""))
        if (
            not post_id
            or post_id in approved_ids
            or post_id in excluded_ids
            or post_id in manifest_excluded_ids
        ):
            continue
        privacy = record.get("privacy") or {}
        if not privacy.get("anonymized"):
            continue
        if privacy.get("contains_sensitive_data") is not False:
            continue
        findings = scan_record(record)
        if any(item.get("severity") != "low" for item in findings):
            continue
        if args.exclude_remote_video_only and is_remote_video_only(record):
            continue
        eligible.append(record)

    if len(eligible) < args.count:
        raise ValueError(
            f"only {len(eligible)} supplemental privacy candidates are available"
        )
    selected = choose_sample(
        eligible,
        count=args.count,
        seed=args.seed,
        excluded_ids=set(),
        required_platforms=("bilibili", "wechat_official_account"),
        required_media_states=("available",),
    )
    post_ids = sorted(str(record["post_id"]) for record in selected)
    if len(post_ids) != len(set(post_ids)):
        raise AssertionError("selected post_ids are not unique")

    payload = {
        "status": "pending_B_human_privacy_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "dataset_sha256": file_hash(dataset_path),
        "approval_file": str(approval_path),
        "approval_sha256": file_hash(approval_path),
        "selection": {
            "seed": args.seed,
            "available_low_risk_unreviewed": len(eligible),
            "selected_count": len(post_ids),
            "minimum_additional_approvals_estimate": 1642,
            "buffer_count": max(0, len(post_ids) - 1642),
            "excluded_manifest_count": len(args.exclude_manifest),
            "excluded_manifest_post_ids": len(manifest_excluded_ids),
            "excluded_remote_video_only": args.exclude_remote_video_only,
            "required_platforms": ["bilibili", "wechat_official_account"],
            "required_media_state_coverage": ["available"],
        },
        "platform_counts": dict(
            sorted(Counter(str(record.get("platform", "unknown")) for record in selected).items())
        ),
        "media_state_counts": dict(
            sorted(Counter(_media_state(record) for record in selected).items())
        ),
        "creator_count": len({_creator_key(record) for record in selected}),
        "terms_missing_count": sum(
            1 for record in selected if not (record.get("provenance") or {}).get("terms_checked_at")
        ),
        "post_ids_sha256": hashlib.sha256("\n".join(post_ids).encode("utf-8")).hexdigest(),
        "post_ids": post_ids,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in payload.items() if key != "post_ids"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

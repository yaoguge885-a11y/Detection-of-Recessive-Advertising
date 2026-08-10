#!/usr/bin/env python3
"""Build a local-only media prefilter for supplemental privacy review.

The prefilter reuses exact file hashes from prior human media decisions.  It
does not turn an automated result into formal human approval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            if line.strip():
                item = json.loads(line)
                records[str(item.get("post_id", ""))] = item
    return records


def media_paths(record: dict, media_root: Path) -> list[tuple[str, Path]]:
    result = []
    for media in record.get("media") or []:
        if not isinstance(media, dict):
            continue
        ref = str(media.get("ref") or "")
        path = media_root / ref
        if ref and path.is_file():
            result.append((ref, path))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build privacy media hash prefilter")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--prior-media-review", required=True)
    parser.add_argument("--media-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    manifest_path = Path(args.manifest)
    prior_path = Path(args.prior_media_review)
    media_root = Path(args.media_root)
    output_path = Path(args.output)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite: {output_path}")

    records = load_jsonl(dataset_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    prior = json.loads(prior_path.read_text(encoding="utf-8-sig"))
    selected_ids = [str(value) for value in manifest.get("post_ids", [])]
    prior_clean_ids = {
        str(item.get("post_id", ""))
        for item in prior.get("items", [])
        if isinstance(item, dict) and item.get("status") == "clean"
    }
    prior_risk_ids = {
        str(item.get("post_id", ""))
        for item in prior.get("items", [])
        if isinstance(item, dict) and item.get("status") == "risk"
    }

    selected_media = {
        post_id: media_paths(records[post_id], media_root) for post_id in selected_ids
    }
    clean_paths = [
        path
        for post_id in prior_clean_ids
        for _, path in media_paths(records.get(post_id, {}), media_root)
    ]
    all_paths = {
        str(path.resolve()): path
        for entries in selected_media.values()
        for _, path in entries
    }
    all_paths.update({str(path.resolve()): path for path in clean_paths})
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        hashes = dict(zip(all_paths, executor.map(sha256, all_paths.values())))

    clean_hashes = {hashes[str(path.resolve())] for path in clean_paths}
    rows = []
    record_counts = Counter()
    occurrence_counts = Counter()
    for post_id in selected_ids:
        media = []
        for ref, path in selected_media[post_id]:
            digest = hashes[str(path.resolve())]
            if digest in clean_hashes:
                state = "prior_human_clean_exact_hash"
            else:
                state = "unseen_hash_needs_local_review"
            occurrence_counts[state] += 1
            media.append(
                {
                    "ref": ref.replace("\\", "/"),
                    "sha256": digest,
                    "bytes": path.stat().st_size,
                    "extension": path.suffix.lower(),
                    "prefilter": state,
                }
            )
        states = {item["prefilter"] for item in media}
        if states and states == {"prior_human_clean_exact_hash"}:
            record_state = "low_risk_all_media_previously_human_clean"
        elif media:
            record_state = "uncertain_unseen_media"
        else:
            record_state = "uncertain_no_local_media"
        record_counts[record_state] += 1
        rows.append({"post_id": post_id, "prefilter": record_state, "media": media})

    unique_selected_hashes = {
        item["sha256"] for row in rows for item in row["media"]
    }
    payload = {
        "status": "automated_prefilter_not_human_approval",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "name": "sha256_exact_match_against_prior_B_human_media_review",
            "formal_approval": False,
            "note": "Low-risk prefilter results still require B human confirmation.",
        },
        "inputs": {
            "dataset": str(dataset_path),
            "manifest": str(manifest_path),
            "prior_media_review": str(prior_path),
            "media_root": str(media_root),
        },
        "summary": {
            "selected_records": len(selected_ids),
            "selected_media_occurrences": sum(len(row["media"]) for row in rows),
            "selected_unique_hashes": len(unique_selected_hashes),
            "prior_clean_records": len(prior_clean_ids),
            "prior_clean_unique_hashes": len(clean_hashes),
            "prior_risk_records": len(prior_risk_ids),
            "prior_risk_hashes_used_as_blacklist": 0,
            "record_prefilter_counts": dict(sorted(record_counts.items())),
            "media_occurrence_prefilter_counts": dict(sorted(occurrence_counts.items())),
        },
        "items": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

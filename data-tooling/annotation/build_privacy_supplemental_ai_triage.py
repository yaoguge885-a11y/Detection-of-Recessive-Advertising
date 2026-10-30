#!/usr/bin/env python3
"""Build an AI first-pass triage for B's supplemental privacy queue.

The output is deliberately not a formal privacy approval. It separates items
that deserve detailed human secondary review from AI-low-risk items that still
require B's final human confirmation under the M1 protocol.
"""

from __future__ import annotations

import argparse
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


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_jsonl_by_id(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            post_id = str(record.get("post_id", ""))
            if not post_id:
                raise ValueError(f"missing post_id at line {line_number}")
            records[post_id] = record
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Build supplemental privacy AI triage")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--prefilter", required=True)
    parser.add_argument("--visual-review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    manifest_path = Path(args.manifest)
    prefilter_path = Path(args.prefilter)
    visual_review_path = Path(args.visual_review)
    output_path = Path(args.output)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite: {output_path}")

    manifest = load_json(manifest_path)
    prefilter = load_json(prefilter_path)
    visual = load_json(visual_review_path)
    records = load_jsonl_by_id(dataset_path)

    post_ids = [str(value) for value in manifest.get("post_ids", [])]
    if not post_ids or len(post_ids) != len(set(post_ids)):
        raise ValueError("manifest post_ids must be non-empty and unique")
    missing_records = [post_id for post_id in post_ids if post_id not in records]
    if missing_records:
        raise ValueError("manifest IDs missing from dataset: " + ", ".join(missing_records[:10]))

    prefilter_by_id = {
        str(item.get("post_id", "")): item
        for item in prefilter.get("items", [])
        if isinstance(item, dict)
    }
    visual_by_id = {
        str(item.get("post_id", "")): item
        for item in visual.get("record_overrides", [])
        if isinstance(item, dict)
    }
    if set(visual_by_id) - set(post_ids):
        raise ValueError("visual-review overrides are outside the manifest")

    items = []
    for number, post_id in enumerate(post_ids, start=1):
        record = records[post_id]
        pre = prefilter_by_id.get(post_id)
        if not pre:
            raise ValueError(f"missing prefilter row: {post_id}")
        media = [item for item in (record.get("media") or []) if isinstance(item, dict)]
        override = visual_by_id.get(post_id)

        if override:
            queue = str(override["queue"])
            recommendation = str(override.get("ai_recommendation", "uncertain"))
            confidence = str(override.get("confidence", "medium"))
            reason = str(override.get("risk", "visual boundary item"))
            suggested_action = str(override.get("suggested_action", ""))
            risk_media_refs = [str(value) for value in override.get("media_refs", [])]
        elif pre.get("prefilter") == "uncertain_no_local_media" and media:
            if not all(item.get("type") == "video" and not item.get("ref") and item.get("source_url") for item in media):
                raise ValueError(f"unexpected no-local-media shape: {post_id}")
            queue = "human_secondary_unavailable_video"
            recommendation = "uncertain"
            confidence = "not_assessed"
            reason = "Only a remote Bilibili video link is available; no local frames were available for visual privacy review."
            suggested_action = "Open the source video for human review, obtain reviewable frames, or exclude the record conservatively."
            risk_media_refs = []
        elif pre.get("prefilter") == "uncertain_no_local_media":
            queue = "ai_low_risk_quick_human_confirmation"
            recommendation = "allow"
            confidence = "high"
            reason = "The low-risk text scan found no medium/high/critical match and the record has no media."
            suggested_action = "B still performs final human confirmation before formal approval."
            risk_media_refs = []
        elif pre.get("prefilter") == "low_risk_all_media_previously_human_clean":
            queue = "ai_low_risk_quick_human_confirmation"
            recommendation = "allow"
            confidence = "high"
            reason = "Every local media file is an exact SHA-256 match to media previously marked clean by B."
            suggested_action = "B still performs final human confirmation before formal approval."
            risk_media_refs = []
        elif pre.get("prefilter") == "uncertain_unseen_media":
            queue = "ai_low_risk_quick_human_confirmation"
            recommendation = "allow"
            confidence = "medium"
            reason = "All previously unseen local media received thumbnail-level AI visual review and no privacy risk was identified for this record."
            suggested_action = "B still performs final human confirmation; GIF review was limited to the first frame."
            risk_media_refs = []
        else:
            raise ValueError(f"unknown prefilter state for {post_id}: {pre.get('prefilter')}")

        items.append(
            {
                "number": number,
                "post_id": post_id,
                "queue": queue,
                "ai_recommendation": recommendation,
                "confidence": confidence,
                "reason": reason,
                "suggested_action": suggested_action,
                "risk_media_refs": risk_media_refs,
                "source_prefilter": pre.get("prefilter"),
            }
        )

    counts = Counter(item["queue"] for item in items)
    recommendation_counts = Counter(item["ai_recommendation"] for item in items)
    payload = {
        "status": "ai_first_pass_not_human_approval",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": visual.get("reviewer", "AI"),
        "formal_approval": False,
        "protocol_note": "AI may sort and summarize, but B must provide final human approval for every record entering the formal pool.",
        "inputs": {
            "dataset": str(dataset_path),
            "manifest": str(manifest_path),
            "prefilter": str(prefilter_path),
            "visual_review": str(visual_review_path),
        },
        "coverage": visual.get("coverage", {}),
        "summary": {
            "total": len(items),
            "queue_counts": dict(sorted(counts.items())),
            "recommendation_counts": dict(sorted(recommendation_counts.items())),
            "detailed_human_secondary_total": sum(
                count for queue, count in counts.items() if queue.startswith("human_secondary_")
            ),
            "ai_low_risk_quick_confirmation_total": counts.get(
                "ai_low_risk_quick_human_confirmation", 0
            ),
        },
        "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

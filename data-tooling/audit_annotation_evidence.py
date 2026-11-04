"""Read-only audit of candidate evidence, with aggregate output by default.

File existence is not proof that the main content was captured or reviewed.
No URLs are fetched, no labels are generated, and no M1 gate is modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

VIDEO_HINT = re.compile(r"投稿了视频|视频作者|本视频|本期视频")
IMAGE_HINT = re.compile(r"查看大图|<图片\d+>")
COUNTS = (
    "records_with_video_entries", "records_with_local_video",
    "records_with_unpinned_remote_video", "records_with_missing_video_without_remote_entry",
    "video_hint_without_video_entry", "video_hint_without_any_media",
    "video_hint_with_only_nonvideo_media", "image_hint_without_image_entry",
    "records_without_local_media", "records_with_missing_local_refs", "records_with_unsafe_refs",
    "records_with_comments", "records_with_capture_status_field",
    "records_missing_published_at", "records_missing_creator_id", "records_missing_content_group_id",
)


def local_ref_status(ref, media_base: Path) -> str:
    if not isinstance(ref, str) or not ref.strip():
        return "not_declared"
    raw = ref.strip().replace("\\", "/")
    if "://" in raw or Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute():
        return "unsafe"
    try:
        path = (media_base / raw).resolve()
        path.relative_to(media_base.resolve())
    except (OSError, ValueError):
        return "unsafe"
    return "exists" if path.is_file() else "missing"


def audit_records(records: list[dict], media_base: Path) -> tuple[dict, list[dict]]:
    totals = {key: 0 for key in COUNTS}
    platforms, ref_states = Counter(), Counter()
    details, ids = [], []
    for row_number, row in enumerate(records, 1):
        pid = row.get("post_id")
        if not isinstance(pid, str) or not pid:
            raise ValueError(f"record {row_number} has no usable post_id")
        ids.append(pid)
        platform = str(row.get("platform") or "unknown")
        platforms[platform] += 1
        media = row.get("media") or []
        if not isinstance(media, list) or any(not isinstance(m, dict) for m in media):
            raise ValueError(f"record {row_number} has invalid media structure")
        statuses = [local_ref_status(m.get("ref"), media_base) for m in media]
        ref_states.update(statuses)
        video = [(m, status) for m, status in zip(media, statuses) if m.get("type") == "video"]
        video_hint = platform.startswith("bilibili") and bool(VIDEO_HINT.search(str(row.get("text") or row.get("content") or "")))
        image_hint = platform.startswith("bilibili") and bool(IMAGE_HINT.search(str(row.get("text") or row.get("content") or "")))
        remote = lambda m: isinstance(m.get("source_url"), str) and m["source_url"].startswith(("https://", "http://"))
        flags = {
            "records_with_video_entries": bool(video),
            "records_with_local_video": any(status == "exists" for _, status in video),
            "records_with_unpinned_remote_video": any(status != "exists" and remote(m) for m, status in video),
            "records_with_missing_video_without_remote_entry": any(status != "exists" and not remote(m) for m, status in video),
            "video_hint_without_video_entry": video_hint and not video,
            "video_hint_without_any_media": video_hint and not media,
            "video_hint_with_only_nonvideo_media": video_hint and bool(media) and not video,
            "image_hint_without_image_entry": image_hint and not any(m.get("type") == "image" for m in media),
            "records_without_local_media": "exists" not in statuses,
            "records_with_missing_local_refs": "missing" in statuses,
            "records_with_unsafe_refs": "unsafe" in statuses,
            "records_with_comments": bool(row.get("comments")),
            "records_with_capture_status_field": isinstance(row.get("capture_status"), dict) and bool(row["capture_status"]),
            "records_missing_published_at": not bool(row.get("published_at")),
            "records_missing_creator_id": not bool(row.get("blogger_id") or row.get("creator_id")),
            "records_missing_content_group_id": not bool(row.get("content_group_id")),
        }
        for key, value in flags.items():
            totals[key] += int(bool(value))
        attention = [key for key in (
            "records_with_unpinned_remote_video", "records_with_missing_video_without_remote_entry",
            "video_hint_without_video_entry", "image_hint_without_image_entry",
            "records_with_missing_local_refs", "records_with_unsafe_refs", "records_missing_published_at",
            "records_missing_creator_id", "records_missing_content_group_id") if flags[key]]
        if attention:
            details.append({"post_id": pid, "row_number": row_number, "flags": attention})
    frequencies = Counter(ids)
    summary = {"record_count": len(records), "unique_post_id_count": len(frequencies),
               "duplicate_row_count": len(records) - len(frequencies), "platform_counts": dict(platforms),
               "counts": totals, "media_reference_states": dict(ref_states),
               "records_with_attention_flags": len(details)}
    return summary, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--media-base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new aggregate JSON; no IDs/text/URLs")
    parser.add_argument("--manifest", type=Path, help="optional fixed manifest to audit only its sample IDs")
    parser.add_argument("--private-details", type=Path, help="optional PRIVATE per-ID flags, never publish")
    args = parser.parse_args()
    outputs = [p for p in (args.output, args.private_details) if p is not None]
    if len({p.resolve() for p in outputs}) != len(outputs):
        parser.error("aggregate and private outputs must be different files")
    for p in outputs:
        if p.exists():
            parser.error(f"refusing to overwrite output: {p}")
    if not args.media_base.is_dir():
        parser.error("media base must be an existing directory")
    raw = args.input.read_bytes()
    rows = []
    for number, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {number}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL line {number} must be an object")
            rows.append(record)
    input_count = len(rows)
    manifest_sha = None
    if args.manifest:
        manifest_raw = args.manifest.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8-sig"))
        ids = [item["post_id"] for item in manifest["items"]]
        if len(set(ids)) != len(ids):
            raise ValueError("manifest contains duplicate IDs")
        wanted = set(ids)
        selected = [row for row in rows if row.get("post_id") in wanted]
        if {row.get("post_id") for row in selected} != wanted:
            raise ValueError("manifest references records absent from input")
        rows = selected
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    summary, details = audit_records(rows, args.media_base)
    fingerprint = hashlib.sha256(raw).hexdigest()
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != fingerprint:
        raise ValueError("input changed during the audit; repeat on a fixed snapshot")
    report = {"schema_version": "m1_annotation_evidence_audit_v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "status": "read_only_evidence_inventory", "formal_evidence": False,
              "input_sha256": fingerprint, "input_record_count": input_count, "manifest_sha256": manifest_sha,
              "labels_created": 0, "network_requests": 0, "source_modified": False,
              "interpretation": {
                  "video_and_image_hints": "Heuristic collection-gap flags, not proof that content is missing; inspect flagged records.",
                  "remote_video": "A URL is not a pinned local video and has not been tested for accessibility.",
                  "local_media": "File existence does not prove substantive content, full evidence, or human viewing.",
                  "capture_status": "Presence of this field does not itself prove complete disclosure or comment collection.",
                  "counts_overlap": True,
              }, **summary}
    for p in outputs:
        p.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    if args.private_details:
        with args.private_details.open("x", encoding="utf-8") as f:
            json.dump({"private": True, "input_sha256": fingerprint, "items": details}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(json.dumps({"output": str(args.output), "record_count": summary["record_count"],
                      "records_with_attention_flags": summary["records_with_attention_flags"],
                      "formal_evidence": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

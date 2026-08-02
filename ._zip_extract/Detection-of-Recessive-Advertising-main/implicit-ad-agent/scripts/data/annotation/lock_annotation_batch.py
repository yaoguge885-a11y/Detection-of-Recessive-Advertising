#!/usr/bin/env python3
"""Create an auditable, private sample manifest for blind annotation batches.

The manifest contains only post IDs and aggregate distributions.  It is intended
for ``data/interim/annotations/`` (which is Git-ignored) and must not be used to
turn an unapproved candidate batch into a formal annotation batch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load a strict JSONL stream and reject malformed records."""
    records: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"record at line {line_number} is not an object")
        records.append(record)
    return records


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guide_version(guide_path: Path) -> str:
    match = re.search(
        r"(?:指南|guide)\s*v?([0-9]+(?:\.[0-9]+)*)",
        guide_path.read_text(encoding="utf-8-sig"),
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("guide version was not found in the guide heading")
    return match.group(1)


def _media_state(record: Mapping[str, Any]) -> str:
    media = record.get("media")
    if not isinstance(media, list) or not media:
        return "missing"
    return "available" if any(item.get("ref") for item in media if isinstance(item, dict)) else "missing"


def _creator_key(record: Mapping[str, Any]) -> str:
    for field in ("blogger_id", "creator_id_hash", "creator_id"):
        value = record.get(field)
        if value:
            return str(value)
    return "missing_creator"


def _validated_candidates(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for record in records:
        post_id = str(record.get("post_id", ""))
        if not post_id:
            raise ValueError("candidate record without post_id")
        if post_id in seen:
            raise ValueError(f"duplicate candidate post_id: {post_id}")
        seen.add(post_id)
        candidates.append(dict(record))
    return candidates


def _select_one_per_group(
    records: Sequence[Dict[str, Any]],
    key_fn: Any,
    required_values: Sequence[str],
    selected: List[Dict[str, Any]],
    selected_ids: Set[str],
    rng: random.Random,
) -> None:
    for required_value in required_values:
        if any(key_fn(record) == required_value for record in selected):
            continue
        choices = [
            record for record in records
            if key_fn(record) == required_value and str(record["post_id"]) not in selected_ids
        ]
        if not choices:
            raise ValueError(f"required coverage value is unavailable: {required_value}")
        chosen = rng.choice(choices)
        selected.append(chosen)
        selected_ids.add(str(chosen["post_id"]))


def choose_sample(
    candidates: Sequence[Dict[str, Any]],
    *,
    count: int,
    seed: int,
    excluded_ids: Set[str],
    required_platforms: Sequence[str] = (),
    required_media_states: Sequence[str] = (),
    required_post_ids: Sequence[str] = (),
) -> List[Dict[str, Any]]:
    """Select a deterministic, creator-balanced sample without excluded IDs."""
    available = [record for record in candidates if str(record["post_id"]) not in excluded_ids]
    if count <= 0:
        raise ValueError("sample count must be positive")
    if len(available) < count:
        raise ValueError(f"only {len(available)} non-overlapping candidates are available")

    anchor_ids = list(required_post_ids)
    if len(set(anchor_ids)) != len(anchor_ids):
        raise ValueError("required post IDs must not contain duplicates")
    if len(anchor_ids) > count:
        raise ValueError("sample count is smaller than required post ID coverage")
    available_by_id = {str(record["post_id"]): record for record in available}
    unavailable_anchors = [post_id for post_id in anchor_ids if post_id not in available_by_id]
    if unavailable_anchors:
        raise ValueError(
            "required post IDs are missing from eligible candidates: "
            + ", ".join(sorted(unavailable_anchors))
        )

    rng = random.Random(seed)
    selected = [available_by_id[post_id] for post_id in anchor_ids]
    selected_ids = set(anchor_ids)
    _select_one_per_group(
        available,
        lambda record: str(record.get("platform", "unknown")),
        required_platforms,
        selected,
        selected_ids,
        rng,
    )
    _select_one_per_group(
        available,
        _media_state,
        required_media_states,
        selected,
        selected_ids,
        rng,
    )
    if len(selected) > count:
        raise ValueError("sample count is smaller than required coverage")

    by_creator: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in available:
        if str(record["post_id"]) not in selected_ids:
            by_creator[_creator_key(record)].append(record)
    creator_keys = list(by_creator)
    rng.shuffle(creator_keys)
    for creator in creator_keys:
        if len(selected) >= count:
            break
        choices = by_creator[creator]
        chosen = rng.choice(choices)
        selected.append(chosen)
        selected_ids.add(str(chosen["post_id"]))

    remainder = [record for record in available if str(record["post_id"]) not in selected_ids]
    rng.shuffle(remainder)
    selected.extend(remainder[: count - len(selected)])
    return selected


def _load_manifest_ids(path: Path) -> Set[str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    post_ids = payload.get("post_ids")
    if not isinstance(post_ids, list) or not all(isinstance(post_id, str) for post_id in post_ids):
        raise ValueError("previous manifest does not contain a valid post_ids list")
    return set(post_ids)


def build_manifest(
    *,
    candidates_path: Path,
    guide_path: Path,
    batch_id: str,
    count: int,
    seed: int,
    batch_kind: str,
    formal_second_round: bool,
    previous_manifest: Optional[Path] = None,
    required_platforms: Sequence[str] = (),
    required_media_states: Sequence[str] = (),
    required_post_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    if batch_kind not in {"pilot", "formal_kappa", "formal_gold", "calibration"}:
        raise ValueError(f"unsupported batch kind: {batch_kind}")
    if formal_second_round and batch_kind != "formal_kappa":
        raise ValueError("formal second round must use batch kind formal_kappa")
    if formal_second_round and previous_manifest is None:
        raise ValueError("formal second round requires a first-round manifest")

    candidates = _validated_candidates(load_jsonl(candidates_path))
    previous_ids = _load_manifest_ids(previous_manifest) if previous_manifest else set()
    sample = choose_sample(
        candidates,
        count=count,
        seed=seed,
        excluded_ids=previous_ids,
        required_platforms=required_platforms,
        required_media_states=required_media_states,
        required_post_ids=required_post_ids,
    )
    post_ids = sorted(str(record["post_id"]) for record in sample)
    overlap_count = len(set(post_ids) & previous_ids)
    if overlap_count:
        raise AssertionError("selected sample overlaps with the previous manifest")

    platform_counts = Counter(str(record.get("platform", "unknown")) for record in sample)
    media_state_counts = Counter(_media_state(record) for record in sample)
    creator_count = len({_creator_key(record) for record in sample})
    sample_fingerprint = hashlib.sha256("\n".join(post_ids).encode("utf-8")).hexdigest()
    return {
        "batch_id": batch_id,
        "batch_kind": batch_kind,
        "formal_second_round": formal_second_round,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "guide_version": _guide_version(guide_path),
        "guide_sha256": sha256_file(guide_path),
        "input_sha256": sha256_file(candidates_path),
        "sample_sha256": sample_fingerprint,
        "sample_count": len(post_ids),
        "post_ids": post_ids,
        "previous_manifest_sha256": sha256_file(previous_manifest) if previous_manifest else None,
        "overlap_with_previous_count": overlap_count,
        "platform_counts": dict(sorted(platform_counts.items())),
        "creator_count": creator_count,
        "media_state_counts": dict(sorted(media_state_counts.items())),
        "selection": {
            "seed": seed,
            "required_platforms": list(required_platforms),
            "required_media_states": list(required_media_states),
            "manual_include_count": len(required_post_ids),
            "manual_include_sha256": (
                hashlib.sha256("\n".join(sorted(required_post_ids)).encode("utf-8")).hexdigest()
                if required_post_ids
                else None
            ),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lock a private blind-annotation sample manifest")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--batch-kind", default="pilot", choices=("pilot", "formal_kappa", "formal_gold", "calibration"))
    parser.add_argument("--formal-second-round", action="store_true")
    parser.add_argument("--previous-manifest", type=Path)
    parser.add_argument("--require-platform", action="append", default=[])
    parser.add_argument("--require-media-state", action="append", choices=("available", "missing"), default=[])
    parser.add_argument(
        "--include-post-id",
        action="append",
        default=[],
        help="manually selected eligible candidate ID that must be in this private batch",
    )
    args = parser.parse_args(argv)

    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite locked manifest: {args.output}")
    manifest = build_manifest(
        candidates_path=args.candidates,
        guide_path=args.guide,
        batch_id=args.batch_id,
        count=args.count,
        seed=args.seed,
        batch_kind=args.batch_kind,
        formal_second_round=args.formal_second_round,
        previous_manifest=args.previous_manifest,
        required_platforms=args.require_platform,
        required_media_states=args.require_media_state,
        required_post_ids=args.include_post_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "post_ids"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

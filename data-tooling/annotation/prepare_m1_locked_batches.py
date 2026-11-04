#!/usr/bin/env python3
"""Freeze and export the four mutually exclusive M1 annotation batches."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lock_annotation_batch import build_manifest, sha256_file


BATCHES = (
    ("round1", "m1_round1_100_formal_3312_v1", 100, 101, "pilot", False),
    ("round2", "m1_round2_formal_150_formal_3312_v1", 150, 202, "formal_kappa", True),
    ("gold_control", "m1_gold_control_180_formal_3312_v1", 180, 303, "formal_gold", False),
    ("gold_assisted", "m1_gold_assisted_1620_formal_3312_v1", 1620, 404, "formal_gold", False),
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _cumulative_manifest(paths: Iterable[Path], output: Path) -> Path:
    sources = list(paths)
    ids: set[str] = set()
    for path in sources:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        post_ids = payload.get("post_ids")
        if not isinstance(post_ids, list) or not all(isinstance(item, str) for item in post_ids):
            raise ValueError(f"invalid post_ids in {path}")
        ids.update(post_ids)
    _write_json(
        output,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_manifests": [path.name for path in sources],
            "source_sha256": {path.name: sha256_file(path) for path in sources},
            "post_ids": sorted(ids),
        },
    )
    return output


def _load_source_lines(path: Path) -> tuple[dict[str, str], int]:
    by_id: dict[str, str] = {}
    count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        count += 1
        record = json.loads(line)
        post_id = str(record.get("post_id", ""))
        if not post_id:
            raise ValueError(f"candidate line {line_number} has no post_id")
        if post_id in by_id:
            raise ValueError(f"duplicate candidate post_id at line {line_number}")
        by_id[post_id] = line
    return by_id, count


def _export_batch(manifest_path: Path, source: dict[str, str], output: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    post_ids = manifest["post_ids"]
    missing = [post_id for post_id in post_ids if post_id not in source]
    if missing:
        raise ValueError(f"{manifest_path.name} contains {len(missing)} missing post IDs")
    output.write_text("\n".join(source[post_id] for post_id in post_ids) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    output_root: Path = args.output_root
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty batch directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_paths: dict[str, Path] = {}
    prior_manifest: Path | None = None
    for name, batch_id, count, seed, kind, formal_second_round in BATCHES:
        manifest_path = output_root / f"{name}_manifest.json"
        manifest = build_manifest(
            candidates_path=args.candidates,
            guide_path=args.guide,
            batch_id=batch_id,
            count=count,
            seed=seed,
            batch_kind=kind,
            formal_second_round=formal_second_round,
            previous_manifest=prior_manifest,
            required_platforms=("bilibili", "wechat_official_account"),
            required_media_states=("available",),
        )
        _write_json(manifest_path, manifest)
        manifest_paths[name] = manifest_path

        if name == "round1":
            prior_manifest = manifest_path
        elif name == "round2":
            prior_manifest = _cumulative_manifest(
                (manifest_paths["round1"], manifest_paths["round2"]),
                output_root / "exclude_round1_round2.json",
            )
        elif name == "gold_control":
            prior_manifest = _cumulative_manifest(
                (
                    manifest_paths["round1"],
                    manifest_paths["round2"],
                    manifest_paths["gold_control"],
                ),
                output_root / "exclude_round1_round2_control.json",
            )

    source, source_count = _load_source_lines(args.candidates)
    all_ids: set[str] = set()
    batch_summary: dict[str, Any] = {}
    for name, *_ in BATCHES:
        manifest_path = manifest_paths[name]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        post_ids = set(manifest["post_ids"])
        overlap = all_ids & post_ids
        if overlap:
            raise ValueError(f"batch overlap detected for {name}: {len(overlap)}")
        all_ids.update(post_ids)
        export_path = output_root / f"{name}.jsonl"
        _export_batch(manifest_path, source, export_path)
        batch_summary[name] = {
            "count": len(post_ids),
            "batch_id": manifest["batch_id"],
            "manifest_sha256": sha256_file(manifest_path),
            "jsonl_sha256": sha256_file(export_path),
            "platform_counts": manifest["platform_counts"],
            "media_state_counts": manifest["media_state_counts"],
        }

    expected_total = sum(item[2] for item in BATCHES)
    if len(all_ids) != expected_total:
        raise ValueError(f"expected {expected_total} unique IDs, got {len(all_ids)}")

    summary = {
        "status": "locked",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cohort": "formal_3312_v1",
        "candidate_count": source_count,
        "candidate_sha256": sha256_file(args.candidates),
        "guide_sha256": sha256_file(args.guide),
        "total_unique_locked": len(all_ids),
        "cross_batch_overlap_count": 0,
        "batches": batch_summary,
    }
    _write_json(output_root / "batch_lock_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

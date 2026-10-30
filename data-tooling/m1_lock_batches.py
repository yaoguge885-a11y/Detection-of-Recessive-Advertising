#!/usr/bin/env python3
"""Lock, export, and verify the four mutually exclusive M1 batches.

Formal mode requires a passed stage-3 formalization report.  ``--preflight``
exists only to exercise the deterministic selection/export pipeline before the
human and compliance gates close; every generated manifest and the summary are
marked non-formal.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


BATCHES = (
    ("round1", "m1_round1_100", 100, 101, "pilot", False),
    ("round2", "m1_round2_formal_150", 150, 202, "formal_kappa", True),
    ("gold_control", "m1_gold_control_180", 180, 303, "formal_gold", False),
    ("gold_assisted", "m1_gold_assisted_1620", 1620, 404, "formal_gold", False),
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def recorded_formal_candidate_sha(formalization: Mapping[str, Any]) -> str | None:
    """Read the candidate digest from current or legacy formalization schemas."""
    current = formalization.get("formal_candidates")
    if isinstance(current, Mapping) and current.get("sha256"):
        return str(current["sha256"]).lower()
    legacy = formalization.get("files")
    if isinstance(legacy, Mapping) and legacy.get("formal_eligible_candidates.jsonl"):
        return str(legacy["formal_eligible_candidates.jsonl"]).lower()
    return None


def load_lock_module(script_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("m1_lock_annotation_batch", script_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load lock_annotation_batch module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_jsonl_index(path: Path) -> tuple[dict[str, str], list[str]]:
    index: dict[str, str] = {}
    errors: list[str] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        post_id = row.get("post_id") if isinstance(row, dict) else None
        if not isinstance(post_id, str) or not post_id:
            errors.append(f"line {line_number}: missing post_id")
            continue
        if post_id in index:
            errors.append(f"line {line_number}: duplicate post_id {post_id}")
            continue
        index[post_id] = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    return index, errors


def write_object(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_cumulative_manifest(
    *, source_manifests: list[Path], output_path: Path, preflight: bool
) -> None:
    ids: set[str] = set()
    for path in source_manifests:
        manifest = load_object(path)
        post_ids = manifest.get("post_ids")
        if not isinstance(post_ids, list):
            raise ValueError(f"{path}: manifest.post_ids must be a list")
        ids.update(str(post_id) for post_id in post_ids)
    write_object(
        output_path,
        {
            "status": "preflight_not_formal" if preflight else "locked",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_manifests": [str(path) for path in source_manifests],
            "post_ids": sorted(ids),
        },
    )


def export_batch(
    *, manifest_path: Path, source_index: Mapping[str, str], output_path: Path
) -> dict[str, Any]:
    manifest = load_object(manifest_path)
    post_ids = manifest.get("post_ids")
    if not isinstance(post_ids, list) or not all(
        isinstance(post_id, str) and post_id for post_id in post_ids
    ):
        raise ValueError(f"{manifest_path}: manifest.post_ids is invalid")
    if len(set(post_ids)) != len(post_ids):
        raise ValueError(f"{manifest_path}: duplicate post_ids")
    missing = [post_id for post_id in post_ids if post_id not in source_index]
    if missing:
        raise ValueError(f"{manifest_path}: source is missing post_ids {missing[:5]}")
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for post_id in post_ids:
            handle.write(source_index[post_id])
            handle.write("\n")
    return {
        "count": len(post_ids),
        "sha256": sha256_file(output_path),
    }


def lock_batches(
    *,
    candidates_path: Path,
    guide_path: Path,
    lock_script_path: Path,
    output_dir: Path,
    formalization_report_path: Path | None,
    preflight: bool,
) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output directory: {output_dir}")
    if not preflight:
        if formalization_report_path is None:
            raise ValueError("formal mode requires --formalization-report")
        formalization = load_object(formalization_report_path)
        if formalization.get("status") != "formal_materialized":
            raise ValueError("stage-3 formalization report is not formal_materialized")
        recorded = recorded_formal_candidate_sha(formalization)
        if str(recorded or "").lower() != sha256_file(candidates_path):
            raise ValueError("candidate SHA-256 does not match the formalization report")

    source_index, source_errors = load_jsonl_index(candidates_path)
    if source_errors:
        raise ValueError(source_errors[0])
    if len(source_index) < sum(batch[2] for batch in BATCHES):
        raise ValueError(
            f"candidate pool has {len(source_index)} records; at least 2050 are required"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    lock_module = load_lock_module(lock_script_path)
    manifests: list[Path] = []
    batch_reports: dict[str, Any] = {}
    owner: dict[str, str] = {}

    for name, batch_id, count, seed, kind, formal_second_round in BATCHES:
        manifest_path = output_dir / f"{name}_manifest.json"
        previous_path: Path | None = None
        if manifests:
            previous_path = output_dir / f"exclude_before_{name}.json"
            write_cumulative_manifest(
                source_manifests=manifests,
                output_path=previous_path,
                preflight=preflight,
            )
        manifest = lock_module.build_manifest(
            candidates_path=candidates_path,
            guide_path=guide_path,
            batch_id=batch_id,
            count=count,
            seed=seed,
            batch_kind=kind,
            formal_second_round=formal_second_round,
            previous_manifest=previous_path,
            required_platforms=("bilibili", "wechat_official_account"),
            required_media_states=("available",),
            required_post_ids=(),
        )
        manifest["status"] = "preflight_not_formal" if preflight else "locked"
        write_object(manifest_path, manifest)
        manifests.append(manifest_path)

        for post_id in manifest["post_ids"]:
            if post_id in owner:
                raise ValueError(
                    f"batch overlap: {post_id} is in {owner[post_id]} and {name}"
                )
            owner[post_id] = name

        export_path = output_dir / f"{name}.jsonl"
        export = export_batch(
            manifest_path=manifest_path,
            source_index=source_index,
            output_path=export_path,
        )
        batch_reports[name] = {
            "batch_id": batch_id,
            "expected_count": count,
            "manifest_count": manifest["sample_count"],
            "manifest_sha256": sha256_file(manifest_path),
            "export_count": export["count"],
            "export_sha256": export["sha256"],
            "platform_counts": manifest["platform_counts"],
            "media_state_counts": manifest["media_state_counts"],
            "creator_count": manifest["creator_count"],
        }

    if len(owner) != 2050:
        raise ValueError(f"four batches contain {len(owner)} unique IDs, expected 2050")
    summary = {
        "status": "preflight_not_formal" if preflight else "locked",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_path": str(candidates_path),
        "candidate_sha256": sha256_file(candidates_path),
        "guide_path": str(guide_path),
        "guide_sha256": sha256_file(guide_path),
        "batch_count": 4,
        "unique_post_id_count": len(owner),
        "overlap_count": 0,
        "batches": batch_reports,
    }
    write_object(output_dir / "batch_lock_report.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Lock and export four M1 batches")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--lock-script", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--formalization-report", type=Path)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        report = lock_batches(
            candidates_path=args.candidates,
            guide_path=args.guide,
            lock_script_path=args.lock_script,
            output_dir=args.output_dir,
            formalization_report_path=args.formalization_report,
            preflight=args.preflight,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

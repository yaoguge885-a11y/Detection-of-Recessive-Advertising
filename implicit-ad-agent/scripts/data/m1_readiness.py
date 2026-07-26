#!/usr/bin/env python3
"""Audit local M1 assets and evaluate the formal P3 entry gate.

Reports contain aggregate counts only. Raw text, source URLs, creator IDs,
annotator IDs, and sensitive matches are intentionally excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


THREE_CLASS_LABELS = {"明广", "暗广", "非广"}
GUIDE_CASE_PATTERN = re.compile(r"^###\s+(EC-\d{2})\b", re.MULTILINE)


def load_json_stream(path: Path) -> list[dict[str, Any]]:
    """Load standard JSONL or a whitespace-separated stream of JSON objects."""
    text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        value, position = decoder.raw_decode(text, position)
        if not isinstance(value, dict):
            raise TypeError(f"record {len(records)} must be an object")
        records.append(value)
    return records


def count_guide_edge_cases(path: Path) -> int:
    """Count unique structured edge-case IDs in an annotation guide."""
    return len(set(GUIDE_CASE_PATTERN.findall(path.read_text(encoding="utf-8"))))


def _annotation_post_id(record: Mapping[str, Any]) -> str | None:
    post_id = record.get("post_id")
    if post_id:
        return str(post_id)
    post = record.get("post")
    if isinstance(post, Mapping) and post.get("post_id"):
        return str(post["post_id"])
    return None


def _candidate_path(dataset_root: Path) -> Path:
    for relative in (
        "anonymized_postsn.jsonl",
        "anonymized_posts.jsonl",
        "interim/candidates_v1_dedup.jsonl",
        "interim/candidates_v1.jsonl",
    ):
        candidate = dataset_root / relative
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("no supported candidate JSON/JSONL file found")


def _relative_media_ref(ref: str) -> str:
    normalized = PurePosixPath(ref.replace("\\", "/")).as_posix()
    return normalized[6:] if normalized.lower().startswith("media/") else normalized


def _media_inventory(dataset_root: Path) -> tuple[set[str], set[str], int]:
    media_root = dataset_root / "media"
    disk_files: set[str] = set()
    zip_files: set[str] = set()
    structured_zip_entries = 0
    if not media_root.is_dir():
        return disk_files, zip_files, structured_zip_entries

    for path in media_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() == ".zip":
            continue
        disk_files.add(path.relative_to(media_root).as_posix().lower())

    structured_suffixes = {".json", ".jsonl", ".csv", ".tsv", ".txt", ".md"}
    for archive_path in media_root.rglob("*.zip"):
        with zipfile.ZipFile(archive_path) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                relative = PurePosixPath(item.filename).as_posix().lower()
                zip_files.add(relative)
                if PurePosixPath(relative).suffix in structured_suffixes:
                    structured_zip_entries += 1
    return disk_files, zip_files, structured_zip_entries


def _safe_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_dataset(dataset_root: Path) -> dict[str, Any]:
    """Return a privacy-safe aggregate audit for a local dataset directory."""
    dataset_root = dataset_root.resolve()
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"dataset root is not a directory: {dataset_root}")

    candidate_path = _candidate_path(dataset_root)
    candidates = load_json_stream(candidate_path)
    post_ids = [str(record["post_id"]) for record in candidates if record.get("post_id")]
    creator_ids = {
        str(record["blogger_id"]) for record in candidates if record.get("blogger_id")
    }
    platform_counts = Counter(
        str(record["platform"]) for record in candidates if record.get("platform")
    )

    annotation_files = sorted(
        path
        for path in (dataset_root / "annotations").glob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}
    ) if (dataset_root / "annotations").is_dir() else []
    annotation_sets: list[set[str]] = []
    annotation_rows: list[int] = []
    valid_three_class_rows: list[int] = []
    for path in annotation_files:
        records = load_json_stream(path)
        annotation_records = [
            record
            for record in records
            if _annotation_post_id(record) is not None and "label" in record
        ]
        annotation_rows.append(len(annotation_records))
        annotation_sets.append(
            {
                post_id
                for record in annotation_records
                if (post_id := _annotation_post_id(record)) is not None
            }
        )
        valid_three_class_rows.append(
            sum(
                record.get("label") in THREE_CLASS_LABELS
                for record in annotation_records
            )
        )
    common_posts = (
        len(set.intersection(*annotation_sets)) if len(annotation_sets) >= 2 else 0
    )

    disk_media, zip_media, structured_zip_entries = _media_inventory(dataset_root)
    refs = [
        _relative_media_ref(str(media["ref"])).lower()
        for record in candidates
        for media in (record.get("media") or [])
        if isinstance(media, Mapping) and media.get("ref")
    ]
    available_media = disk_media | zip_media
    unique_refs = set(refs)

    terms_checked = 0
    privacy_counts: Counter[str] = Counter()
    for record in candidates:
        provenance = record.get("provenance")
        if isinstance(provenance, Mapping) and provenance.get("terms_checked_at"):
            terms_checked += 1
        collected = record.get("_collected")
        if isinstance(collected, Mapping) and collected.get("terms_checked_at"):
            terms_checked += 1
        privacy = record.get("privacy")
        if isinstance(privacy, Mapping):
            key = (
                f"anonymized={privacy.get('anonymized')},"
                f"contains_sensitive_data={privacy.get('contains_sensitive_data')}"
            )
            privacy_counts[key] += 1

    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_fingerprint": _safe_digest(candidate_path),
        "candidates": {
            "rows": len(candidates),
            "unique_posts": len(set(post_ids)),
            "duplicate_post_rows": len(post_ids) - len(set(post_ids)),
            "unique_creators": len(creator_ids),
            "platform_counts": dict(sorted(platform_counts.items())),
        },
        "annotations": {
            "file_count": len(annotation_files),
            "rows_per_file": annotation_rows,
            "unique_posts_per_file": [len(values) for values in annotation_sets],
            "common_posts": common_posts,
            "valid_three_class_rows_per_file": valid_three_class_rows,
        },
        "media": {
            "references": len(refs),
            "unique_references": len(unique_refs),
            "available_unique_references": len(unique_refs & available_media),
            "missing_unique_references": len(unique_refs - available_media),
            "disk_files": len(disk_media),
            "zip_files": len(zip_media),
            "structured_zip_entries": structured_zip_entries,
        },
        "compliance": {
            "terms_checked_records": terms_checked,
            "privacy_claim_counts": dict(sorted(privacy_counts.items())),
        },
    }


def _threshold_check(observed: Any, required: Any) -> dict[str, Any]:
    if observed is None:
        status = "missing"
    else:
        status = "passed" if observed >= required else "failed"
    return {"status": status, "observed": observed, "required": required}


def evaluate_m1_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate every authoritative M1 requirement without inferred passes."""
    candidate_check = _threshold_check(evidence.get("candidate_unique_count"), 3000)
    gold_check = _threshold_check(evidence.get("gold_count"), 1500)
    guide_check = _threshold_check(evidence.get("guide_edge_case_count"), 20)

    kappa = evidence.get("second_round_kappa")
    formal_round = evidence.get("second_round_formal")
    if kappa is None or formal_round is None:
        agreement_status = "missing"
    elif formal_round is not True:
        agreement_status = "review_required"
    else:
        agreement_status = "passed" if kappa >= 0.6 else "failed"
    agreement_check = {
        "status": agreement_status,
        "observed": kappa,
        "required": "formal second-round Cohen kappa >= 0.6",
    }

    creator_leakage = evidence.get("creator_leakage_count")
    duplicate_leakage = evidence.get("near_duplicate_leakage_count")
    if creator_leakage is None or duplicate_leakage is None:
        split_status = "missing"
    else:
        split_status = (
            "passed"
            if creator_leakage == 0 and duplicate_leakage == 0
            else "failed"
        )
    split_check = {
        "status": split_status,
        "observed": {
            "creator_leakage_count": creator_leakage,
            "near_duplicate_leakage_count": duplicate_leakage,
        },
        "required": "both counts equal 0",
    }

    privacy = evidence.get("privacy_approved")
    terms = evidence.get("terms_complete")
    if privacy is None or terms is None:
        compliance_status = "missing"
    elif privacy is True and terms is True:
        compliance_status = "passed"
    else:
        compliance_status = "review_required"
    compliance_check = {
        "status": compliance_status,
        "observed": {
            "privacy_approved": privacy,
            "terms_complete": terms,
        },
        "required": "privacy approved and source terms complete",
    }

    dataset_card = evidence.get("dataset_card_complete")
    if dataset_card is None:
        dataset_card_status = "missing"
    else:
        dataset_card_status = "passed" if dataset_card is True else "failed"
    dataset_card_check = {
        "status": dataset_card_status,
        "observed": dataset_card,
        "required": True,
    }

    checks = {
        "candidate_pool": candidate_check,
        "gold": gold_check,
        "annotation_guide": guide_check,
        "agreement": agreement_check,
        "split_leakage": split_check,
        "compliance": compliance_check,
        "dataset_card": dataset_card_check,
    }
    return {
        "gate": "M1",
        "passed": all(check["status"] == "passed" for check in checks.values()),
        "checks": checks,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object in {path}")
    return value


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _gate_evidence(args: argparse.Namespace) -> dict[str, Any]:
    audit = _read_json(args.audit)
    agreement = _read_json(args.agreement)
    card_status = _read_json(args.dataset_card_status)
    evidence: dict[str, Any] = {
        "candidate_unique_count": audit.get("candidates", {}).get("unique_posts"),
        "gold_count": 0,
        "guide_edge_case_count": count_guide_edge_cases(args.guide),
        "second_round_kappa": agreement.get("kappa"),
        "second_round_formal": agreement.get("formal_second_round", False),
        "creator_leakage_count": None,
        "near_duplicate_leakage_count": None,
        "privacy_approved": card_status.get("privacy_approved"),
        "terms_complete": card_status.get("terms_complete"),
        "dataset_card_complete": card_status.get("dataset_card_complete"),
    }
    if args.gold_report:
        evidence["gold_count"] = _read_json(args.gold_report).get("gold_count")
    if args.split_report:
        split = _read_json(args.split_report)
        evidence["creator_leakage_count"] = split.get("creator_leakage_count")
        evidence["near_duplicate_leakage_count"] = split.get(
            "near_duplicate_leakage_count"
        )
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M1 dataset audit and phase gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="audit an external dataset")
    audit_parser.add_argument("--dataset-root", type=Path, required=True)
    audit_parser.add_argument("--output", type=Path, required=True)

    gate_parser = subparsers.add_parser("gate", help="evaluate the formal M1 gate")
    gate_parser.add_argument("--audit", type=Path, required=True)
    gate_parser.add_argument("--guide", type=Path, required=True)
    gate_parser.add_argument("--agreement", type=Path, required=True)
    gate_parser.add_argument("--dataset-card-status", type=Path, required=True)
    gate_parser.add_argument("--gold-report", type=Path)
    gate_parser.add_argument("--split-report", type=Path)
    gate_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        report = audit_dataset(args.dataset_root)
        _write_report(args.output, report)
        return 0

    gate_report = evaluate_m1_gate(_gate_evidence(args))
    _write_report(args.output, gate_report)
    return 0 if gate_report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

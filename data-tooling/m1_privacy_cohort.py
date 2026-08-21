#!/usr/bin/env python3
"""Audit and materialize the conservative M1 privacy cohort.

The default ``audit`` command is read-only.  ``materialize`` is intentionally
gated: it refuses to write a formal cohort unless the completed B spotcheck has
passed validation and the supplied source dataset hash exactly matches the hash
recorded in the cohort approval.  Use ``--preview`` only for non-formal dry-run
artifacts; preview outputs are marked as such and cannot be mistaken for formal
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


KNOWN_MEDIA_REVIEW = "privacy_media_review_B.json"
KNOWN_SUPPLEMENTAL_REVIEW = "privacy_supplemental_visual_secondary_review_B.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def duplicate_values(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
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
        if not isinstance(row, dict):
            errors.append(f"line {line_number}: record is not an object")
            continue
        post_id = row.get("post_id")
        if not isinstance(post_id, str) or not post_id:
            errors.append(f"line {line_number}: missing post_id")
            continue
        records.append(row)
    return records, errors


def _review_ids(
    path: Path | None,
    *,
    expected_decisions: set[str],
    decision_fields: tuple[str, ...] = ("decision", "status", "result"),
) -> set[str]:
    if path is None:
        return set()
    payload = load_object(path)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"{path}: items must be a list")
    found: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        decision = next(
            (str(item.get(field)) for field in decision_fields if item.get(field)), ""
        )
        post_id = item.get("post_id")
        if decision in expected_decisions and isinstance(post_id, str) and post_id:
            found.add(post_id)
    return found


def audit_cohort(
    *,
    dataset_path: Path,
    approval_path: Path,
    allowlist_path: Path,
    spotcheck_manifest_path: Path | None = None,
    media_review_path: Path | None = None,
    supplemental_review_path: Path | None = None,
) -> dict[str, Any]:
    approval = load_object(approval_path)
    allowlist = load_object(allowlist_path)
    records, dataset_errors = load_jsonl(dataset_path)
    errors = list(dataset_errors)
    warnings: list[str] = []

    dataset_ids = [str(record["post_id"]) for record in records]
    dataset_duplicates = duplicate_values(dataset_ids)
    if dataset_duplicates:
        errors.append(f"dataset contains duplicate post_ids: {dataset_duplicates[:5]}")
    dataset_set = set(dataset_ids)

    approved_raw = approval.get("post_ids")
    if not isinstance(approved_raw, list) or not all(
        isinstance(post_id, str) and post_id for post_id in approved_raw
    ):
        errors.append("approval.post_ids must be a list of non-empty strings")
        approved_ids: list[str] = []
    else:
        approved_ids = list(approved_raw)

    excluded_raw = approval.get("excluded")
    if not isinstance(excluded_raw, list):
        errors.append("approval.excluded must be a list")
        excluded_items: list[Mapping[str, Any]] = []
    else:
        excluded_items = [item for item in excluded_raw if isinstance(item, dict)]
        if len(excluded_items) != len(excluded_raw):
            errors.append("every approval.excluded entry must be an object")

    excluded_ids = [
        str(item.get("post_id"))
        for item in excluded_items
        if isinstance(item.get("post_id"), str) and item.get("post_id")
    ]
    for label, values in (("approved", approved_ids), ("excluded", excluded_ids)):
        duplicates = duplicate_values(values)
        if duplicates:
            errors.append(f"{label} cohort contains duplicate post_ids: {duplicates[:5]}")

    approved_set = set(approved_ids)
    excluded_set = set(excluded_ids)
    overlap = sorted(approved_set & excluded_set)
    if overlap:
        errors.append(f"approved/excluded overlap: {overlap[:5]}")
    missing_from_partition = sorted(dataset_set - approved_set - excluded_set)
    unexpected_partition_ids = sorted((approved_set | excluded_set) - dataset_set)
    if missing_from_partition:
        errors.append(
            f"partition misses {len(missing_from_partition)} dataset IDs: "
            f"{missing_from_partition[:5]}"
        )
    if unexpected_partition_ids:
        errors.append(
            f"partition contains {len(unexpected_partition_ids)} IDs not in dataset: "
            f"{unexpected_partition_ids[:5]}"
        )

    allowlist_ids_raw = allowlist.get("post_ids")
    if not isinstance(allowlist_ids_raw, list) or not all(
        isinstance(post_id, str) and post_id for post_id in allowlist_ids_raw
    ):
        errors.append("allowlist.post_ids must be a list of non-empty strings")
        allowlist_ids: list[str] = []
    else:
        allowlist_ids = list(allowlist_ids_raw)
    if duplicate_values(allowlist_ids):
        errors.append("allowlist contains duplicate post_ids")
    if set(allowlist_ids) != approved_set:
        errors.append("allowlist post_ids do not exactly equal approval.post_ids")
    if allowlist.get("total_approved") != len(allowlist_ids):
        errors.append("allowlist.total_approved does not equal allowlist post_id count")

    actual_dataset_sha = sha256_file(dataset_path)
    approval_dataset_sha = str(approval.get("dataset_sha256", "")).lower()
    dataset_hash_matches_approval = approval_dataset_sha == actual_dataset_sha
    if not dataset_hash_matches_approval:
        warnings.append(
            "supplied dataset hash does not match approval.dataset_sha256; the ID "
            "partition can be audited, but this dataset cannot be used for formal "
            "materialization"
        )

    reason_counts = Counter(str(item.get("reason", "")) for item in excluded_items)

    media_risk_ids = _review_ids(
        media_review_path, expected_decisions={"risk"}
    )
    supplemental_redact_ids = _review_ids(
        supplemental_review_path, expected_decisions={"redact", "exclude"}
    )
    missing_known_media_risks = sorted(media_risk_ids - excluded_set)
    missing_supplemental_risks = sorted(supplemental_redact_ids - excluded_set)
    if missing_known_media_risks:
        errors.append(
            f"{len(missing_known_media_risks)} known media-risk IDs are not excluded: "
            f"{missing_known_media_risks[:5]}"
        )
    if missing_supplemental_risks:
        errors.append(
            f"{len(missing_supplemental_risks)} supplemental redact/exclude IDs are "
            f"not excluded: {missing_supplemental_risks[:5]}"
        )

    spotcheck_summary: dict[str, Any] | None = None
    if spotcheck_manifest_path is not None:
        spotcheck = load_object(spotcheck_manifest_path)
        spotcheck_ids = spotcheck.get("post_ids", [])
        if not isinstance(spotcheck_ids, list):
            errors.append("spotcheck manifest post_ids must be a list")
            spotcheck_ids = []
        spot_set = {str(post_id) for post_id in spotcheck_ids}
        uncovered = sorted(spot_set - approved_set - excluded_set)
        if uncovered:
            errors.append(
                f"spotcheck manifest contains {len(uncovered)} IDs outside the partition: "
                f"{uncovered[:5]}"
            )
        spotcheck_summary = {
            "sample_size": len(spotcheck_ids),
            "in_approved": len(spot_set & approved_set),
            "in_excluded": len(spot_set & excluded_set),
            "uncovered": len(uncovered),
        }

    return {
        "audit": "m1_privacy_cohort_v1",
        "partition_passed": not errors,
        "formal_materialization_ready": not errors and dataset_hash_matches_approval,
        "dataset": {
            "path": str(dataset_path),
            "sha256": actual_dataset_sha,
            "approval_dataset_sha256": approval_dataset_sha or None,
            "hash_matches_approval": dataset_hash_matches_approval,
            "record_count": len(dataset_ids),
            "duplicate_post_id_count": len(dataset_duplicates),
        },
        "cohort": {
            "approval_path": str(approval_path),
            "approval_sha256": sha256_file(approval_path),
            "allowlist_path": str(allowlist_path),
            "allowlist_sha256": sha256_file(allowlist_path),
            "approved_count": len(approved_ids),
            "excluded_count": len(excluded_ids),
            "partition_count": len(approved_set | excluded_set),
            "overlap_count": len(overlap),
            "uncovered_dataset_count": len(missing_from_partition),
            "unexpected_partition_count": len(unexpected_partition_ids),
            "allowlist_matches_approved": set(allowlist_ids) == approved_set,
            "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        },
        "known_risks": {
            "media_risk_count": len(media_risk_ids),
            "media_risks_excluded": len(media_risk_ids & excluded_set),
            "supplemental_redact_or_exclude_count": len(supplemental_redact_ids),
            "supplemental_risks_excluded": len(
                supplemental_redact_ids & excluded_set
            ),
        },
        "spotcheck_manifest": spotcheck_summary,
        "errors": errors,
        "warnings": warnings,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def materialize(
    *,
    dataset_path: Path,
    approval_path: Path,
    allowlist_path: Path,
    spotcheck_validation_path: Path,
    output_dir: Path,
    preview: bool,
    audit_options: dict[str, Any],
) -> dict[str, Any]:
    audit = audit_cohort(
        dataset_path=dataset_path,
        approval_path=approval_path,
        allowlist_path=allowlist_path,
        **audit_options,
    )
    validation = load_object(spotcheck_validation_path)
    validation_passed = validation.get("passed") is True
    if not audit["partition_passed"]:
        raise ValueError("cohort partition audit failed; refusing to materialize")
    if not preview and not audit["formal_materialization_ready"]:
        raise ValueError(
            "dataset hash does not match approval; refusing formal materialization"
        )
    if not preview and not validation_passed:
        raise ValueError(
            "completed B spotcheck validation has not passed; refusing formal materialization"
        )

    approval = load_object(approval_path)
    approved_ids = set(str(post_id) for post_id in approval["post_ids"])
    records, errors = load_jsonl(dataset_path)
    if errors:
        raise ValueError(errors[0])
    selected = [record for record in records if str(record["post_id"]) in approved_ids]
    selected_ids = {str(record["post_id"]) for record in selected}
    missing = sorted(approved_ids - selected_ids)
    if missing:
        raise ValueError(f"dataset is missing approved post_ids: {missing[:5]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / "formal_eligible_candidates.jsonl"
    approval_output = output_dir / "privacy_approval.json"
    allowlist_output = output_dir / "public_allowlist.json"
    report_output = output_dir / "formalization_report.json"
    for path in (candidates_path, approval_output, allowlist_output, report_output):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")

    with candidates_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    approval_output.write_bytes(approval_path.read_bytes())
    allowlist_output.write_bytes(allowlist_path.read_bytes())
    report = {
        "status": "preview_not_formal" if preview else "formal_materialized",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "spotcheck_validation_passed": validation_passed,
        "candidate_count": len(selected),
        "files": {
            "formal_eligible_candidates.jsonl": sha256_file(candidates_path),
            "privacy_approval.json": sha256_file(approval_output),
            "public_allowlist.json": sha256_file(allowlist_output),
        },
        "audit": audit,
    }
    _write_json(report_output, report)
    return report


def reconcile_spotcheck(
    *,
    dataset_path: Path,
    approval_path: Path,
    allowlist_path: Path,
    spotcheck_review_path: Path,
    spotcheck_validation_path: Path,
    supplemental_review_path: Path | None,
    media_review_path: Path | None,
    output_dir: Path,
) -> dict[str, Any]:
    """Create a non-formal conservative cohort proposal after B's spotcheck."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to write into non-empty output dir: {output_dir}")
    validation = load_object(spotcheck_validation_path)
    if validation.get("passed") is not True:
        raise ValueError("spotcheck validation has not passed")
    expected_review_sha = str(
        (validation.get("review") or {}).get("sha256", "")
        if isinstance(validation.get("review"), dict)
        else ""
    ).lower()
    actual_review_sha = sha256_file(spotcheck_review_path)
    if expected_review_sha != actual_review_sha:
        raise ValueError("spotcheck review SHA-256 does not match validation report")

    base_audit = audit_cohort(
        dataset_path=dataset_path,
        approval_path=approval_path,
        allowlist_path=allowlist_path,
        media_review_path=media_review_path,
    )
    if not base_audit["partition_passed"]:
        raise ValueError("base cohort partition audit failed")

    approval = load_object(approval_path)
    review = load_object(spotcheck_review_path)
    if review.get("status") != "completed_B_spotcheck_10pct_review":
        raise ValueError("spotcheck review is not completed")
    review_items = review.get("items")
    if not isinstance(review_items, list):
        raise ValueError("spotcheck review.items must be a list")

    approved_order = [str(post_id) for post_id in approval["post_ids"]]
    approved_set = set(approved_order)
    excluded_items = [dict(item) for item in approval["excluded"]]
    excluded_by_id = {str(item["post_id"]): item for item in excluded_items}
    moved_by_spotcheck: list[str] = []
    spotcheck_allow_already_excluded: list[str] = []
    spotcheck_risk_already_excluded: list[str] = []

    for item in review_items:
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("post_id", ""))
        decision = item.get("decision")
        if decision in {"redact", "exclude"}:
            if post_id in approved_set:
                approved_set.remove(post_id)
                moved_by_spotcheck.append(post_id)
                excluded_by_id[post_id] = {
                    "post_id": post_id,
                    "decision": "exclude",
                    "reason": (
                        "conservative exclusion: B 10% spotcheck decision "
                        + str(decision)
                    ),
                }
            elif post_id in excluded_by_id:
                spotcheck_risk_already_excluded.append(post_id)
        elif decision == "allow" and post_id in excluded_by_id:
            # A spotcheck allow decision does not override an independent scanner,
            # zero-byte-media, or earlier conservative exclusion reason.
            spotcheck_allow_already_excluded.append(post_id)

    supplemental_moved: list[str] = []
    supplemental_already_excluded: list[str] = []
    supplemental_risk_ids = _review_ids(
        supplemental_review_path, expected_decisions={"redact", "exclude"}
    )
    for post_id in sorted(supplemental_risk_ids):
        if post_id in approved_set:
            approved_set.remove(post_id)
            supplemental_moved.append(post_id)
            excluded_by_id[post_id] = {
                "post_id": post_id,
                "decision": "exclude",
                "reason": "conservative exclusion: B supplemental media decision redact",
            }
        elif post_id in excluded_by_id:
            supplemental_already_excluded.append(post_id)

    final_approved = [post_id for post_id in approved_order if post_id in approved_set]
    final_excluded = list(excluded_by_id.values())
    final_excluded.sort(key=lambda item: str(item["post_id"]))
    if set(final_approved) & set(excluded_by_id):
        raise AssertionError("reconciled approved/excluded cohorts overlap")

    records, dataset_errors = load_jsonl(dataset_path)
    if dataset_errors:
        raise ValueError(dataset_errors[0])
    dataset_ids = {str(record["post_id"]) for record in records}
    partition_ids = set(final_approved) | set(excluded_by_id)
    if partition_ids != dataset_ids:
        raise ValueError("reconciled cohort does not exactly partition the dataset")
    selected = [record for record in records if str(record["post_id"]) in approved_set]

    output_dir.mkdir(parents=True, exist_ok=True)
    approval_output = output_dir / "privacy_approval.proposal.json"
    allowlist_output = output_dir / "public_allowlist.proposal.json"
    candidates_output = output_dir / "formal_eligible_candidates.proposal.jsonl"
    report_output = output_dir / "reconciliation_report.json"
    proposal = dict(approval)
    proposal.update(
        {
            "status": "proposal_pending_A_reconciliation_not_formal",
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "prepared_by": "deterministic reconciliation of B evidence",
            "source_approval_sha256": sha256_file(approval_path),
            "spotcheck_review_sha256": actual_review_sha,
            "spotcheck_validation_sha256": sha256_file(spotcheck_validation_path),
            "post_ids": final_approved,
            "excluded": final_excluded,
        }
    )
    _write_json(approval_output, proposal)
    _write_json(
        allowlist_output,
        {
            "status": "proposal_pending_A_reconciliation_not_formal",
            "total_approved": len(final_approved),
            "post_ids": final_approved,
        },
    )
    with candidates_output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")

    dataset_sha = sha256_file(dataset_path)
    approval_dataset_sha = str(approval.get("dataset_sha256", "")).lower()
    report = {
        "status": "proposal_pending_A_reconciliation_not_formal",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "formal_ready": False,
        "counts": {
            "base_approved": len(approved_order),
            "base_excluded": len(approval["excluded"]),
            "spotcheck_allow": sum(
                item.get("decision") == "allow" for item in review_items if isinstance(item, dict)
            ),
            "spotcheck_redact": sum(
                item.get("decision") == "redact" for item in review_items if isinstance(item, dict)
            ),
            "spotcheck_exclude": sum(
                item.get("decision") == "exclude" for item in review_items if isinstance(item, dict)
            ),
            "moved_from_approved_by_spotcheck": len(moved_by_spotcheck),
            "spotcheck_risk_already_excluded": len(spotcheck_risk_already_excluded),
            "spotcheck_allow_kept_excluded": len(spotcheck_allow_already_excluded),
            "moved_from_approved_by_supplemental_review": len(supplemental_moved),
            "supplemental_risk_already_excluded": len(supplemental_already_excluded),
            "proposed_approved": len(final_approved),
            "proposed_excluded": len(final_excluded),
            "partition_total": len(partition_ids),
        },
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_sha,
            "source_approval_dataset_sha256": approval_dataset_sha,
            "hash_matches_source_approval": dataset_sha == approval_dataset_sha,
        },
        "evidence": {
            "source_approval_sha256": sha256_file(approval_path),
            "source_allowlist_sha256": sha256_file(allowlist_path),
            "spotcheck_review_sha256": actual_review_sha,
            "spotcheck_validation_sha256": sha256_file(spotcheck_validation_path),
            "supplemental_review_sha256": (
                sha256_file(supplemental_review_path)
                if supplemental_review_path is not None
                else None
            ),
        },
        "files": {
            "privacy_approval.proposal.json": sha256_file(approval_output),
            "public_allowlist.proposal.json": sha256_file(allowlist_output),
            "formal_eligible_candidates.proposal.jsonl": sha256_file(candidates_output),
        },
        "blockers": [
            "A must review and sign the reconciled cohort; this proposal is not formal approval",
            "source dataset SHA-256 does not match the original cohort approval"
            if dataset_sha != approval_dataset_sha
            else "A must bind the matching source dataset and evidence",
            "stage-4 A calibration review and A/B model decision are still required",
        ],
    }
    _write_json(report_output, report)
    return report


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--spotcheck-manifest", type=Path)
    parser.add_argument("--media-review", type=Path)
    parser.add_argument("--supplemental-review", type=Path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit/materialize M1 privacy cohort")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    add_common_arguments(audit_parser)
    audit_parser.add_argument("--report", type=Path, required=True)

    materialize_parser = subparsers.add_parser("materialize")
    add_common_arguments(materialize_parser)
    materialize_parser.add_argument("--spotcheck-validation", type=Path, required=True)
    materialize_parser.add_argument("--output-dir", type=Path, required=True)
    materialize_parser.add_argument("--preview", action="store_true")

    reconcile_parser = subparsers.add_parser("reconcile-spotcheck")
    reconcile_parser.add_argument("--dataset", type=Path, required=True)
    reconcile_parser.add_argument("--approval", type=Path, required=True)
    reconcile_parser.add_argument("--allowlist", type=Path, required=True)
    reconcile_parser.add_argument("--spotcheck-review", type=Path, required=True)
    reconcile_parser.add_argument("--spotcheck-validation", type=Path, required=True)
    reconcile_parser.add_argument("--media-review", type=Path)
    reconcile_parser.add_argument("--supplemental-review", type=Path)
    reconcile_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "reconcile-spotcheck":
            report = reconcile_spotcheck(
                dataset_path=args.dataset,
                approval_path=args.approval,
                allowlist_path=args.allowlist,
                spotcheck_review_path=args.spotcheck_review,
                spotcheck_validation_path=args.spotcheck_validation,
                supplemental_review_path=args.supplemental_review,
                media_review_path=args.media_review,
                output_dir=args.output_dir,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        common = {
            "spotcheck_manifest_path": args.spotcheck_manifest,
            "media_review_path": args.media_review,
            "supplemental_review_path": args.supplemental_review,
        }
        if args.command == "audit":
            report = audit_cohort(
                dataset_path=args.dataset,
                approval_path=args.approval,
                allowlist_path=args.allowlist,
                **common,
            )
            _write_json(args.report, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["partition_passed"] else 1
        report = materialize(
            dataset_path=args.dataset,
            approval_path=args.approval,
            allowlist_path=args.allowlist,
            spotcheck_validation_path=args.spotcheck_validation,
            output_dir=args.output_dir,
            preview=args.preview,
            audit_options=common,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

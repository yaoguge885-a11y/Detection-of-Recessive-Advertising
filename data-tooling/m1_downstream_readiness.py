#!/usr/bin/env python3
"""Read-only readiness matrix for M1 stages 5–12.

This tool never creates batches, annotations, Gold, splits, or approvals.  It
only inspects fixed evidence paths and explains which formal action is allowed
next, preventing preparation artifacts from being mistaken for completed work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def stream_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig")
        decoder = json.JSONDecoder()
        count = 0
        index = 0
        while index < len(text):
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                break
            value, index = decoder.raw_decode(text, index)
            count += len(value) if isinstance(value, list) else 1
        return count
    except (OSError, json.JSONDecodeError):
        return None


def recorded_formal_candidate_sha(formalization: dict[str, Any]) -> str | None:
    """Read the candidate digest from current or legacy formalization schemas."""
    current = formalization.get("formal_candidates")
    if isinstance(current, dict) and current.get("sha256"):
        return str(current["sha256"]).lower()
    legacy = formalization.get("files")
    if isinstance(legacy, dict) and legacy.get("formal_eligible_candidates.jsonl"):
        return str(legacy["formal_eligible_candidates.jsonl"]).lower()
    return None


def stage(ready: bool, blockers: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    return {"ready_to_start": ready, "blockers": blockers, "evidence": evidence}


def evaluate(repo: Path) -> dict[str, Any]:
    reports = repo / "data" / "reports" / "m1"
    guide = repo / "docs" / "annotation_guide_v1.md"

    formal_root = reports / "privacy" / "formal_3312_v2"
    formal_candidates = formal_root / "formal_eligible_candidates.jsonl"
    formalization_path = formal_root / "formalization_report.json"
    formalization = read_object(formalization_path)
    candidate_count = stream_count(formal_candidates)
    stage3_ok = False
    stage3_blockers: list[str] = []
    if formalization is None:
        stage3_blockers.append("missing/invalid formalization_report.json")
    elif formalization.get("status") != "formal_materialized":
        stage3_blockers.append("formalization report is not formal_materialized")
    if candidate_count is None:
        stage3_blockers.append("missing/invalid formal_eligible_candidates.jsonl")
    elif candidate_count < 2050:
        stage3_blockers.append(f"formal candidate count {candidate_count} is below 2050")
    if formalization is not None and formal_candidates.is_file():
        recorded = recorded_formal_candidate_sha(formalization)
        actual = sha256_file(formal_candidates)
        if str(recorded or "").lower() != actual:
            stage3_blockers.append("formal candidate SHA does not match formalization report")
    stage3_ok = not stage3_blockers

    calibration_path = reports / "qwen_calibration_20_human_review_summary.json"
    calibration = read_object(calibration_path)
    stage4_blockers: list[str] = []
    if calibration is None:
        stage4_blockers.append("missing/invalid A/B calibration summary")
    else:
        if calibration.get("status") != "jointly_approved":
            stage4_blockers.append("calibration model route is not jointly_approved")
        if calibration.get("final_model_choice") not in {"qwen3.5:4b", "--no-llm"}:
            stage4_blockers.append("final_model_choice must be qwen3.5:4b or --no-llm")
        if not calibration.get("review_a_sha256") or not calibration.get("review_b_sha256"):
            stage4_blockers.append("calibration summary must bind both review SHA-256 values")
    stage4_ok = not stage4_blockers

    stage5_blockers = stage3_blockers + stage4_blockers
    stages: dict[str, Any] = {
        "stage5_lock_batches": stage(
            stage3_ok and stage4_ok,
            stage5_blockers,
            {
                "formalization_report": str(formalization_path),
                "formal_candidate_path": str(formal_candidates),
                "formal_candidate_count": candidate_count,
                "calibration_summary": str(calibration_path),
            },
        )
    }

    locked_root = reports / "locked_batches"
    lock_report_path = locked_root / "batch_lock_report.json"
    lock_report = read_object(lock_report_path)
    lock_blockers: list[str] = []
    if lock_report is None:
        lock_blockers.append("missing/invalid locked_batches/batch_lock_report.json")
    else:
        if lock_report.get("status") != "locked":
            lock_blockers.append("batch lock report status is not locked")
        if lock_report.get("unique_post_id_count") != 2050:
            lock_blockers.append("locked batches do not contain exactly 2050 unique IDs")
        if lock_report.get("overlap_count") != 0:
            lock_blockers.append("locked batch overlap_count is not zero")
    for name in ("round1", "round2", "gold_control", "gold_assisted"):
        if not (locked_root / f"{name}_manifest.json").is_file():
            lock_blockers.append(f"missing {name}_manifest.json")
        if not (locked_root / f"{name}.jsonl").is_file():
            lock_blockers.append(f"missing {name}.jsonl")
    stages["stage6_round1"] = stage(
        not lock_blockers,
        lock_blockers,
        {"batch_lock_report": str(lock_report_path)},
    )

    round1_agreement_path = reports / "round1_agreement.json"
    round1_agreement = read_object(round1_agreement_path)
    freeze_path = reports / "annotation_guide_freeze_receipt.json"
    freeze = read_object(freeze_path)
    round2_blockers: list[str] = []
    if round1_agreement is None:
        round2_blockers.append("missing/invalid round1_agreement.json")
    if freeze is None:
        round2_blockers.append("missing/invalid annotation_guide_freeze_receipt.json")
    else:
        if freeze.get("status") != "frozen":
            round2_blockers.append("annotation guide is not recorded as frozen")
        if not guide.is_file() or str(freeze.get("guide_sha256") or "").lower() != sha256_file(guide):
            round2_blockers.append("frozen guide SHA does not match current annotation guide")
    stages["stage7_round2"] = stage(
        not round2_blockers,
        round2_blockers,
        {"round1_agreement": str(round1_agreement_path), "guide_freeze": str(freeze_path)},
    )

    formal_agreement_path = reports / "formal_second_round_agreement.json"
    formal_agreement = read_object(formal_agreement_path)
    kappa_blockers: list[str] = []
    if formal_agreement is None:
        kappa_blockers.append("missing/invalid formal_second_round_agreement.json")
    else:
        if formal_agreement.get("formal_second_round") is not True:
            kappa_blockers.append("agreement report is not a valid formal second round")
        if formal_agreement.get("common_pair_count") != 150:
            kappa_blockers.append("formal second round does not contain exactly 150 paired records")
        kappa = formal_agreement.get("kappa")
        if not isinstance(kappa, (int, float)) or kappa < 0.60:
            kappa_blockers.append("formal Cohen kappa is below 0.60 or missing")
    for name in ("stage8_gold_control", "stage9_gold_assisted"):
        stages[name] = stage(
            not kappa_blockers,
            list(kappa_blockers),
            {"formal_agreement": str(formal_agreement_path)},
        )

    validation_root = reports / "annotation_validation"
    validation_paths = [
        validation_root / f"{batch}_{reviewer}.json"
        for batch in ("gold_control", "gold_assisted")
        for reviewer in ("A", "B")
    ]
    gold_input_blockers: list[str] = []
    for path in validation_paths:
        payload = read_object(path)
        if payload is None or payload.get("passed") is not True or payload.get("remaining_count") != 0:
            gold_input_blockers.append(f"missing/incomplete validation: {path.name}")
    stages["stage10_adjudication_gold"] = stage(
        not gold_input_blockers,
        gold_input_blockers,
        {"annotation_validation_reports": [str(path) for path in validation_paths]},
    )

    gold_path = repo / "data" / "gold" / "gold_v1.jsonl"
    gold_report_path = reports / "gold_build_report.json"
    gold_report = read_object(gold_report_path)
    gold_count = stream_count(gold_path)
    duplicate_report_path = reports / "near_duplicate_detection_report.json"
    duplicate_report = read_object(duplicate_report_path)
    split_input_blockers: list[str] = []
    if gold_report is None:
        split_input_blockers.append("missing/invalid gold_build_report.json")
    elif not isinstance(gold_report.get("gold_count"), int) or gold_report["gold_count"] < 1500:
        split_input_blockers.append("gold_build_report gold_count is below 1500")
    if gold_count is None or gold_count < 1500:
        split_input_blockers.append("gold_v1.jsonl is missing/invalid or below 1500")
    if duplicate_report is None or duplicate_report.get("status") != "passed":
        split_input_blockers.append("missing/invalid passed near_duplicate_detection_report.json")
    stages["stage11_group_split"] = stage(
        not split_input_blockers,
        split_input_blockers,
        {
            "gold": str(gold_path),
            "gold_report": str(gold_report_path),
            "gold_count": gold_count,
            "near_duplicate_detection_report": str(duplicate_report_path),
        },
    )

    split_report_path = reports / "split_report.json"
    split_report = read_object(split_report_path)
    card_path = reports / "dataset_card_status.json"
    card = read_object(card_path)
    final_blockers: list[str] = []
    if split_report is None:
        final_blockers.append("missing/invalid split_report.json")
    else:
        for key in ("creator_leakage_count", "near_duplicate_leakage_count"):
            if split_report.get(key) != 0:
                final_blockers.append(f"split report {key} is not zero")
    if card is None:
        final_blockers.append("missing/invalid dataset_card_status.json")
    else:
        false_keys = [key for key, value in card.items() if value is not True]
        if false_keys:
            final_blockers.append(f"dataset card evidence remains false: {false_keys}")
    stages["stage12_final_gate"] = stage(
        not final_blockers,
        final_blockers,
        {"split_report": str(split_report_path), "dataset_card_status": str(card_path)},
    )

    next_stage = next((name for name, value in stages.items() if not value["ready_to_start"]), None)
    return {
        "status": "read_only_preparation_matrix",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo.resolve()),
        "all_downstream_stages_ready": all(value["ready_to_start"] for value in stages.values()),
        "first_blocked_stage": next_stage,
        "stages": stages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect M1 stages 5-12 without mutating formal state")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = evaluate(args.repo_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if (not args.strict or report["all_downstream_stages_ready"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

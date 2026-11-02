"""Check frozen v2 human exports without supplying labels or signing approvals.

Default output contains receipt metadata only. --compare requires two valid
exports and --seal; originals are copied byte-for-byte before any comparison.
All generated output is private, is non-formal evidence, and never updates M1.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "data/run_outputs/blind_review_returns"
BLIND = REPO / "data/reports/m1/qwen_blind_test_20260827_remote_links_v2"
LABELS = {"明广", "暗广", "非广", "uncertain", "out_of_scope"}
THREE = {"明广", "暗广", "非广"}
ATTESTATIONS = ("read_guide", "no_other_answers", "independent", "evidence_checked")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(data: bytes):
    def reject(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(data.decode("utf-8-sig"), parse_constant=reject)


def frozen_context(repo_root: Path = REPO) -> tuple[dict, list]:
    repo_root = Path(repo_root).resolve()
    blind_root = repo_root / "data/reports/m1/qwen_blind_test_20260827_remote_links_v2"
    html = (blind_root / "delivery/B/M1_Blind_Human_Review_B.html").read_text(encoding="utf-8-sig")
    values = {}
    for key in ("META", "ITEMS"):
        found = re.search(r"^\s*const " + key + r"=(.*);$", html, re.M)
        if not found:
            raise ValueError("Frozen page is missing " + key)
        values[key] = json.loads(found.group(1))
    meta = values["META"]
    actual = digest((blind_root / "blind_sample_manifest_remote_links_v2.json").read_bytes())
    if actual != meta["manifest_sha256"].lower():
        raise ValueError("Frozen manifest/page hash mismatch")
    for key, path in (
        ("source_sha256", repo_root / "data/reports/m1/privacy/formal_3312_v2/formal_eligible_candidates.jsonl"),
        ("guide_sha256", blind_root / "delivery/COORDINATOR/annotation_guide_v1.md"),
    ):
        if digest(path.read_bytes()) != meta[key].lower():
            raise ValueError("Frozen context hash mismatch: " + key)
    return meta, values["ITEMS"]


def validate(payload, role: str, meta: dict, expected: list) -> dict:
    """Validate declarations and completeness; cannot verify human truthfulness."""
    errors = []
    def need(condition, message):
        if not condition:
            errors.append(message)
    if not isinstance(payload, dict):
        return {"structurally_valid": False, "errors": ["export must be an object"]}
    need(payload.get("schema_version") == "m1_blind_human_review_v2", "wrong schema version")
    need(payload.get("role") == role, "wrong role")
    need(payload.get("annotation_method") == "human", "annotation_method must be human")
    need(payload.get("qwen_visible") is False, "qwen_visible must be false")
    need(not any(re.search(r"model|suggestion|reasoning", k, re.I) for k in payload), "model suggestion fields present")
    for key in ("manifest_sha256", "source_sha256", "guide_sha256"):
        need(str(payload.get(key, "")).lower() == meta[key].lower(), "wrong " + key)
    need(payload.get("sample_count") == len(expected), "wrong sample_count")
    need(bool(str(payload.get("exported_at", "")).strip()), "missing export timestamp")
    att = payload.get("attestation")
    if not isinstance(att, dict):
        att = {}
        errors.append("missing attestation object")
    for key in ATTESTATIONS:
        need(att.get(key) is True, "missing declaration: " + key)
    for key in ("reviewer_id", "reviewer_name"):
        need(isinstance(att.get(key), str) and bool(att[key].strip()), "missing " + key)
        need(payload.get(key) == att.get(key), "inconsistent " + key)
    need(payload.get("annotator_id") == att.get("reviewer_id"), "inconsistent annotator_id")
    entries = payload.get("items")
    if not isinstance(entries, list) or any(not isinstance(x, dict) for x in entries):
        return {"structurally_valid": False, "errors": errors + ["items must be an object array"]}
    expected_ids = [x["post_id"] for x in expected]
    need([x.get("post_id") for x in entries] == expected_ids, "sample IDs/order differ from frozen manifest")
    need(len(entries) == len(expected), "wrong item count")
    unavailable_total = 0
    expected_by_id = {x["post_id"]: x for x in expected}
    for index, row in enumerate(entries, 1):
        prefix = "item " + str(index) + ": "
        target = expected_by_id.get(row.get("post_id"))
        if target is None:
            continue
        need(row.get("ordinal") == target["ordinal"], prefix + "wrong ordinal")
        need(row.get("reviewed") is True, prefix + "not marked reviewed")
        need(row.get("label") in LABELS, prefix + "invalid label")
        conf = row.get("confidence")
        need(isinstance(conf, (int, float)) and not isinstance(conf, bool) and math.isfinite(conf) and 0 <= conf <= 1,
             prefix + "invalid confidence")
        need(isinstance(row.get("evidence"), str) and bool(row["evidence"].strip()), prefix + "missing evidence note")
        need(bool(row.get("reviewed_at")), prefix + "missing review timestamp")
        if row.get("label") == "uncertain":
            need(isinstance(row.get("uncertain_reason"), str) and bool(row["uncertain_reason"].strip()), prefix + "missing uncertainty reason")
        media = row.get("media_review")
        if not isinstance(media, dict):
            errors.append(prefix + "missing media_review")
            continue
        local_entries = [m for m in target["media"] if m["local_exists"]]
        local = {m["ref"] for m in local_entries}
        remote = {m["remote_key"]: m for m in target["media"] if m.get("remote_available")}
        missing = [m for m in target["media"] if not m["local_exists"] and not m.get("remote_available")]
        counts = {"media_ref_count": len(target["media"]), "local_media_ref_count": len(local_entries),
                  "remote_link_media_ref_count": len(remote), "missing_media_ref_count": len(missing)}
        for key, count in counts.items():
            need(media.get(key) == count, prefix + "wrong " + key)
        viewed = media.get("viewed_media_refs")
        valid_viewed = isinstance(viewed, list) and all(isinstance(x, str) for x in viewed)
        need(valid_viewed and len(viewed) == len(set(viewed)) and set(viewed) == local, prefix + "local media not completely accounted for")
        need(media.get("all_local_media_viewed") is True, prefix + "local media declaration missing")
        need(media.get("media_review_confirmed") is True, prefix + "media confirmation missing")
        statuses = media.get("remote_media_statuses", {})
        attempts = media.get("remote_open_attempts", {})
        if not isinstance(statuses, dict) or not isinstance(attempts, dict):
            errors.append(prefix + "invalid remote media audit")
            continue
        need(set(statuses) == set(remote), prefix + "remote statuses differ from fixed entries")
        for key in remote:
            status = statuses.get(key)
            need(status in {"reviewed", "unavailable"}, prefix + "unresolved remote media")
            if status == "reviewed":
                need(isinstance(attempts.get(key), str) and bool(attempts[key].strip()), prefix + "remote viewed without an opening record")
            if status == "unavailable":
                unavailable_total += 1
        need(media.get("all_remote_media_resolved") is True, prefix + "remote resolution declaration missing")
        if missing or "unavailable" in statuses.values():
            need(att.get("media_gaps_ack") is True and media.get("media_gap_acknowledged") is True, prefix + "evidence gap not acknowledged")
    gap = unavailable_total > 0 or meta["missing_media_count"] > 0
    expected_status = ("completed_with_declared_evidence_gaps" if gap else
                       "completed_with_remote_unpinned_media_evidence" if meta["remote_link_media_count"] else
                       "completed_independent_blind_human_review")
    need(payload.get("status") == expected_status, "completion status inconsistent with evidence state")
    return {"structurally_valid": not errors, "role": role, "item_count": len(entries),
            "unavailable_remote_count": unavailable_total, "errors": errors,
            "human_independence_verified": False,
            "note": "Checks declarations and recorded coverage; does not prove actual human review or label quality."}


def compare(a: dict, b: dict) -> tuple[dict, list]:
    pairs = list(zip(a["items"], b["items"]))
    shared = [(x, y) for x, y in pairs if x["label"] in THREE and y["label"] in THREE]
    same_all = sum(x["label"] == y["label"] for x, y in pairs)
    same_shared = sum(x["label"] == y["label"] for x, y in shared)
    stats = {"purpose": "21-item engineering calibration; not formal Round 2 or Gold",
             "total": len(pairs), "same_label_count": same_all,
             "all_label_agreement": same_all / len(pairs) if pairs else None,
             "shared_three_class_count": len(shared), "shared_three_class_agreement_count": same_shared,
             "shared_three_class_agreement": same_shared / len(shared) if shared else None,
             "shared_three_class_coverage": len(shared) / len(pairs) if pairs else None,
             "label_counts_A": dict(Counter(x["label"] for x, _ in pairs)),
             "label_counts_B": dict(Counter(y["label"] for _, y in pairs)),
             "formal_kappa": None, "formal_gold_count": 0, "model_route_approved": False}
    queue = [{"ordinal": x["ordinal"], "post_id": x["post_id"], "label_A": x["label"], "label_B": y["label"],
              "human_final_label": None, "human_reason": None, "adjudicators": [], "adjudicated_at": None}
             for x, y in pairs if x["label"] != y["label"] or x["label"] not in THREE]
    stats["human_adjudication_required_count"] = len(queue)
    return stats, queue


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO, help="repository containing the private frozen v2 batch")
    parser.add_argument("--a", type=Path, help="A's ORIGINAL exported JSON, not a ZIP")
    parser.add_argument("--b", type=Path, help="B's ORIGINAL exported JSON")
    parser.add_argument("--seal", action="store_true", help="copy valid originals byte-for-byte to a new private directory")
    parser.add_argument("--compare", action="store_true", help="requires both exports and --seal; reveals cross-role labels")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.compare and not (args.a and args.b and args.seal):
        parser.error("--compare requires --a, --b and --seal; no comparison before both originals are sealed")
    meta, expected = frozen_context(args.repo_root)
    reports, payloads, originals = {}, {}, {}
    for role, path in (("A", args.a), ("B", args.b)):
        if path is None:
            reports[role] = {"status": "not_supplied", "structurally_valid": False}
            continue
        raw = path.read_bytes()
        payload = read_json(raw)
        result = validate(payload, role, meta, expected)
        result.update({"source": str(path.resolve()), "sha256": digest(raw)})
        reports[role], payloads[role], originals[role] = result, payload, raw
    all_valid = all(r.get("structurally_valid") for r in reports.values())
    distinct = None
    if all_valid:
        distinct = payloads["A"]["reviewer_id"].strip().casefold() != payloads["B"]["reviewer_id"].strip().casefold()
        all_valid = all_valid and distinct
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    out = args.output_dir or args.repo_root / "data/run_outputs/blind_review_returns" / ("receipt_" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"checked_at": datetime.now(timezone.utc).isoformat(), "formal_evidence": False,
               "human_independence_verified": False, "roles": reports, "distinct_reviewer_ids": distinct,
               "both_exports_structurally_valid": all_valid, "sealed_roles": [],
               "comparison_generated": False, "M1_gate_updated": False}
    if args.seal:
        for role, raw in originals.items():
            if reports[role]["structurally_valid"]:
                target = out / ("original_" + role + ".json")
                with target.open("xb") as f:
                    f.write(raw)
                if digest(target.read_bytes()) != reports[role]["sha256"]:
                    raise RuntimeError("Sealed copy integrity failure")
                receipt["sealed_roles"].append(role)
    if args.compare and all_valid and receipt["sealed_roles"] == ["A", "B"]:
        stats, queue = compare(payloads["A"], payloads["B"])
        write_json(out / "comparison.json", stats)
        write_json(out / "needs_human_adjudication.json", {"status": "awaiting_human_adjudication", "items": queue})
        receipt["comparison_generated"] = True
    write_json(out / "receipt.json", receipt)
    print(json.dumps({"output_dir": str(out.resolve()), "roles": {k: {q: v.get(q) for q in ("status", "structurally_valid", "item_count", "errors")} for k, v in reports.items()},
                      "both_exports_structurally_valid": all_valid, "comparison_generated": receipt["comparison_generated"]}, ensure_ascii=False, indent=2))
    return 0 if all_valid else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        sys.exit(1)

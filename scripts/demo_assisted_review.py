"""Generate a synthetic assisted-review handoff, without private data or models."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-tooling/annotation"))
import generate_m1_qwen_blind_html as generator
import build_assisted_review as assisted


def run_demo(output_root: Path) -> dict:
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    inputs = output_root / "synthetic_inputs"
    (inputs / "media").mkdir(parents=True)
    (inputs / "media/pixel.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    rows = [{"post_id": f"synthetic_assisted_{n}", "platform": "synthetic", "title": f"Synthetic example {n}",
             "text": "SYNTHETIC FIXTURE ONLY. No real person or advertisement.", "comments": [],
             "media": [{"type": "image", "ref": "media/pixel.png"}] if n == 3 else []} for n in (1, 2, 3)]
    source = inputs / "candidates.jsonl"
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    manifest = inputs / "manifest.json"
    manifest.write_text(json.dumps({"sample_count": 3, "qwen_run_performed": False,
        "source": {"sha256": generator.sha256_file(source)},
        "items": [{"ordinal": n, "post_id": row["post_id"]} for n, row in enumerate(rows, 1)]}), encoding="utf-8")
    delivery = inputs / "delivery"
    generator.generate_delivery(repo_root=output_root, manifest_path=manifest, input_path=source,
        guide_path=ROOT / "docs/annotation_guide_v1.md", media_base=inputs, output_root=delivery, roles=("B",))
    page = delivery / "B/M1_Blind_Human_Review_B.html"
    html = page.read_text(encoding="utf-8")
    meta = json.loads(re.search(r"^\s*const META=(.*);$", html, re.M).group(1))
    records = {row["post_id"]: {"label": "", "confidence": "", "evidence_codes": [], "evidence": "", "uncertain_reason": "",
        "reviewed": False, "reviewed_at": "", "media_review_confirmed": False, "viewed_media_refs": [],
        "remote_media_statuses": {}, "remote_open_attempts": {}} for row in rows}
    records[rows[0]["post_id"]].update(label="非广", confidence="0.8", evidence="Existing synthetic note; preserve exactly.", reviewed=True)
    records[rows[1]["post_id"]].update(label="uncertain", confidence="0.6")
    draft = inputs / "draft.json"
    draft.write_text(json.dumps({"schema_version": "m1_blind_draft_snapshot_v2", "synthetic_fixture": True,
        "formal_evidence": False, "role": "B", "sample_count": 3,
        **{key: meta[key] for key in ("manifest_sha256", "source_sha256", "guide_sha256", "evidence_code_dictionary_sha256")},
        "ordered_post_ids": [row["post_id"] for row in rows],
        "state": {"records": records, "attestation": {"reviewer_name": "SYNTHETIC REVIEWER", "reviewer_id": "B"}}}), encoding="utf-8")
    suggestions = inputs / "suggestions.json"
    suggestions.write_text(json.dumps({"suggestion_author": "Synthetic fixture, no model called", "media_inspection": {"synthetic_fixture": True},
        "items": [{"ordinal": 2, "fields": {"evidence": "Synthetic added note", "uncertain_reason": "Synthetic gap"}, "review_note": "TEST ONLY"},
                  {"ordinal": 3, "fields": {"label": "非广", "confidence": "0.7", "evidence": "Synthetic example", "evidence_codes": []}, "review_note": "TEST ONLY"}]}), encoding="utf-8")
    result = assisted.build_assisted_review(draft_path=draft, page_path=page, suggestions_path=suggestions,
                                          media_base=inputs, output_root=output_root / "review")
    report = {"status": "passed", "synthetic_fixture": True, "formal_evidence": False, "network_requests": 0,
              "model_calls": 0, "sample_count": 3, "entrypoint": result["entrypoint"],
              "preserved_existing_fields": result["original_nonempty_fields_unchanged"], "ai_filled_ordinals": result["ai_filled_ordinals"]}
    (output_root / "demo_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    result = run_demo(args.output_root or ROOT / "data/run_outputs" / ("assisted_demo_" + stamp))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

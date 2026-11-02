"""Package an existing B draft and supplied AI suggestions for human review.

This is the portable form of the completed local continuation workflow. It
does not call a model, change a filled field, certify human viewing, or create
formal blind-review evidence. Inputs and outputs containing real records stay
private; use scripts/demo_assisted_review.py for a public synthetic example.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
from urllib.parse import quote

ASSETS = Path(__file__).resolve().parent
FILLABLE = ("label", "confidence", "evidence_codes", "evidence", "uncertain_reason")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def empty(value) -> bool:
    return value is None or value == "" or value == []


def build_assisted_review(*, draft_path: Path, page_path: Path, suggestions_path: Path,
                          media_base: Path, output_root: Path) -> dict:
    draft_path, page_path, suggestions_path, media_base, output_root = (
        Path(p).resolve() for p in (draft_path, page_path, suggestions_path, media_base, output_root))
    if output_root.exists():
        raise FileExistsError("Choose a new output directory; existing review progress is preserved")
    raw = draft_path.read_bytes()
    snapshot = json.loads(raw.decode("utf-8-sig"))
    if snapshot.get("schema_version") not in {"m1_blind_draft_snapshot_v1", "m1_blind_draft_snapshot_v2"} or snapshot.get("role") != "B":
        raise ValueError("Expected a B partial-draft snapshot")
    page = page_path.read_text(encoding="utf-8-sig")
    constants = {}
    for key in ("META", "ITEMS", "GUIDE_TEXT"):
        match = re.search(r"^\s*const " + key + r"=(.*);$", page, re.M)
        if not match:
            raise ValueError("Page is missing frozen constant " + key)
        constants[key] = json.loads(match.group(1))
    meta, items = constants["META"], constants["ITEMS"]
    ids = [item["post_id"] for item in items]
    if len(set(ids)) != len(ids) or snapshot.get("sample_count") != len(ids) or snapshot.get("ordered_post_ids") != ids:
        raise ValueError("Draft/page sample count or order mismatch")
    for key in ("manifest_sha256", "source_sha256", "guide_sha256"):
        if str(snapshot.get(key, "")).lower() != str(meta.get(key, "")).lower():
            raise ValueError("Draft/page fingerprint mismatch: " + key)
    if meta.get("evidence_code_dictionary_sha256") and snapshot.get("evidence_code_dictionary_sha256") != meta["evidence_code_dictionary_sha256"]:
        raise ValueError("Draft/page evidence dictionary mismatch")
    original_records = deepcopy(snapshot["state"]["records"])
    if set(original_records) != set(ids):
        raise ValueError("Draft records do not match the fixed sample")
    records = deepcopy(original_records)
    suggestions = json.loads(suggestions_path.read_text(encoding="utf-8-sig"))
    entries = suggestions.get("items", [])
    by_ordinal = {entry["ordinal"]: entry for entry in entries}
    if len(by_ordinal) != len(entries) or not set(by_ordinal).issubset({item["ordinal"] for item in items}):
        raise ValueError("Unknown or duplicate suggestion ordinal")
    result_items, preserved_count, added_fields = [], 0, 0
    for item in items:
        ordinal, pid = item["ordinal"], item["post_id"]
        original, suggestion = original_records[pid], by_ordinal.get(ordinal)
        edited = []
        editable = [key for key in FILLABLE if empty(original.get(key))] if suggestion else []
        if suggestion:
            for key, value in suggestion["fields"].items():
                if key not in FILLABLE:
                    raise ValueError("Suggestions cannot change viewing records or declarations")
                if empty(original.get(key)) and not empty(value):
                    records[pid][key] = deepcopy(value)
                    edited.append(key)
        for key, value in original.items():
            if key not in edited:
                if records[pid][key] != value:
                    raise ValueError("Existing field changed")
                preserved_count += 1
            elif not empty(value):
                raise ValueError("Filled field would be overwritten")
        display_source = deepcopy(item)
        for media in display_source["media"]:
            if media["local_exists"]:
                ref = str(media["ref"]).replace("\\", "/")
                if Path(ref).is_absolute() or PureWindowsPath(ref).is_absolute():
                    raise ValueError("Expected relative media reference")
                path = (media_base / ref).resolve()
                try:
                    path.relative_to(media_base)
                except ValueError as exc:
                    raise ValueError("Media reference escapes media base") from exc
                if not path.is_file():
                    raise FileNotFoundError(path)
                media["local_url"] = quote(Path(os.path.relpath(path, output_root)).as_posix(), safe="/._-")
        remote = original.get("remote_media_statuses", {})
        title = item.get("title")
        result_items.append({"ordinal": ordinal, "post_id": pid,
            "display_title": title if title not in (None, "", "None") else f"第 {ordinal} 条（原记录未提供标题）",
            "source": display_source, "ai_filled_fields": edited, "editable_fields": editable,
            "evidence_code_scheme": meta.get("evidence_code_scheme", "frozen_review_ui_v2") if original.get("evidence_codes") else suggestions.get("evidence_code_scheme", "annotation_guide_v1"),
            "ai_suggestion": deepcopy(suggestion["fields"]) if suggestion else None,
            "review_note": suggestion.get("review_note", "") if suggestion else "原填写保留，AI 没有修改或替你重新确认。",
            "original_media_summary": f"原记录本地已打开 {len(original.get('viewed_media_refs', []))} 项；在线视频已查看 {sum(v == 'reviewed' for v in remote.values())} 项、不可用 {sum(v == 'unavailable' for v in remote.values())} 项。AI 不追加人工观看记录。"})
        added_fields += len(edited)
    seed = {"schema_version": "m1_assisted_review_seed_v1", "annotation_method": "ai_assisted_human_review",
        "formal_evidence": False, "independent_blind_review": False,
        "source_snapshot_sha256": digest(raw), "source_snapshot_filename": draft_path.name,
        "manifest_sha256": snapshot["manifest_sha256"], "source_sha256": snapshot["source_sha256"],
        "guide_sha256": snapshot["guide_sha256"], "created_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": {key: snapshot["state"]["attestation"].get(key, "") for key in ("reviewer_name", "reviewer_id")},
        "original_records": original_records, "records": records, "items": result_items,
        "guide_text": constants["GUIDE_TEXT"], "media_inspection": suggestions.get("media_inspection", {"scope": "not_supplied"}),
        "suggestion_author": suggestions.get("suggestion_author", "not_supplied")}
    if draft_path.read_bytes() != raw:
        raise ValueError("Draft changed during preparation")
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "original_user_draft.json").write_bytes(raw)
    (output_root / "seed.json").write_text(json_text(seed), encoding="utf-8")
    (output_root / "review_core.js").write_bytes((ASSETS / "assisted_review_core.js").read_bytes())
    embedded = json_text(seed).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (ASSETS / "assisted_review_template.html").read_text(encoding="utf-8").replace("__SEED_JSON__", embedded)
    target = output_root / "B_AI辅助复核_接续草稿.html"
    target.write_text(html, encoding="utf-8")
    report = {"source_sha256_before": digest(raw), "source_sha256_after": digest(draft_path.read_bytes()),
        "original_draft_unchanged": draft_path.read_bytes() == raw, "original_nonempty_fields_unchanged": True,
        "preserved_field_count": preserved_count, "ai_filled_field_count": added_fields,
        "ai_filled_ordinals": [item["ordinal"] for item in result_items if item["ai_filled_fields"]],
        "new_label_count": sum("label" in item["ai_filled_fields"] for item in result_items),
        "user_media_review_flags_unchanged": True, "no_ai_confirmation_marked_complete": True,
        "export_schema": "m1_ai_assisted_human_review_v1", "formal_evidence": False, "entrypoint": str(target)}
    (output_root / "preservation_report.json").write_text(json_text(report), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--suggestions", type=Path, required=True)
    parser.add_argument("--media-base", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_assisted_review(draft_path=args.draft, page_path=args.page, suggestions_path=args.suggestions,
                                   media_base=args.media_base, output_root=args.output_dir)
    print(json_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

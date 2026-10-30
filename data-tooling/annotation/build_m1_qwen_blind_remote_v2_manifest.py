"""Build a corrected, immutable-input manifest for the M1 remote-link UI.

The v1 sample selection is preserved byte-for-byte at the ``post_id`` level.
Only the evidence availability description is recomputed from the read-only
source JSONL and media root.  The output is a new file and this tool refuses to
overwrite it, so an already distributed v1 package is never mutated.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import generate_m1_qwen_blind_html as html_generator


MANIFEST_SCHEMA_VERSION = "m1_qwen_blind_test_manifest_remote_links_v2"


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _url_sha256(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest().upper()


def build_manifest(
    *,
    repo_root: Path | str,
    parent_manifest_path: Path | str,
    input_path: Path | str,
    media_base: Path | str,
    output_path: Path | str,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    parent_manifest_path = Path(parent_manifest_path).resolve()
    input_path = Path(input_path).resolve()
    media_base = Path(media_base).resolve()
    output_path = Path(output_path).resolve()
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing manifest: {output_path}")
    for required in (parent_manifest_path, input_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    if not media_base.is_dir():
        raise FileNotFoundError(media_base)

    parent = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(parent, Mapping):
        raise ValueError("parent manifest must be a JSON object")
    if (parent.get("qwen_run_performed") is not False
            or parent.get("labels_known_to_sampler") is not False):
        raise ValueError("parent must explicitly attest no Qwen run and labels unknown to sampler")
    source_sha = html_generator.sha256_file(input_path)
    expected_source_sha = str((parent.get("source") or {}).get("sha256") or "").upper()
    if expected_source_sha and source_sha != expected_source_sha:
        raise ValueError(
            f"source SHA mismatch: expected {expected_source_sha}, got {source_sha}"
        )

    rows = html_generator._read_jsonl(input_path)
    prepared = html_generator._prepare_items(
        parent, rows, media_base, output_path.parent
    )
    prepared_by_id = {item["post_id"]: item for item in prepared}
    local_count = sum(
        1 for item in prepared for media in item["media"] if media["local_exists"]
    )
    remote_count = sum(
        1
        for item in prepared
        for media in item["media"]
        if media["remote_available"]
    )
    unavailable_count = sum(
        1
        for item in prepared
        for media in item["media"]
        if not media["local_exists"] and not media["remote_available"]
    )
    media_count = sum(len(item["media"]) for item in prepared)

    output = copy.deepcopy(dict(parent))
    output["schema_version"] = MANIFEST_SCHEMA_VERSION
    output["status"] = "awaiting_A_B_blind_labels"
    output["created_at"] = html_generator._now_iso()
    output["qwen_run_performed"] = False
    output["labels_known_to_sampler"] = False
    output["parent_manifest"] = {
        "path": _display_path(parent_manifest_path, repo_root),
        "sha256": html_generator.sha256_file(parent_manifest_path),
        "sample_selection_unchanged": True,
    }
    output["revision_reason"] = (
        f"v2 preserves {len(prepared)} selected post_ids and recomputes evidence: "
        f"{local_count} local, {remote_count} allowlisted remote unpinned, "
        f"{unavailable_count} unavailable media entries."
    )
    output["evidence_state"] = {
        "media_root": _display_path(media_base, repo_root),
        "source_media_entry_count": media_count,
        "local_media_ref_count": local_count,
        "remote_link_media_count": remote_count,
        "unavailable_media_count": unavailable_count,
        "remote_url_policy": "https_bilibili_video_bvid_only",
        "remote_content_sha256_available": False,
        "comment_collection_completeness": "unknown_for_all_selected_records",
        "disclosure_collection_completeness": "unknown_for_all_selected_records",
    }
    output["review_interface_contract"] = {
        "roles_receive_identical_evidence_entries": True,
        "remote_click_is_not_view_confirmation": True,
        "remote_status_required": ["reviewed", "unavailable"],
        "unavailable_status_is_declared_evidence_gap": True,
        "v1_drafts_accepted": False,
    }

    rewritten_items: list[dict[str, Any]] = []
    for selected in output.get("items") or []:
        if not isinstance(selected, Mapping):
            raise ValueError("parent manifest item is not an object")
        selected_copy = copy.deepcopy(dict(selected))
        prepared_item = prepared_by_id.get(str(selected_copy.get("post_id") or ""))
        if prepared_item is None:
            raise ValueError("parent item is absent from prepared source evidence")
        media = prepared_item["media"]
        selected_copy["media_count"] = len(media)
        selected_copy["local_media_count"] = sum(
            1 for entry in media if entry["local_exists"]
        )
        selected_copy["remote_link_media_count"] = sum(
            1 for entry in media if entry["remote_available"]
        )
        selected_copy["missing_media_count"] = sum(
            1
            for entry in media
            if not entry["local_exists"] and not entry["remote_available"]
        )
        selected_copy["remote_links"] = [
            {
                "media_number": entry["number"],
                "url": entry["remote_url"],
                "url_sha256": _url_sha256(entry["remote_url"]),
                "content_sha256": None,
            }
            for entry in media
            if entry["remote_available"]
        ]
        rewritten_items.append(selected_copy)
    output["items"] = rewritten_items

    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_generator._write_text(
        output_path, json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    )
    return {
        "output_path": output_path.as_posix(),
        "sha256": html_generator.sha256_file(output_path),
        "sample_count": len(prepared),
        "source_media_entry_count": media_count,
        "local_media_ref_count": local_count,
        "remote_link_media_count": remote_count,
        "unavailable_media_count": unavailable_count,
        "parent_manifest_sha256": html_generator.sha256_file(parent_manifest_path),
        "source_sha256": source_sha,
    }


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_default_repo_root())
    parser.add_argument("--parent-manifest", type=Path)
    parser.add_argument("--input", dest="input_path", type=Path)
    parser.add_argument("--media-base", type=Path)
    parser.add_argument("--output", dest="output_path", type=Path)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    parent_dir = root / "data" / "reports" / "m1" / "qwen_blind_test_20260825"
    output_dir = (
        root
        / "data"
        / "reports"
        / "m1"
        / "qwen_blind_test_20260827_remote_links_v2"
    )
    try:
        result = build_manifest(
            repo_root=root,
            parent_manifest_path=args.parent_manifest
            or parent_dir / "blind_sample_manifest.json",
            input_path=args.input_path
            or root
            / "data"
            / "reports"
            / "m1"
            / "privacy"
            / "formal_3312_v2"
            / "formal_eligible_candidates.jsonl",
            media_base=args.media_base
            or root / "data" / "run_outputs" / "merged_20260728",
            output_path=args.output_path
            or output_dir / "blind_sample_manifest_remote_links_v2.json",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

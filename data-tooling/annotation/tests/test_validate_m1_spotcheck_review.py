from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "validate_m1_spotcheck_review.py"
SPEC = importlib.util.spec_from_file_location("validate_m1_spotcheck_review", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '\n'.join(json.dumps({"post_id": post_id}) for post_id in ("p1", "p2"))
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    write_json(
        manifest,
        {
            "status": "pending_human_B_review",
            "seed": 7,
            "population": 20,
            "sample_size": 2,
            "post_ids": ["p1", "p2"],
        },
    )
    review = tmp_path / "review.json"
    write_json(
        review,
        {
            "status": MODULE.COMPLETED_STATUS,
            "reviewer": "B",
            "exported_at": "2026-08-14T01:02:03Z",
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "seed": 7,
            "population": 20,
            "sample_count": 2,
            "decision_counts": {"allow": 1, "redact": 1, "exclude": 0},
            "items": [
                {
                    "number": 1,
                    "post_id": "p1",
                    "platform": "bilibili",
                    "notes": "",
                    "updated_at": "2026-08-14T01:00:00Z",
                    "decision": "allow",
                    "reviewed": True,
                },
                {
                    "number": 2,
                    "post_id": "p2",
                    "platform": "wechat_official_account",
                    "notes": "media contains a visible identifier",
                    "updated_at": "2026-08-14T01:01:00Z",
                    "decision": "redact",
                    "reviewed": True,
                },
            ],
        },
    )
    return manifest, review, dataset


def test_valid_review_passes(tmp_path: Path) -> None:
    manifest, review, dataset = fixture(tmp_path)
    report = MODULE.validate(
        manifest_path=manifest, review_path=review, dataset_path=dataset
    )
    assert report["passed"] is True
    assert report["errors"] == []
    assert report["review"]["decision_counts"] == {
        "allow": 1,
        "redact": 1,
        "exclude": 0,
    }


def test_rejects_missing_notes_and_wrong_id(tmp_path: Path) -> None:
    manifest, review, dataset = fixture(tmp_path)
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["items"][1]["post_id"] = "unexpected"
    payload["items"][1]["notes"] = ""
    write_json(review, payload)
    report = MODULE.validate(
        manifest_path=manifest, review_path=review, dataset_path=dataset
    )
    assert report["passed"] is False
    assert any("requires notes" in error for error in report["errors"])
    assert any("unexpected post_ids" in error for error in report["errors"])
    assert any("missing 1 manifest" in error for error in report["errors"])


def test_rejects_tampered_manifest_fingerprint(tmp_path: Path) -> None:
    manifest, review, dataset = fixture(tmp_path)
    payload = json.loads(review.read_text(encoding="utf-8"))
    payload["manifest_sha256"] = "0" * 64
    write_json(review, payload)
    report = MODULE.validate(
        manifest_path=manifest, review_path=review, dataset_path=dataset
    )
    assert report["passed"] is False
    assert any("manifest_sha256" in error for error in report["errors"])

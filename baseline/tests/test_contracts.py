"""Focused tests for the isolated baseline input contract."""

import builtins
import json
from pathlib import Path

import pytest

from baseline.contracts import BaselineInputError, load_input_bundle


LABELS = ("明广", "暗广", "非广")


def test_formal_mode_rejects_current_failed_m1_gate(tmp_path: Path):
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": False}), encoding="utf-8")
    with pytest.raises(BaselineInputError, match="M1 gate has not passed"):
        load_input_bundle(mode="formal", m1_gate_path=gate)


def test_failed_formal_gate_precedes_test_confirmation_and_model_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": False}), encoding="utf-8")
    sklearn_imports: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object):
        if name == "sklearn" or name.startswith("sklearn."):
            sklearn_imports.append(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(BaselineInputError, match="M1 gate has not passed"):
        load_input_bundle(
            mode="formal",
            m1_gate_path=gate,
            evaluation_split="test",
            confirm_test_evaluation=False,
        )
    assert sklearn_imports == []


def test_formal_test_requires_explicit_confirmation(tmp_path: Path):
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": True}), encoding="utf-8")
    with pytest.raises(BaselineInputError, match="test evaluation requires"):
        load_input_bundle(
            mode="formal",
            m1_gate_path=gate,
            evaluation_split="test",
            confirm_test_evaluation=False,
        )


def _write_fixture(tmp_path: Path) -> dict[str, Path]:
    rows = []
    gold = []
    ids: dict[str, list[str]] = {"train": [], "dev": [], "test": []}
    for split_index, split in enumerate(ids):
        for label_index, label in enumerate(LABELS):
            post_id = f"fixture_{split}_{label_index}"
            creator_id = f"fixture_creator_{split}_{label_index}"
            rows.append(
                {
                    "post_id": post_id,
                    "blogger_id": creator_id,
                    "published_at": f"2024-01-{split_index + 1:02d}T12:00:00+00:00",
                    "text": "fixture text",
                    "blogger_history_refs": [],
                    "content_group_id": None,
                }
            )
            gold.append({"post_id": post_id, "label": label})
            ids[split].append(post_id)
    content_path = tmp_path / "content.jsonl"
    content_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    gold_path = tmp_path / "gold.jsonl"
    gold_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in gold),
        encoding="utf-8",
    )
    paths: dict[str, Path] = {
        "content_path": content_path,
        "gold_path": gold_path,
    }
    for split, split_ids in ids.items():
        path = tmp_path / f"{split}.txt"
        path.write_text("\n".join(split_ids) + "\n", encoding="utf-8")
        paths[f"{split}_ids_path"] = path
    split_report = tmp_path / "split_report.json"
    split_report.write_text(
        json.dumps(
            {
                "post_leakage_count": 0,
                "creator_leakage_count": 0,
                "content_group_leakage_count": 0,
                "near_duplicate_leakage_count": 0,
                "near_duplicate_check_status": "passed",
            }
        ),
        encoding="utf-8",
    )
    paths["split_report_path"] = split_report
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"gate": "M1", "passed": True}), encoding="utf-8")
    paths["m1_gate_path"] = gate
    return paths


def test_synthetic_mode_accepts_explicit_fixture(tmp_path: Path):
    paths = _write_fixture(tmp_path)
    metadata = tmp_path / "fixture_metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "fixture_version": "merged-history-synthetic-v1",
                "dataset_kind": "synthetic_fixture",
            }
        ),
        encoding="utf-8",
    )

    bundle = load_input_bundle(
        mode="synthetic",
        fixture_metadata_path=metadata,
        **paths,
    )

    assert bundle.mode == "synthetic"
    assert len(bundle.posts) == 9
    assert len(bundle.gold) == 9
    assert bundle.input_hashes["fixture_metadata"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_content", "duplicate content post_id"),
        ("invalid_gold_label", "invalid formal Gold label"),
        ("missing_gold_content", "Gold/content coverage mismatch"),
        ("overlapping_splits", "split IDs overlap"),
        ("missing_split_id", "split/Gold coverage mismatch"),
        ("nonzero_creator_leakage", "split leakage check failed"),
        ("missing_near_duplicate_evidence", "split leakage evidence is incomplete"),
        ("split_missing_class", "each split must contain all three labels"),
    ],
)
def test_input_contracts_fail_closed(tmp_path: Path, mutation: str, message: str):
    paths = _write_fixture(tmp_path)
    if mutation == "duplicate_content":
        with paths["content_path"].open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "post_id": "fixture_train_0",
                        "blogger_id": "fixture_creator_train_0",
                        "published_at": "2024-01-01T12:00:00+00:00",
                        "text": "fixture text",
                        "blogger_history_refs": [],
                        "content_group_id": None,
                    }
                )
                + "\n"
            )
    elif mutation == "invalid_gold_label":
        lines = paths["gold_path"].read_text(encoding="utf-8").splitlines()
        lines[0] = json.dumps({"post_id": "fixture_train_0", "label": "uncertain"})
        paths["gold_path"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "missing_gold_content":
        lines = paths["content_path"].read_text(encoding="utf-8").splitlines()
        paths["content_path"].write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    elif mutation == "overlapping_splits":
        path = paths["dev_ids_path"]
        path.write_text(
            path.read_text(encoding="utf-8") + "fixture_train_0\n", encoding="utf-8"
        )
    elif mutation == "missing_split_id":
        path = paths["test_ids_path"]
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    elif mutation == "nonzero_creator_leakage":
        report = json.loads(paths["split_report_path"].read_text(encoding="utf-8"))
        report["creator_leakage_count"] = 1
        paths["split_report_path"].write_text(json.dumps(report), encoding="utf-8")
    elif mutation == "missing_near_duplicate_evidence":
        report = json.loads(paths["split_report_path"].read_text(encoding="utf-8"))
        report.pop("near_duplicate_check_status")
        paths["split_report_path"].write_text(json.dumps(report), encoding="utf-8")
    elif mutation == "split_missing_class":
        path = paths["gold_path"]
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rows[0]["label"] = rows[1]["label"]
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
    else:  # pragma: no cover - protects the test helper from silent omissions.
        raise AssertionError(mutation)

    with pytest.raises(BaselineInputError, match=message):
        load_input_bundle(mode="formal", **paths)

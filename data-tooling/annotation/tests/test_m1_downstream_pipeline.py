from __future__ import annotations

import importlib.util
from pathlib import Path


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOOLING = Path(__file__).parents[2]
GOLD = load("build_gold_dataset_for_pipeline", TOOLING / "annotation" / "build_gold_dataset.py")
METADATA = load("m1_gold_metadata_for_pipeline", TOOLING / "m1_gold_metadata.py")
SPLIT = load("split_by_blogger_for_pipeline", TOOLING / "annotation" / "split_by_blogger.py")


def annotation(post_id: str, annotator: str, label: str) -> dict:
    return {
        "post_id": post_id,
        "annotator_id": annotator,
        "annotation_method": "human",
        "label": label,
        "confidence": 0.9,
    }


def test_synthetic_gold_to_group_split_has_no_leakage() -> None:
    a = {
        "p1": annotation("p1", "A", "明广"),
        "p2": annotation("p2", "A", "非广"),
        "p3": annotation("p3", "A", "暗广"),
        "p4": annotation("p4", "A", "非广"),
    }
    b = {
        "p1": annotation("p1", "B", "明广"),
        "p2": annotation("p2", "B", "暗广"),
        "p3": annotation("p3", "B", "暗广"),
        "p4": annotation("p4", "B", "非广"),
    }
    adjudication = {
        "p2": {
            "post_id": "p2",
            "label": "非广",
            "conflict_reason": "synthetic disagreement",
            "arbiter": "A+B",
            "arbiter_note": "synthetic joint decision",
        }
    }
    gold_rows, excluded = GOLD.merge_annotations(a, b, adjudication, min_confidence=0.6)
    assert len(gold_rows) == 4
    assert excluded == []

    canonical = {
        "p1": {"post_id": "p1", "blogger_id": "creator1", "content_group_id": "g1"},
        "p2": {"post_id": "p2", "blogger_id": "creator2", "content_group_id": "g1"},
        "p3": {"post_id": "p3", "blogger_id": "creator3", "content_group_id": None},
        "p4": {"post_id": "p4", "blogger_id": "creator4", "content_group_id": None},
    }
    enriched = []
    for row in gold_rows:
        source = canonical[row["post_id"]]
        enriched.append({**row, "blogger_id": source["blogger_id"], "content_group_id": source["content_group_id"]})

    groups = SPLIT.build_split_groups(enriched)
    assignments, _ = SPLIT.split_groups(groups, seed=42)
    leakage = SPLIT.validate_split_leakage(enriched, assignments)
    assert leakage["post_leakage_count"] == 0
    assert leakage["creator_leakage_count"] == 0
    assert leakage["near_duplicate_leakage_count"] == 0
    assert sum(len(ids) for ids in assignments.values()) == 4

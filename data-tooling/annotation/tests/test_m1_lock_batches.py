from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "m1_lock_batches.py"
SPEC = importlib.util.spec_from_file_location("m1_lock_batches", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_reads_current_formalization_candidate_digest() -> None:
    digest = "a" * 64
    payload = {"formal_candidates": {"sha256": digest, "record_count": 2932}}
    assert MODULE.recorded_formal_candidate_sha(payload) == digest


def test_reads_legacy_formalization_candidate_digest() -> None:
    digest = "b" * 64
    payload = {"files": {"formal_eligible_candidates.jsonl": digest}}
    assert MODULE.recorded_formal_candidate_sha(payload) == digest

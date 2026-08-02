"""Persistent, queryable records for one complete analysis decision chain."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from ..contracts import EvidenceBundle, PostRecord, RunMetadata, VerdictReport
from ..orchestration import RunEvent


class RunRecord(BaseModel):
    post: PostRecord
    evidence_bundle: EvidenceBundle
    verdict_report: VerdictReport
    run_metadata: RunMetadata
    run_events: list[RunEvent]
    readable_report: str


class RunStore(Protocol):
    def put(self, record: RunRecord) -> None:
        ...

    def get(self, run_id: str) -> RunRecord | None:
        ...


class JsonRunStore:
    """One atomic JSON file per run; designed for local reproducibility."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @staticmethod
    def _safe_run_id(run_id: str) -> str:
        if not run_id or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for char in run_id
        ):
            raise ValueError("run_id contains unsafe path characters")
        return run_id

    def _path(self, run_id: str) -> Path:
        return self.directory / f"{self._safe_run_id(run_id)}.json"

    def put(self, record: RunRecord) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(record.run_metadata.run_id)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(target)

    def get(self, run_id: str) -> RunRecord | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        return RunRecord.model_validate_json(path.read_text(encoding="utf-8"))

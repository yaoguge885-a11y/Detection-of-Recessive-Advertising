"""Bounded parallel annotation with version-bound, per-record checkpoints.

Checkpoints are local research artifacts.  They are not human annotations or
formal Gold.  A resume requires identical inputs, guide, settings and code.
"""
from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence


def write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class BatchSession:
    """Hold an output-directory lock and own one immutable batch configuration."""

    def __init__(self, output_dir: Path, config: Mapping[str, Any], resume: str | None):
        self.output_dir = output_dir.resolve()
        self.config = dict(config)
        self.resume = resume
        self.records: dict[int, dict[str, Any]] = {}

    def __enter__(self) -> "BatchSession":
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lock = self.output_dir / ".batch.lock"
        try:
            descriptor = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ValueError("output directory is locked; check the owning process before removing .batch.lock") from exc
        os.close(descriptor)
        try:
            self._load()
        except BaseException:
            self.lock.unlink()
            raise
        return self

    def _load(self) -> None:
        if self.resume == "latest":
            candidates = sorted(self.output_dir.glob("run_config_*.json"))
            if not candidates:
                raise ValueError("no version-bound checkpoint; legacy progress files cannot be resumed")
            self.batch_id = candidates[-1].stem.removeprefix("run_config_")
        elif self.resume:
            if not re.fullmatch(r"[0-9_]+", self.resume):
                raise ValueError("invalid resume batch ID")
            self.batch_id = self.resume
        else:
            self.batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        config_path = self.output_dir / f"run_config_{self.batch_id}.json"
        self.checkpoints = self.output_dir / f"checkpoints_{self.batch_id}"
        if self.resume:
            if not config_path.is_file() or not self.checkpoints.is_dir():
                raise ValueError("version-bound batch configuration/checkpoint directory is missing")
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            if saved != self.config:
                raise ValueError("resume configuration mismatch: input, guide, selection, media, code or settings changed")
        else:
            if config_path.exists() or self.checkpoints.exists():
                raise FileExistsError("batch already exists")
            self.checkpoints.mkdir()
            write_json_atomic(config_path, self.config)
        selected = self.config["post_ids"]
        for path in sorted(self.checkpoints.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            ordinal = payload.get("ordinal")
            if (type(ordinal) is not int or not 0 <= ordinal < len(selected)
                    or path.stem != f"{ordinal:08d}"
                    or payload.get("post_id") != selected[ordinal]
                    or payload.get("audit", {}).get("post_id") != selected[ordinal]
                    or payload.get("audit", {}).get("tier") not in {"auto", "suggest", "manual"}
                    or ordinal in self.records):
                raise ValueError("checkpoint identity/order is invalid")
            self.records[ordinal] = payload

    def save(self, ordinal: int, record: dict[str, Any]) -> None:
        if ordinal in self.records:
            raise ValueError("refusing to overwrite a completed checkpoint")
        payload = {**record, "ordinal": ordinal, "post_id": self.config["post_ids"][ordinal]}
        write_json_atomic(self.checkpoints / f"{ordinal:08d}.json", payload)
        self.records[ordinal] = payload

    def export(self) -> dict[str, Path]:
        """Rebuild ordered projections; a resume never appends duplicate output."""
        paths = {kind: self.output_dir / f"{kind}_{self.batch_id}.jsonl"
                 for kind in ("auto", "suggest", "audit", "progress")}
        for kind, path in paths.items():
            temporary = path.with_name(path.name + ".writing")
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                for ordinal in sorted(self.records):
                    record = self.records[ordinal]
                    audit = record["audit"]
                    value = ({"post_id": record["post_id"], "tier": audit["tier"],
                              "label": audit["label_normalized"],
                              "fallback": audit["fallback"], "error": bool(audit["error"])}
                             if kind == "progress" else record.get(kind))
                    if value is not None:
                        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
            temporary.replace(path)
        return paths

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.lock.unlink()


def run_ordered(
    posts: Sequence[dict[str, Any]],
    session: BatchSession,
    worker: Callable[[dict[str, Any]], dict[str, Any]],
    num_parallel: int,
) -> None:
    """Keep at most num_parallel jobs in flight and persist in manifest order."""
    if num_parallel < 1:
        raise ValueError("num_parallel must be positive")
    pending = iter((i, post) for i, post in enumerate(posts) if i not in session.records)
    with ThreadPoolExecutor(max_workers=num_parallel) as pool:
        futures: deque = deque()
        for _ in range(num_parallel):
            item = next(pending, None)
            if item is not None:
                ordinal, post = item
                futures.append((ordinal, pool.submit(worker, post)))
        while futures:
            ordinal, future = futures.popleft()
            session.save(ordinal, future.result())
            item = next(pending, None)
            if item is not None:
                ordinal, post = item
                futures.append((ordinal, pool.submit(worker, post)))

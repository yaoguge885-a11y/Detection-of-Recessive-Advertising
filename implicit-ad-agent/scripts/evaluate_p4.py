#!/usr/bin/env python3
"""Generate explicit, zero-network P4 engineering evaluation reports."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from impad.creator_shift import (
    CreatorShiftBenchmarkFixture,
    run_creator_shift_benchmark,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate version-bound P4 engineering reports.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    creator_shift = commands.add_parser(
        "creator-shift",
        help="Evaluate deterministic CreatorShift baselines.",
    )
    creator_shift.add_argument("--fixture", type=Path, required=True)
    creator_shift.add_argument("--output", type=Path, required=True)
    return parser


def _write_report(output: Path, payload: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "creator-shift":
        fixture = CreatorShiftBenchmarkFixture.model_validate_json(
            args.fixture.read_text(encoding="utf-8")
        )
        report = run_creator_shift_benchmark(fixture)
        _write_report(args.output, report.model_dump_json(indent=2))
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

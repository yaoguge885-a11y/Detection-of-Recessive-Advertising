"""Command line entry point for the isolated history baseline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .contracts import BaselineInputError, load_input_bundle
from .features import build_common_cohort
from .reporting import build_report, serialize_report
from .runner import run_baselines


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--content", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--train-ids", required=True, type=Path)
    parser.add_argument("--dev-ids", required=True, type=Path)
    parser.add_argument("--test-ids", required=True, type=Path)
    parser.add_argument("--split-report", required=True, type=Path)
    parser.add_argument("--m1-gate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--evaluation-split", choices=("train", "dev", "test"), default="dev"
    )
    parser.add_argument(
        "--confirm-test-evaluation",
        action="store_true",
        help="explicitly confirm a formal test-split evaluation",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m baseline.cli",
        description="Run the privacy-safe merged-history baseline.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    synthetic = subparsers.add_parser(
        "synthetic", help="run the versioned anonymous fixture"
    )
    _add_common_arguments(synthetic)
    synthetic.add_argument("--fixture-metadata", required=True, type=Path)

    formal = subparsers.add_parser(
        "formal", help="run an M1-approved formal Gold input"
    )
    _add_common_arguments(formal)
    return parser


def _write_atomic(output_path: Path, report: dict[str, object]) -> None:
    """Serialize and replace the final report only after a successful write."""

    serialized = serialize_report(report)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        temporary_path.write_text(serialized + "\n", encoding="utf-8")
        temporary_path.replace(output_path)
    except OSError as exc:
        raise BaselineInputError("output report could not be written") from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            # A failed cleanup must not obscure the original input/output error.
            pass


def _run(arguments: argparse.Namespace) -> None:
    input_kwargs = {
        "mode": arguments.mode,
        "content_path": arguments.content,
        "gold_path": arguments.gold,
        "train_ids_path": arguments.train_ids,
        "dev_ids_path": arguments.dev_ids,
        "test_ids_path": arguments.test_ids,
        "split_report_path": arguments.split_report,
        "m1_gate_path": arguments.m1_gate,
        "evaluation_split": arguments.evaluation_split,
        "confirm_test_evaluation": arguments.confirm_test_evaluation,
    }
    if arguments.mode == "synthetic":
        input_kwargs["fixture_metadata_path"] = arguments.fixture_metadata

    bundle = load_input_bundle(**input_kwargs)
    cohort = build_common_cohort(bundle)
    results = run_baselines(bundle, cohort)
    report = build_report(bundle, cohort, results)
    _write_atomic(arguments.output, report)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        _run(arguments)
    except BaselineInputError as exc:
        print(f"baseline blocked: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by subprocess tests
    raise SystemExit(main())


__all__ = ["build_parser", "main"]

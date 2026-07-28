#!/usr/bin/env python3
"""Generate explicit, zero-network P3 engineering evaluation reports."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from impad.evaluation import (
    ClassificationEvaluationFixture,
    build_classification_report,
)
from impad.rag import (
    load_legal_corpus,
    load_retrieval_benchmark,
    run_p3_retrieval_benchmark,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate version-bound P3 engineering reports.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    retrieval = commands.add_parser(
        "retrieval",
        help="Evaluate deterministic hybrid legal retrieval.",
    )
    retrieval.add_argument("--corpus", type=Path, required=True)
    retrieval.add_argument("--benchmark", type=Path, required=True)
    retrieval.add_argument("--output", type=Path, required=True)
    classification = commands.add_parser(
        "classification",
        help="Analyze errors in an explicit classification fixture.",
    )
    classification.add_argument("--predictions", type=Path, required=True)
    classification.add_argument("--output", type=Path, required=True)
    return parser


def _write_report(output: Path, payload: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "retrieval":
        corpus = load_legal_corpus(args.corpus)
        benchmark = load_retrieval_benchmark(args.benchmark)
        report = run_p3_retrieval_benchmark(corpus, benchmark)
        _write_report(args.output, report.model_dump_json(indent=2))
        return 0
    if args.command == "classification":
        fixture = ClassificationEvaluationFixture.model_validate_json(
            args.predictions.read_text(encoding="utf-8")
        )
        report = build_classification_report(fixture)
        _write_report(args.output, report.model_dump_json(indent=2))
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

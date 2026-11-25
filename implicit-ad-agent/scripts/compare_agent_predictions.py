#!/usr/bin/env python3
"""Compare two same-target label sets without running OCR or model inference.

Accepted input formats
----------------------
1. Expanded-agent JSON/JSONL rows.  A JSON object may contain a ``rows``
   array (the existing ``expanded_agent.json`` envelope), or JSONL may contain
   one row per line.  Each row has ``post_id``, ``gold_label`` and a
   ``predictions`` object such as ``{"current": "非广", "own_3": "非广"}``.
   Select an arm with ``--before-arm`` and ``--after-arm``.
2. Minimal JSON/JSONL rows.  Each row has exactly the useful fields
   ``post_id``, ``label`` (the three-class gold label), and
   ``predicted_label`` (one of the three labels or ``需复核``).  Arm flags are
   ignored for rows that already provide ``predicted_label``.

The join is strict by ``post_id``: duplicate IDs, mismatched cohorts, and
conflicting gold labels fail the command.  ``需复核`` is an incorrect
prediction for accuracy/F1 and recall, while normal false positives count
only ``明广``/``暗广`` predictions on ``非广`` posts; reviews are reported
separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from impad.evaluation.paired import (  # noqa: E402
    PairingError,
    build_paired_report,
    load_prediction_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reproducibly compare before/after labels on the exact same "
            "post_id cohort. This is label-only; it does not run OCR."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--before",
        type=Path,
        required=True,
        help="before JSON or JSONL prediction set",
    )
    parser.add_argument(
        "--after",
        type=Path,
        required=True,
        help="after JSON or JSONL prediction set",
    )
    parser.add_argument(
        "--before-arm",
        default="current",
        help="expanded-agent arm for --before (default: current)",
    )
    parser.add_argument(
        "--after-arm",
        default="own_3",
        help="expanded-agent arm for --after (default: own_3)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="path for the UTF-8 JSON report",
    )
    return parser


def _write_report(output: Path, payload: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        before, before_source = load_prediction_file(
            args.before,
            arm=args.before_arm,
        )
        after, after_source = load_prediction_file(
            args.after,
            arm=args.after_arm,
        )
        report = build_paired_report(
            before,
            after,
            source_metadata={"before": before_source, "after": after_source},
        )
    except (OSError, PairingError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _write_report(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

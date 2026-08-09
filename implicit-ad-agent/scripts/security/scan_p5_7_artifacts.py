"""Command-line P5.7 artifact scanner with secret-free JSON output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from impad.security.artifact_scan import scan_artifacts  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan explicit generated artifact paths for P5.7 leaks."
    )
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        dest="paths",
        help="Artifact file or directory. Repeat for multiple paths.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings = scan_artifacts(args.paths)
    print(json.dumps(
        [item.model_dump(mode="json") for item in findings],
        ensure_ascii=False,
    ))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())

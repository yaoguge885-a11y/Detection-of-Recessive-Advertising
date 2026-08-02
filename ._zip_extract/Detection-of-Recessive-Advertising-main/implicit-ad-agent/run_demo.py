"""Run de-identified samples through the unified P3 analysis service.

Usage:
    python run_demo.py
    python run_demo.py --llm
    python run_demo.py --image path/to.jpg
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from impad.services import (
    AnalysisResult,
    AnalysisService,
    get_default_analysis_service,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SAMPLES = PROJECT_ROOT / "samples" / "sample_posts.json"


def run_demo(
    samples_path: str | Path = DEFAULT_SAMPLES,
    *,
    image_path: str | None = None,
    service: AnalysisService | None = None,
) -> list[AnalysisResult]:
    """Analyze fixed samples locally through the shared service boundary."""

    if image_path:
        posts = [{
            "text": "分享一下最近入手的好物～",
            "blogger": "demo",
            "image_path": image_path,
        }]
    else:
        posts = json.loads(
            Path(samples_path).read_text(encoding="utf-8")
        )
    active_service = service or get_default_analysis_service()
    return [
        active_service.analyze(post, runtime_mode="local")
        for post in posts
    ]


def main(
    argv: Sequence[str] | None = None,
    *,
    samples_path: str | Path = DEFAULT_SAMPLES,
    service: AnalysisService | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="deprecated compatibility flag; analysis remains deterministic",
    )
    parser.add_argument(
        "--image",
        help="optional local image path for the real vision pipeline",
    )
    args = parser.parse_args(argv)

    if args.llm:
        print(">> --llm 已弃用；继续使用零 Key 的确定性 AnalysisService。\n")

    results = run_demo(
        samples_path,
        image_path=args.image,
        service=service,
    )
    for index, result in enumerate(results, start=1):
        print(f"===== 分析结果 {index} =====")
        print(result.readable_report)
        print(f"run_id：{result.run_metadata.run_id}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

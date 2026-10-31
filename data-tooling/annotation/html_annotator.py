#!/usr/bin/env python3
"""Command-line entry point for the local HTML annotation workbench.

Example (PowerShell, from the repository root)::

    python data-tooling/annotation/html_annotator.py `
      --dataset data/synthetic/simulated_posts_v1.json `
      --dataset-id synthetic_demo `
      --batch-id batch_a `
      --annotator-id alice `
      --media-root data/synthetic `
      --no-auto-suggest

The server binds to 127.0.0.1 only.  Annotation logs are written under the
Git-ignored ``data/annotations/workbench`` tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from annotation_workbench.ollama_bridge import OllamaBridge
from annotation_workbench.server import WorkbenchApp, run_server
from annotation_workbench.store import (
    DEFAULT_GUIDE_VERSION,
    AnnotationStore,
    BatchSpec,
    WorkbenchError,
    prepare_batch,
    safe_component,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "annotations" / "workbench"
DEFAULT_GUIDE = REPO_ROOT / "docs" / "annotation_guide_v1.md"


def _default_id(path: Path) -> str:
    stem = path.stem
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in stem).strip("._-")
    return cleaned[:80] or "dataset"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本机 HTML 人工标注工作台（只监听 127.0.0.1）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", required=True, type=Path, help="帖子数据 JSON/JSONL")
    parser.add_argument("--dataset-id", default=None, help="数据集标识（目录名，默认取数据文件名）")
    parser.add_argument("--batch-id", default="batch1", help="批次标识（目录名）")
    parser.add_argument("--annotator-id", required=True, help="标注人标识；不同人必须不同")
    parser.add_argument("--media-root", required=True, type=Path, help="本地媒体根目录（路径不得越出）")
    parser.add_argument("--manifest", type=Path, default=None, help="固定 post_id 清单（txt/json/jsonl/csv）")
    parser.add_argument(
        "--manifest-role", choices=("exploratory", "approved"), default="exploratory",
        help="清单用途；approved 只代表用户声明，工具不验证批准来源",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="本地标注输出根目录")
    parser.add_argument("--guide", type=Path, default=DEFAULT_GUIDE, help="权威标注指南")
    parser.add_argument("--model", default="qwen3.5:9b", help="Ollama 模型")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434", help="Ollama 地址，必须是回环地址")
    parser.add_argument("--timeout", type=float, default=120.0, help="Ollama 单次请求超时秒数")
    parser.add_argument("--num-predict", type=int, default=1536, help="模型最大生成 token")
    parser.add_argument("--comment-limit", type=int, default=30, help="发给模型的当前帖评论条数上限")
    parser.add_argument(
        "--no-auto-suggest", action="store_true",
        help="关闭模型建议，进入真正的独立盲标（/api/suggest 返回 403）",
    )
    parser.add_argument("--port", type=int, default=8765, help="端口（0 表示随机空闲端口）")
    parser.add_argument("--check-only", action="store_true", help="只校验数据/清单/批次并打印摘要，不启动服务")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset = args.dataset.expanduser().resolve()
        media_root = args.media_root.expanduser().resolve()
        manifest = args.manifest.expanduser().resolve() if args.manifest else None
        guide = args.guide.expanduser().resolve()
        if not guide.is_file():
            raise WorkbenchError(f"标注指南不存在：{guide}")
        if args.manifest_role == "approved" and manifest is None:
            raise WorkbenchError("--manifest-role approved 必须同时提供 --manifest")
        if args.num_predict <= 0:
            raise WorkbenchError("--num-predict 必须为正整数")
        if args.comment_limit < 0:
            raise WorkbenchError("--comment-limit 不能为负数")
        dataset_id = safe_component(args.dataset_id or _default_id(dataset), field_name="dataset_id")
        batch_id = safe_component(args.batch_id, field_name="batch_id")
        annotator_id = safe_component(args.annotator_id, field_name="annotator_id")
        guide_text = guide.read_text(encoding="utf-8-sig")
        spec = BatchSpec(
            dataset_id=dataset_id,
            batch_id=batch_id,
            annotator_id=annotator_id,
            dataset_path=dataset,
            output_root=args.output_root.expanduser().resolve(),
            media_root=media_root,
            manifest_path=manifest,
            manifest_role=args.manifest_role,
            guide_version=DEFAULT_GUIDE_VERSION,
            guide_sha256=sha256_text(guide_text),
        )
        prepared = prepare_batch(spec)
        if args.check_only:
            summary = {
                "dataset_id": dataset_id,
                "batch_id": batch_id,
                "annotator_id": annotator_id,
                "post_count": len(prepared.ordered_ids),
                "manifest_role": spec.manifest_role,
                "formal_gold_allowed": prepared.formal_gold_allowed,
                "manifest_validation": prepared.manifest_validation,
                "warnings": prepared.warnings,
                "batch_dir": str(prepared.batch_dir),
                "batch_manifest": prepared.manifest,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        bridge = OllamaBridge(
            model=args.model,
            url=args.ollama_url,
            timeout=args.timeout,
            guide_path=guide,
            num_predict=args.num_predict,
            comment_limit=args.comment_limit,
            enabled=not args.no_auto_suggest,
        )
        store = AnnotationStore(prepared)
        app = WorkbenchApp(store, bridge, auto_suggest=not args.no_auto_suggest)
        run_server(app, port=args.port)
        return 0
    except WorkbenchError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

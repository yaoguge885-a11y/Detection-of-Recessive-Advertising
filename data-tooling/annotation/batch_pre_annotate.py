#!/usr/bin/env python3
"""批量预标注脚本 —— 正式双标前先跑一轮全量自动判断，减少人工工作量。

管线（co-pilot-auto-judge-design v1.0）：
  1. 逐条加载帖子
  2. 计算 6 维关键词向量（本地免费，<0.1s）
  3. 可选：YOLO+OCR 图片分析（需要 vision 依赖，失败自动降级为纯文本）
  4. Qwen3.5 9B via Ollama 综合判定（实测时延写入审计）
  5. 三级分类：
       - 🟢 auto   (threshold > 0 且 confidence >= threshold) → 自动保存工程建议记录
       - 🟡 suggest (0.55 <= confidence < threshold) → 输出建议，供人工确认
       - 🔴 manual  (confidence < 0.55)              → 不输出建议
  6. uncertain 始终人工处理；阈值为 0 禁用自动接收
  7. Ollama 不可用/超时/非 JSON → 记录错误与关键词规则回退

用法：
  python data-tooling/annotation/batch_pre_annotate.py \
    --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
    --output-dir data/annotations/preannotated \
    --auto-threshold 0.85 \
    --ollama-model qwen3.5:9b \
    --limit 100

输出：
  <output-dir>/auto_<timestamp>.jsonl     自动保存的标注记录（annotator_id=system）
  <output-dir>/suggest_<timestamp>.jsonl  建议记录（等待人工确认）
  <output-dir>/stats_<timestamp>.json     统计报告（各区间分布/耗时/回退数）
  <output-dir>/audit_<timestamp>.jsonl    每条调用的版本与证据审计
  <output-dir>/checkpoints_<timestamp>/  原子检查点，按清单顺序恢复输出
"""
from __future__ import annotations

import argparse
import math
import threading
from collections import Counter
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Windows GBK 控制台兼容：强制 UTF-8 输出 ──
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 项目根目录 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from auto_judge import (  # type: ignore # noqa: E402
    OLLAMA_DEFAULT_MODEL,
    OLLAMA_DEFAULT_URL,
    OLLAMA_TIMEOUT,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX,
    OLLAMA_WARMUP_TIMEOUT,
    DEFAULT_AUTO_THRESHOLD,
    GUIDE_VERSION,
    SUGGESTION_LOWER_BOUND,
    classify_confidence,
    compute_keyword_weights_for_post,
    run_auto_judge,
    warm_up_model,
)

CST = timezone(timedelta(hours=8))


def file_sha256(path: Path) -> str:
    """流式计算文件 SHA-256，避免把候选文件再次整体读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 文件（兼容美化打印的多行 JSON）。"""
    raw_text = path.read_text(encoding="utf-8-sig")
    records: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw_text)
    while idx < n:
        while idx < n and raw_text[idx] in " \t\n\r":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(raw_text, idx)
            if isinstance(obj, dict):
                records.append(obj)
            idx = end
        except json.JSONDecodeError:
            nxt = raw_text.find("{", idx + 1)
            if nxt == -1:
                break
            idx = nxt
    return records


def parse_post_id_manifest(payload: Any) -> List[str]:
    """从 JSON manifest 提取唯一 post_id，严格保留 manifest 顺序。"""
    values: Any = payload
    if isinstance(payload, dict):
        if "items" in payload:
            values = payload["items"]
        elif "post_ids" in payload:
            values = payload["post_ids"]
        else:
            raise ValueError("manifest 必须包含 items 或 post_ids")
    if not isinstance(values, list) or not values:
        raise ValueError("manifest 的 post_id 列表不能为空")

    post_ids: List[str] = []
    seen = set()
    for index, value in enumerate(values, 1):
        raw = value.get("post_id") if isinstance(value, dict) else value
        post_id = str(raw or "").strip()
        if not post_id:
            raise ValueError(f"manifest 第 {index} 项缺少 post_id")
        if post_id in seen:
            raise ValueError(f"manifest 含重复 post_id: {post_id}")
        seen.add(post_id)
        post_ids.append(post_id)
    return post_ids


def _get_vision_models():
    """线程安全地获取 YOLO+OCR 模型（只加载一次，失败缓存异常）。"""
    global _vision_error
    with _vision_lock:
        if _vision_error is not None:
            raise _vision_error
        if _vision_models["yolo"] is None:
            try:
                from auto_image_annotate import load_yolo, load_ocr  # type: ignore
                _vision_models["yolo"] = load_yolo()
                _vision_models["ocr"] = load_ocr()
            except Exception as exc:  # noqa: BLE001 - 缺依赖/加载失败都缓存
                _vision_error = exc
                raise
    return _vision_models["yolo"], _vision_models["ocr"]


def analyze_images_for_post(post: Dict[str, Any], media_base: Path) -> Dict[int, Dict]:
    """对帖子中的内容图片跑 YOLO+OCR，返回 {序号: 分析结果}。

    任一环节失败（缺依赖/文件缺失/异常）都降级为 {}，不中断批处理。
    模型使用线程安全全局缓存，只加载一次。
    """
    results: Dict[int, Dict] = {}
    try:
        from auto_image_annotate import analyze_image  # type: ignore
    except Exception:
        return results  # vision 依赖未安装，跳过图片分析

    try:
        yolo, ocr = _get_vision_models()
    except Exception:
        return results  # 模型加载失败，降级

    try:
        import re
        from image_prefilter import extract_content_image_indices  # type: ignore
    except Exception:
        text = post.get("text") or ""
        indices = set()
        for m in re.finditer(r"<图片(\d+)>", text):
            indices.add(int(m.group(1)) - 1)
        if not indices:
            return results
    else:
        indices = extract_content_image_indices(post.get("text") or "")

    media = post.get("media", [])
    for i in sorted(indices):
        if i >= len(media):
            continue
        ref = media[i].get("ref", "")
        img_path = media_base / ref if ref else None
        if not img_path or not img_path.exists():
            results[i] = {"error": "file missing"}
            continue
        try:
            analysis = analyze_image(yolo, ocr, img_path, i + 1, ref, "")
            results[i] = {
                "detected_elements": analysis.get("detected_elements", {}),
                "visual_evidence_codes": analysis.get("visual_evidence_codes", []),
                "description": analysis.get("description", ""),
                "ocr_text": analysis.get("ocr_text"),
                "analysis_method": "yolo_ocr_auto",
            }
        except Exception as exc:
            results[i] = {"error": str(exc)[:100]}
    return results


from batch_annotation_runtime import BatchSession, run_ordered, write_json_atomic

_vision_models = {"yolo": None, "ocr": None}
_vision_lock = threading.Lock()
_vision_error = None

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'Outputs: auto_*.jsonl, suggest_*.jsonl, audit_*.jsonl, progress_*.jsonl, '
        'stats_*.json and version-bound checkpoints. These are not formal human labels.'))
    parser.add_argument('--input', '-i', required=True)
    parser.add_argument('--guide', default='docs/annotation_guide_v1.md')
    parser.add_argument('--post-id-manifest', default='')
    parser.add_argument('--output-dir', '-o', default='data/annotations/preannotated')
    parser.add_argument('--ollama-model', default=OLLAMA_DEFAULT_MODEL)
    parser.add_argument('--ollama-url', default=OLLAMA_DEFAULT_URL)
    parser.add_argument('--timeout', type=float, default=OLLAMA_TIMEOUT)
    parser.add_argument('--auto-threshold', type=float, default=DEFAULT_AUTO_THRESHOLD)
    parser.add_argument('--keep-alive', default=OLLAMA_KEEP_ALIVE)
    parser.add_argument('--num-ctx', type=int, default=OLLAMA_NUM_CTX)
    parser.add_argument('--no-warmup', action='store_true')
    parser.add_argument('--no-images', action='store_true')
    parser.add_argument('--media-base', default='data')
    parser.add_argument('--limit', '-n', type=int, default=0)
    parser.add_argument('--annotator-id', default='system')
    parser.add_argument('--num-parallel', type=int, default=1,
                        help='bounded in-flight requests; defaults to 1 for calibration')
    parser.add_argument('--image-workers', type=int, default=1)
    parser.add_argument('--resume', nargs='?', const='latest', default=None,
                        help='resume a version-bound batch (optional batch ID)')
    args = parser.parse_args(argv)
    if min(args.num_ctx, args.num_parallel, args.image_workers) < 1:
        parser.error('context and worker counts must be positive')
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout must be positive and finite')
    if not math.isfinite(args.auto_threshold) or not 0 <= args.auto_threshold <= 1:
        parser.error('auto-threshold must be between 0 and 1')
    if args.limit < 0:
        parser.error('limit must be nonnegative')
    try:
        input_path = Path(args.input).resolve()
        guide_path = Path(args.guide).resolve()
        guide_text = guide_path.read_text(encoding='utf-8-sig')
        if not guide_text.strip():
            raise ValueError('authoritative guide is empty')
        guide_sha = file_sha256(guide_path)
        all_posts = load_jsonl(input_path)
        by_id = {}
        for post in all_posts:
            pid = str(post.get('post_id') or '').strip()
            if not pid or pid in by_id:
                raise ValueError('input post IDs must be nonempty and unique')
            by_id[pid] = post
        manifest_info = None
        posts = all_posts
        if args.post_id_manifest:
            manifest_path = Path(args.post_id_manifest).resolve()
            ids = parse_post_id_manifest(json.loads(manifest_path.read_text(encoding='utf-8-sig')))
            if any(pid not in by_id for pid in ids):
                raise ValueError('manifest contains IDs absent from input')
            posts = [by_id[pid] for pid in ids]
            manifest_info = {'path': str(manifest_path), 'sha256': file_sha256(manifest_path),
                             'post_id_count': len(ids)}
        if args.limit:
            posts = posts[:args.limit]
        if not posts:
            raise ValueError('selected batch is empty')
        media_base = Path(args.media_base).resolve()
        media_digests = {}
        if not args.no_images:
            for post in posts:
                for media in post.get('media') or []:
                    ref = media.get('ref')
                    if not ref or ref in media_digests:
                        continue
                    path = (media_base / ref).resolve()
                    if not path.is_relative_to(media_base):
                        raise ValueError('media reference escapes media root')
                    media_digests[ref] = file_sha256(path) if path.is_file() else 'missing'
        code_dir = Path(__file__).resolve().parent
        config = {
            'schema_version': 'm1_audited_parallel_batch_v1',
            'post_ids': [str(post['post_id']) for post in posts],
            'input': {'path': str(input_path), 'sha256': file_sha256(input_path),
                      'record_count': len(all_posts), 'selected_count': len(posts)},
            'guide': {'path': str(guide_path), 'sha256': guide_sha, 'version': GUIDE_VERSION},
            'selection_manifest': manifest_info,
            'code_sha256': {name: file_sha256(code_dir / name) for name in (
                'batch_pre_annotate.py', 'batch_annotation_runtime.py', 'auto_judge.py',
                'manual_review_annotate.py', 'auto_image_annotate.py', 'image_prefilter.py')},
            'settings': vars(args) | {'resume': None, 'no_warmup': None},
            'media_sha256': media_digests,
        }
        with BatchSession(Path(args.output_dir), config, args.resume) as session:
            started = time.perf_counter()
            prior_count = len(session.records)
            warmup_ok = None
            warmup_sec = 0.0
            if not args.no_warmup and prior_count < len(posts):
                warmup_start = time.perf_counter()
                warmup_ok = warm_up_model(model=args.ollama_model, url=args.ollama_url,
                    timeout=OLLAMA_WARMUP_TIMEOUT, keep_alive=args.keep_alive, num_ctx=args.num_ctx)
                warmup_sec = round(time.perf_counter() - warmup_start, 3)
            image_slots = threading.BoundedSemaphore(args.image_workers)

            def worker(post):
                image_analyses = None
                if not args.no_images:
                    with image_slots:
                        image_analyses = analyze_images_for_post(post, media_base)
                weights = compute_keyword_weights_for_post(post.get('text') or '')
                start = time.perf_counter()
                result = run_auto_judge(post, image_analyses=image_analyses,
                    keyword_weights=weights, model=args.ollama_model, url=args.ollama_url,
                    timeout=args.timeout, auto_threshold=args.auto_threshold,
                    keep_alive=args.keep_alive, guide_text=guide_text, guide_version=GUIDE_VERSION,
                    guide_sha256=guide_sha, media_analysis_requested=not args.no_images,
                    collection_complete=post.get('collection_complete'), num_ctx=args.num_ctx)
                latency = round(time.perf_counter() - start, 3)
                suggestion = result.get('suggestion')
                audit = {
                    'post_id': str(post['post_id']), 'generated_at': datetime.now(CST).isoformat(),
                    'tier': result['tier'], 'label_raw': result.get('label_raw'),
                    'label_normalized': suggestion.get('label') if suggestion else None,
                    'confidence': suggestion.get('confidence') if suggestion else None,
                    'confidence_raw': suggestion.get('confidence_raw') if suggestion else None,
                    'backend': result.get('backend', 'none'), 'fallback': bool(result.get('fallback')),
                    'error': result.get('error'), 'model': args.ollama_model,
                    'guide_version': GUIDE_VERSION, 'guide_sha256': guide_sha,
                    'media_analysis_requested': not args.no_images,
                    'media_evidence_status': result.get('media_evidence_status', 'unknown'),
                    'image_analysis_count': len(image_analyses or {}),
                    'collection_complete': result.get('collection_complete', 'unknown'),
                    'num_ctx': args.num_ctx, 'latency_sec': latency, 'suggestion': suggestion,
                }
                auto = None
                suggested = None
                if audit['tier'] == 'auto':
                    auto = dict(result['record'])
                    auto['annotator_id'] = args.annotator_id
                elif audit['tier'] == 'suggest':
                    suggested = dict(audit, annotator_id='system', keyword_weights=weights,
                                     image_analyses=image_analyses or {})
                return {'audit': audit, 'auto': auto, 'suggest': suggested}

            interrupted = False
            try:
                run_ordered(posts, session, worker, args.num_parallel)
            except KeyboardInterrupt:
                interrupted = True
            finally:
                paths = session.export()
            audits = [session.records[i]['audit'] for i in sorted(session.records)]
            latencies = [item['latency_sec'] for item in audits]
            subsequent = latencies[1:]
            tiers = {name: sum(a['tier'] == name for a in audits) for name in ('auto', 'suggest', 'manual')}
            stats = {
                'status': 'interrupted' if interrupted else 'completed',
                'batch_id': session.batch_id, 'input': config['input'], 'guide': config['guide'],
                'selection_manifest': manifest_info, 'code_sha256': config['code_sha256'],
                'command': [sys.executable, __file__, *(sys.argv[1:] if argv is None else argv)],
                'total': len(posts), 'total_processed': len(audits),
                'session_processed': len(audits) - prior_count, 'num_parallel': args.num_parallel,
                'image_workers': args.image_workers, 'tiers': tiers, 'auto_saved': tiers['auto'],
                'suggested': tiers['suggest'], 'audit_count': len(audits),
                'fallback_count': sum(a['fallback'] for a in audits),
                'error_count': sum(bool(a['error']) for a in audits),
                'labels': dict(Counter(a['label_normalized'] for a in audits if a['label_normalized'])),
                'backends': dict(Counter(a['backend'] for a in audits)),
                'media_evidence_status': dict(Counter(a['media_evidence_status'] for a in audits)),
                'raw_normalized_difference_count': sum(a['label_raw'] is not None and
                    str(a['label_raw']) != str(a['label_normalized']) for a in audits),
                'ollama_model': args.ollama_model, 'ollama_url': args.ollama_url, 'num_ctx': args.num_ctx,
                'auto_threshold': args.auto_threshold, 'media_analysis_requested': not args.no_images,
                'media_base': str(media_base), 'keep_alive': args.keep_alive,
                'warmup_ok': warmup_ok, 'warmup_duration_sec': warmup_sec, 'latency_sec': latencies,
                'first_inference_sec': latencies[0] if latencies else None,
                'subsequent_median_sec': statistics.median(subsequent) if subsequent else None,
                'subsequent_p90_sec': (statistics.quantiles(subsequent, n=10, method='inclusive')[8]
                                     if len(subsequent) > 1 else subsequent[0] if subsequent else None),
                'duration_sec': round(time.perf_counter() - started, 3),
                'outputs': {name: str(path) for name, path in paths.items()},
                'output_sha256': {name: file_sha256(path) for name, path in paths.items()},
                'finished_at': datetime.now(CST).isoformat(),
            }
            stats_path = session.output_dir / f'stats_{session.batch_id}.json'
            write_json_atomic(stats_path, stats)
            print(json.dumps({'status': stats['status'], 'batch_id': session.batch_id,
                'audit_count': len(audits), 'session_processed': stats['session_processed'],
                'tiers': tiers, 'stats': str(stats_path)}, ensure_ascii=False, indent=2))
            return 130 if interrupted else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

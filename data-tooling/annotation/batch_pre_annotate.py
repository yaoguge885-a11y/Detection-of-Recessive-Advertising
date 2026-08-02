#!/usr/bin/env python3
"""批量预标注脚本 —— 正式双标前先跑一轮全量自动判断，减少人工工作量。

管线（co-pilot-auto-judge-design v1.0）+ 速度优化（序列批处理 + 异步流水线）：
  1. 逐条加载帖子
  2. 计算 6 维关键词向量（本地免费，<0.1s）
  3. 可选：YOLO+OCR 图片分析（线程池预取，模型只加载一次，失败降级为纯文本）
  4. Qwen3.5 9B via Ollama 综合判定（本地，2-4s/条）
  5. 三级分类：
       - 🟢 auto   (confidence >= --auto-threshold) → 自动保存标注记录
       - 🟡 suggest (0.55 <= confidence < threshold) → 输出建议，供人工确认
       - 🔴 manual  (confidence < 0.55)              → 不输出建议
  6. Ollama 不可用/超时/非 JSON → 关键词规则回退（见设计文档 4.4）

速度优化（2026-08-02 v2）：
  - 客户端 asyncio 并发窗口（--num-parallel）：让 Ollama 服务端有多个在飞请求
    可做序列批处理（配合 ollama_server.py 的 OLLAMA_NUM_PARALLEL）
  - 图片分析预取流水线：后台线程池提前分析后续帖子的图片，
    GPU(LLM) 与 CPU/GPU(YOLO+OCR) 同时忙碌，消除串行停顿
  - YOLO/OCR 模型全局缓存：不再每条帖子重新加载模型

用法：
  python data-tooling/annotation/batch_pre_annotate.py \
    --input data/run_outputs/merged_20260728/anonymized_posts.jsonl \
    --output-dir data/annotations/preannotated \
    --auto-threshold 0.85 \
    --ollama-model qwen3.5:9b \
    --num-parallel 2 \
    --limit 100

输出：
  <output-dir>/auto_<timestamp>.jsonl     自动保存的标注记录（annotator_id=system）
  <output-dir>/suggest_<timestamp>.jsonl  建议记录（等待人工确认）
  <output-dir>/stats_<timestamp>.json     统计报告（各区间分布/耗时/回退数/吞吐）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
    OLLAMA_WARMUP_TIMEOUT,
    DEFAULT_AUTO_THRESHOLD,
    SUGGESTION_LOWER_BOUND,
    compute_keyword_weights_for_post,
    run_auto_judge,
    warm_up_model,
)

CST = timezone(timedelta(hours=8))

# ── YOLO/OCR 模型全局缓存（线程安全，避免每条帖子重新加载模型）──
_vision_models: Dict[str, Any] = {"yolo": None, "ocr": None}
_vision_lock = threading.Lock()
_vision_error: Optional[Exception] = None


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


# ════════════════════════════════════════════════════════════════════
# 断点续传：进度检查点
# ════════════════════════════════════════════════════════════════════
def find_latest_batch_ts(output_dir: Path) -> Optional[str]:
    """在输出目录中找到最近一个批次的时间戳（依据 progress_*.jsonl）。"""
    files = list(output_dir.glob("progress_*.jsonl"))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    name = files[0].name  # progress_20260802_192521.jsonl
    return name[len("progress_"):-len(".jsonl")]


def load_checkpoint(output_dir: Path, ts: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """加载断点检查点。

    Returns:
        (processed, stats)
        processed: {post_id: 检查点记录}，已完成帖子集合
        stats: 从检查点重建的统计（tiers/labels/fallback/error）
    """
    progress_path = output_dir / f"progress_{ts}.jsonl"
    processed: Dict[str, Dict[str, Any]] = {}
    stats: Dict[str, Any] = {
        "tiers": {"auto": 0, "suggest": 0, "manual": 0},
        "labels": {},
        "fallback_count": 0,
        "error_count": 0,
    }
    if not progress_path.exists():
        return processed, stats
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = rec.get("post_id", "")
        if not pid:
            continue
        processed[pid] = rec
        tier = rec.get("tier", "")
        if tier in stats["tiers"]:
            stats["tiers"][tier] += 1
        label = rec.get("label")
        if label:
            stats["labels"][label] = stats["labels"].get(label, 0) + 1
        if rec.get("fallback"):
            stats["fallback_count"] += 1
        if rec.get("error"):
            stats["error_count"] += 1
    return processed, stats


def write_progress(progress_path: Path, rec: Dict[str, Any]) -> None:
    """追加一条进度检查点（每条帖子完成后立即调用，崩溃/中断可恢复）。"""
    with progress_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


class ImagePrefetcher:
    """图片分析预取流水线：后台线程池提前分析后续帖子的图片。

    作用：GPU(LLM 推理) 与 CPU/GPU(YOLO+OCR) 同时忙碌，消除串行停顿。
    线程安全：Future 字典只在事件循环单线程内读写。
    """

    def __init__(self, posts: List[Dict], media_base: Path,
                 executor: ThreadPoolExecutor, window: int, enabled: bool):
        self.posts = posts
        self.media_base = media_base
        self.executor = executor
        self.window = max(window, 1)
        self.enabled = enabled
        self._futures: Dict[str, Any] = {}  # post_id -> concurrent Future
        self._idx = 0

    def _refill(self) -> None:
        """按窗口填充预取队列（同步方法，事件循环内调用无竞态）。"""
        if not self.enabled or self.executor is None:
            return
        while self._idx < len(self.posts) and len(self._futures) < self.window:
            post = self.posts[self._idx]
            self._idx += 1
            pid = post.get("post_id", "?")
            fut = self.executor.submit(analyze_images_for_post, post, self.media_base)
            self._futures[pid] = fut

    async def get(self, post: Dict) -> Dict[int, Dict]:
        """取当前帖子的图片分析结果；同时补满预取窗口。"""
        pid = post.get("post_id", "?")
        fut = self._futures.pop(pid, None)
        self._refill()  # 补位，保持窗口满
        if fut is not None:
            try:
                return await asyncio.wrap_future(fut)
            except Exception:
                return {}
        if not self.enabled:
            return {}
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                self.executor, analyze_images_for_post, post, self.media_base)
        except Exception:
            return {}


async def process_one(post: Dict, sem: asyncio.Semaphore, prefetcher: ImagePrefetcher,
                      model: str, url: str, timeout: float, auto_threshold: float,
                      keep_alive: str, stats: Dict, auto_path: Path, suggest_path: Path,
                      progress_path: Path, annotator_id: str, total: int, done: List[int]) -> None:
    """处理单条帖子：图片(预取) → 关键词 → Ollama 判定 → 写输出 + 进度检查点。"""
    pid = post.get("post_id", "?")
    async with sem:
        image_analyses = await prefetcher.get(post)

        text = post.get("text") or ""
        keyword_weights = compute_keyword_weights_for_post(text)

        # 在线程池中执行同步的 run_auto_judge（requests 网络 I/O 释放 GIL，
        # 配合信号量并发窗口 = Ollama 服务端序列批处理的在飞请求数）
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, run_auto_judge,
            post, image_analyses, keyword_weights,
            model, url, timeout, auto_threshold, keep_alive,
        )

        tier = result["tier"]
        stats["tiers"][tier] = stats["tiers"].get(tier, 0) + 1
        if result["fallback"]:
            stats["fallback_count"] += 1
        if result["error"]:
            stats["error_count"] += 1

        suggestion = result["suggestion"]
        label = None
        conf = None
        if suggestion is not None:
            label = suggestion.get("label", "?")
            conf = suggestion.get("confidence", 0.0)
            stats["labels"][label] = stats["labels"].get(label, 0) + 1
            if tier == "auto":
                record = result["record"] or {}
                record["annotator_id"] = annotator_id
                with auto_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"  🟢 [{done[0] + 1}/{total}] {pid} auto_accepted: {label} (conf={conf:.2f})")
            elif tier == "suggest":
                suggestion_record = {
                    "post_id": pid,
                    "annotator_id": "system",
                    "guide_version": "1.0",
                    "suggestion": suggestion,
                    "keyword_weights": keyword_weights,
                    "image_analyses": image_analyses,
                    "generated_at": datetime.now(CST).isoformat(),
                }
                with suggest_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(suggestion_record, ensure_ascii=False) + "\n")
                print(f"  🟡 [{done[0] + 1}/{total}] {pid} suggest: {label} (conf={conf:.2f})")
            else:
                print(f"  🔴 [{done[0] + 1}/{total}] {pid} manual: {label} (conf={conf:.2f})")
        else:
            print(f"  🔴 [{done[0] + 1}/{total}] {pid} manual: 无建议（纯人工）")

        # ── 进度检查点：任何结果（含 manual 无建议）都记录，支持断点续传 ──
        write_progress(progress_path, {
            "post_id": pid,
            "tier": tier,
            "label": label,
            "confidence": conf,
            "fallback": bool(result["fallback"]),
            "error": bool(result["error"]),
            "finished_at": datetime.now(CST).isoformat(),
        })
        done[0] += 1


async def run_batch_async(posts: List[Dict], media_base: Path,
                          num_parallel: int, image_workers: int, no_images: bool,
                          model: str, url: str, timeout: float, auto_threshold: float,
                          keep_alive: str, auto_path: Path, suggest_path: Path,
                          progress_path: Path, annotator_id: str,
                          initial_stats: Optional[Dict] = None,
                          done_start: int = 0) -> Dict:
    """异步流水线主流程，返回统计字典。

    Args:
        initial_stats: 断点续传时传入已重建的统计（含已处理部分）
        done_start: 断点续传时已处理的帖子数（用于进度计数）
    """
    stats: Dict[str, Any] = {
        "num_parallel": num_parallel,
        "image_workers": image_workers,
        "tiers": {"auto": 0, "suggest": 0, "manual": 0},
        "labels": {},
        "fallback_count": 0,
        "error_count": 0,
    }
    if initial_stats:
        for k in ("tiers", "labels", "fallback_count", "error_count"):
            if k in initial_stats:
                stats[k] = initial_stats[k]
    total = len(posts)
    done: List[int] = [done_start]
    sem = asyncio.Semaphore(num_parallel)

    img_exec = ThreadPoolExecutor(max_workers=image_workers) if not no_images else None
    prefetcher = ImagePrefetcher(
        posts, media_base, img_exec,
        window=max(num_parallel * 2, 4),
        enabled=not no_images,
    )
    # 预热预取窗口
    if img_exec is not None:
        prefetcher._refill()

    start = time.time()
    try:
        tasks = [asyncio.create_task(
            process_one(post, sem, prefetcher, model, url, timeout,
                        auto_threshold, keep_alive, stats, auto_path, suggest_path,
                        progress_path, annotator_id, total, done))
            for post in posts]
        await asyncio.gather(*tasks)
    finally:
        if img_exec is not None:
            img_exec.shutdown(wait=False, cancel_futures=False)

    stats["duration_sec"] = round(time.time() - start, 2)
    stats["session_processed"] = total
    stats["total_processed"] = done_start + total
    stats["throughput_posts_per_sec"] = round(total / stats["duration_sec"], 2) if stats["duration_sec"] else 0
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量预标注 —— 分置信度自动判断系统（Ollama + Qwen3.5 9B）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True,
                        help="输入帖子 JSONL 路径")
    parser.add_argument("--output-dir", "-o", default="data/annotations/preannotated",
                        help="输出目录（默认 data/annotations/preannotated）")
    parser.add_argument("--auto-threshold", type=float, default=DEFAULT_AUTO_THRESHOLD,
                        help=f"自动保存阈值（默认 {DEFAULT_AUTO_THRESHOLD}，范围 0.70–0.95）")
    parser.add_argument("--ollama-model", default=OLLAMA_DEFAULT_MODEL,
                        help=f"Ollama 模型名（默认 {OLLAMA_DEFAULT_MODEL}）")
    parser.add_argument("--ollama-url", default=OLLAMA_DEFAULT_URL,
                        help=f"Ollama 服务地址（默认 {OLLAMA_DEFAULT_URL}）")
    parser.add_argument("--timeout", type=float, default=OLLAMA_TIMEOUT,
                        help=f"单条推理超时秒数（默认 {OLLAMA_TIMEOUT}）")
    parser.add_argument("--keep-alive", default=None,
                        help=f"模型常驻时长（默认 {OLLAMA_KEEP_ALIVE}；-1=永久常驻）")
    parser.add_argument("--no-warmup", action="store_true",
                        help="跳过模型预热（默认先预热再批量，避免每条都冷启动加载模型）")
    parser.add_argument("--no-images", action="store_true",
                        help="跳过图片分析（无 vision 依赖或追求速度时使用）")
    parser.add_argument("--media-base", default="data",
                        help="图片本地存储根目录（默认 data）")
    parser.add_argument("--num-parallel", type=int, default=2,
                        help="客户端并发窗口（默认 2；建议 1-4，需与 ollama 的 "
                             "OLLAMA_NUM_PARALLEL 匹配；8GB 显存 + 9B 模型建议 2-3）")
    parser.add_argument("--image-workers", type=int, default=2,
                        help="图片分析线程池大小（默认 2；仅启用图片分析时有效）")
    parser.add_argument("--limit", "-n", type=int, default=0,
                        help="最多处理条数，0=全部（默认 0）")
    parser.add_argument("--annotator-id", default="system",
                        help="自动保存记录使用的标注人 ID（默认 system）")
    # ── 断点续传 ──
    parser.add_argument("--resume", default=None,
                        help="恢复指定批次（时间戳，如 20260802_192521；从进度检查点跳过已完成帖子）")
    parser.add_argument("--resume-latest", action="store_true",
                        help="自动恢复输出目录中最近一个批次（--resume 的快捷方式）")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        sys.exit(1)

    # ── 加载 ──
    print(f"📂 加载帖子: {input_path}")
    posts = load_jsonl(input_path)
    if args.limit > 0:
        posts = posts[:args.limit]
    total = len(posts)
    print(f"  共 {total} 条")

    # ── 输出文件（含断点续传）──
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定批次时间戳：--resume 指定 / --resume-latest 探测 / 全新
    resume_ts = args.resume
    if resume_ts is None and args.resume_latest:
        resume_ts = find_latest_batch_ts(output_dir)
        if resume_ts is None:
            print("⚠️ 未找到可恢复的批次（无 progress_*.jsonl），将作为全新批次启动")
    ts = resume_ts if resume_ts else datetime.now(CST).strftime("%Y%m%d_%H%M%S")

    auto_path = output_dir / f"auto_{ts}.jsonl"
    suggest_path = output_dir / f"suggest_{ts}.jsonl"
    stats_path = output_dir / f"stats_{ts}.json"
    progress_path = output_dir / f"progress_{ts}.jsonl"

    # ── 断点续传：加载检查点，跳过已完成帖子 ──
    done_start = 0
    initial_stats = None
    if resume_ts:
        processed, checkpoint_stats = load_checkpoint(output_dir, ts)
        if processed:
            before = len(posts)
            posts = [p for p in posts if p.get("post_id") not in processed]
            done_start = len(processed)
            initial_stats = checkpoint_stats
            print(f"  🔄 断点续传批次 {ts}: 已处理 {done_start} 条，剩余 {len(posts)} 条")
        else:
            print(f"  ⚠️ 批次 {ts} 无检查点记录，全新处理 {len(posts)} 条")

    print(f"  🟢 自动保存输出: {auto_path}")
    print(f"  🟡 建议输出:     {suggest_path}")
    print(f"  📊 统计输出:     {stats_path}")
    print(f"  📌 进度检查点:   {progress_path}")

    keep_alive = args.keep_alive or OLLAMA_KEEP_ALIVE

    # ── 统计 ──
    stats = {
        "started_at": datetime.now(CST).isoformat(),
        "total": total,
        "resumed_from": resume_ts,
        "auto_threshold": args.auto_threshold,
        "suggestion_lower_bound": SUGGESTION_LOWER_BOUND,
        "ollama_model": args.ollama_model,
        "ollama_url": args.ollama_url,
        "tiers": {"auto": 0, "suggest": 0, "manual": 0},
        "labels": {},
        "fallback_count": 0,
        "error_count": 0,
        "duration_sec": 0.0,
    }

    # ── 模型预热：先加载并驻留模型，避免每条帖子冷启动加载 6.6GB ──
    if not args.no_warmup:
        print(f"\n⏳ 预热模型 {args.ollama_model}（首次加载可能需要 1~2 分钟）...")
        ok = warm_up_model(
            model=args.ollama_model,
            url=args.ollama_url,
            timeout=OLLAMA_WARMUP_TIMEOUT,
            keep_alive=keep_alive,
        )
        if ok:
            print(f"  ✅ 模型已就绪（常驻 {keep_alive}，后续推理直接命中已加载模型）")
        else:
            print(f"  ⚠️ 预热失败，将降级为关键词回退")
        stats["warmup_ok"] = ok
        stats["keep_alive"] = keep_alive
    else:
        stats["warmup_ok"] = None
        stats["keep_alive"] = keep_alive

    media_base = Path(args.media_base)

    # ── 异步流水线：并发窗口 + 图片预取，配合 Ollama 序列批处理 ──
    print(f"  ⚡ 并发窗口: {args.num_parallel} | 图片线程: {args.image_workers if not args.no_images else 0} "
          f"| 图片分析: {'开' if not args.no_images else '关'}")
    stats.update(asyncio.run(run_batch_async(
        posts=posts,
        media_base=media_base,
        num_parallel=max(1, args.num_parallel),
        image_workers=max(1, args.image_workers),
        no_images=args.no_images,
        model=args.ollama_model,
        url=args.ollama_url,
        timeout=args.timeout,
        auto_threshold=args.auto_threshold,
        keep_alive=keep_alive,
        auto_path=auto_path,
        suggest_path=suggest_path,
        progress_path=progress_path,
        annotator_id=args.annotator_id,
        initial_stats=initial_stats,
        done_start=done_start,
    )))

    stats["duration_sec"] = stats.get("duration_sec", 0.0)
    stats["finished_at"] = datetime.now(CST).isoformat()

    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # ── 汇总 ──
    print("\n" + "═" * 56)
    print("📊 批量预标注完成")
    print("═" * 56)
    print(f"  批次:        {ts}" + ("（断点续传）" if resume_ts else ""))
    print(f"  数据总数:    {total}")
    print(f"  本轮处理:    {stats.get('session_processed', len(posts))} 条"
          f"（累计 {stats.get('total_processed', total)} 条）")
    print(f"  🟢 自动保存:  {stats['tiers'].get('auto', 0)}  ({auto_path.name})")
    print(f"  🟡 建议:      {stats['tiers'].get('suggest', 0)}  ({suggest_path.name})")
    print(f"  🔴 纯人工:    {stats['tiers'].get('manual', 0)}")
    print(f"  关键词回退:   {stats['fallback_count']}  (Ollama 失败自动降级)")
    print(f"  耗时:        {stats['duration_sec']:.1f}s")
    print(f"  吞吐:        {stats.get('throughput_posts_per_sec', 0):.2f} 条/秒"
          f"（并发窗口 {args.num_parallel}）")
    print(f"  统计报告:    {stats_path}")


if __name__ == "__main__":
    main()

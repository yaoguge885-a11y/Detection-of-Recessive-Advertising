#!/usr/bin/env python3
"""批量预标注脚本 —— 正式双标前先跑一轮全量自动判断，减少人工工作量。

管线（co-pilot-auto-judge-design v1.0）：
  1. 逐条加载帖子
  2. 计算 6 维关键词向量（本地免费，<0.1s）
  3. 可选：YOLO+OCR 图片分析（需要 vision 依赖，失败自动降级为纯文本）
  4. Qwen3.5 9B via Ollama 综合判定（本地，~5-15s/条）
  5. 三级分类：
       - 🟢 auto   (confidence >= --auto-threshold) → 自动保存标注记录
       - 🟡 suggest (0.55 <= confidence < threshold) → 输出建议，供人工确认
       - 🔴 manual  (confidence < 0.55)              → 不输出建议
  6. Ollama 不可用/超时/非 JSON → 关键词规则回退（见设计文档 4.4）

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
"""
from __future__ import annotations

import argparse
import json
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
    OLLAMA_WARMUP_TIMEOUT,
    DEFAULT_AUTO_THRESHOLD,
    SUGGESTION_LOWER_BOUND,
    classify_confidence,
    compute_keyword_weights_for_post,
    run_auto_judge,
    warm_up_model,
)

CST = timezone(timedelta(hours=8))


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
    """
    results: Dict[int, Dict] = {}
    try:
        from auto_image_annotate import load_yolo, load_ocr, analyze_image  # type: ignore
    except Exception:
        return results  # vision 依赖未安装，跳过图片分析

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
    try:
        yolo = load_yolo()
        ocr = load_ocr()
    except Exception:
        return results

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
    parser.add_argument("--limit", "-n", type=int, default=0,
                        help="最多处理条数，0=全部（默认 0）")
    parser.add_argument("--annotator-id", default="system",
                        help="自动保存记录使用的标注人 ID（默认 system）")
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

    # ── 输出文件 ──
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
    auto_path = output_dir / f"auto_{ts}.jsonl"
    suggest_path = output_dir / f"suggest_{ts}.jsonl"
    stats_path = output_dir / f"stats_{ts}.json"

    print(f"  🟢 自动保存输出: {auto_path}")
    print(f"  🟡 建议输出:     {suggest_path}")
    print(f"  📊 统计输出:     {stats_path}")

    keep_alive = args.keep_alive or OLLAMA_KEEP_ALIVE

    # ── 统计 ──
    stats = {
        "started_at": datetime.now(CST).isoformat(),
        "total": total,
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

    auto_records: List[Dict[str, Any]] = []
    suggest_records: List[Dict[str, Any]] = []
    media_base = Path(args.media_base)

    start = time.time()
    try:
        for i, post in enumerate(posts, 1):
            pid = post.get("post_id", "?")
            print(f"\n[{i}/{total}] {pid}")

            # 图片分析（可选）
            image_analyses: Dict[int, Dict] = {}
            if not args.no_images:
                image_analyses = analyze_images_for_post(post, media_base)
                if image_analyses:
                    ok = sum(1 for a in image_analyses.values() if "error" not in a)
                    print(f"  🖼 图片分析: {ok}/{len(image_analyses)} 成功")

            # 关键词向量（本地免费）
            text = post.get("text") or ""
            keyword_weights = compute_keyword_weights_for_post(text)

            # 自动判断管线
            result = run_auto_judge(
                post,
                image_analyses=image_analyses,
                keyword_weights=keyword_weights,
                model=args.ollama_model,
                url=args.ollama_url,
                timeout=args.timeout,
                auto_threshold=args.auto_threshold,
                keep_alive=keep_alive,
            )

            tier = result["tier"]
            stats["tiers"][tier] = stats["tiers"].get(tier, 0) + 1
            if result["fallback"]:
                stats["fallback_count"] += 1
            if result["error"]:
                stats["error_count"] += 1

            suggestion = result["suggestion"]
            if suggestion is None:
                print(f"  🔴 manual: 无建议（纯人工）")
                continue

            label = suggestion.get("label", "?")
            conf = suggestion.get("confidence", 0.0)
            stats["labels"][label] = stats["labels"].get(label, 0) + 1

            if tier == "auto":
                record = result["record"] or {}
                record["annotator_id"] = args.annotator_id
                auto_records.append(record)
                with auto_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"  🟢 auto_accepted: {label} (conf={conf:.2f}) → 已自动保存")
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
                suggest_records.append(suggestion_record)
                with suggest_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(suggestion_record, ensure_ascii=False) + "\n")
                print(f"  🟡 suggest: {label} (conf={conf:.2f}) → 等待人工确认")
            else:
                print(f"  🔴 manual: {label} (conf={conf:.2f}) 低于建议下限，纯人工")
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断，保存已处理结果...")

    stats["duration_sec"] = round(time.time() - start, 2)
    stats["finished_at"] = datetime.now(CST).isoformat()
    stats["auto_saved"] = len(auto_records)
    stats["suggested"] = len(suggest_records)

    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    # ── 汇总 ──
    print("\n" + "═" * 56)
    print("📊 批量预标注完成")
    print("═" * 56)
    print(f"  总数:        {total}")
    print(f"  🟢 自动保存:  {stats['tiers'].get('auto', 0)}  ({auto_path.name})")
    print(f"  🟡 建议:      {stats['tiers'].get('suggest', 0)}  ({suggest_path.name})")
    print(f"  🔴 纯人工:    {stats['tiers'].get('manual', 0)}")
    print(f"  关键词回退:   {stats['fallback_count']}  (Ollama 失败自动降级)")
    print(f"  耗时:        {stats['duration_sec']:.1f}s")
    print(f"  统计报告:    {stats_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
图片位置复核工具 —— 对 llm_needs_review=true 的记录进行三层检查。

三层机制：
  1. 规则层（自动）：纯文本模式检测 — 图片标记是否在合理位置
  2. 抽样层（半自动）：生成人工复核样本 — 展示 <图片N> 标记上下文
  3. 统计层（自动）：汇总问题分布，估算清洗质量

用法：
  # 全量规则检查 + 生成复核样本
  python scripts/data/annotation/review_image_placement.py \
    --input data/interim/candidates_v1_dedup.jsonl \
    --output data/reports/image_placement_review.json \
    --review-samples data/reports/review_samples.txt

  # 只看 needs_review 标记的记录
  python scripts/data/annotation/review_image_placement.py \
    --input data/interim/candidates_v1_dedup.jsonl \
    --needs-review-only
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CST = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════════════════════
# 第一层：规则检查
# ═══════════════════════════════════════════════════════════════

def check_image_marker_sanity(text: str, media_count: int) -> List[Dict]:
    """对含 <图片N> 标记的文本做规则层面的合理性检查。

    返回发现的问题列表，每个问题包含 {type, detail, position}。
    """
    issues = []

    if not text:
        return [{"type": "empty_text", "detail": "正文为空，无法验证图片位置"}]

    # 1. 统计文本中的 <图片N> 标记数量
    markers = re.findall(r'<图片(\d+)>', text)
    marker_indices = [int(m) for m in markers]
    marker_count = len(markers)

    # 2. 标记数 vs 实际图片数
    if marker_count == 0 and media_count > 0:
        issues.append({
            "type": "no_markers",
            "detail": f"正文中有 {media_count} 张图片但未找到 <图片N> 标记",
            "severity": "high",
        })
    elif marker_count < media_count:
        issues.append({
            "type": "missing_markers",
            "detail": f"正文中只有 {marker_count} 个标记，但实际有 {media_count} 张图片",
            "severity": "medium",
        })
    elif marker_count > media_count:
        issues.append({
            "type": "extra_markers",
            "detail": f"正文中有 {marker_count} 个标记，但实际只有 {media_count} 张图片",
            "severity": "medium",
        })

    # 3. 标记编号是否连续（1,2,3...而非 1,3,5）
    if marker_indices:
        expected = list(range(1, max(marker_indices) + 1))
        if marker_indices != sorted(marker_indices):
            issues.append({
                "type": "unordered_markers",
                "detail": f"图片标记顺序不递增: {marker_indices[:10]}",
                "severity": "medium",
            })
        missing_nums = set(expected) - set(marker_indices)
        if missing_nums:
            issues.append({
                "type": "skipped_numbers",
                "detail": f"跳过的图片编号: {sorted(missing_nums)[:10]}",
                "severity": "low",
            })

    # 4. 检查标记位置是否合理
    for match in re.finditer(r'<图片\d+>', text):
        pos = match.start()
        marker = match.group()

        # 4a. 是否在 URL 中间
        before = text[max(0, pos - 30):pos]
        after = text[match.end():match.end() + 30]
        if "http" in before[-10:] or "http" in after[:10]:
            issues.append({
                "type": "marker_in_url",
                "detail": f"{marker} 出现在 URL 附近: ...{before[-20:]} | {after[:20]}...",
                "severity": "high",
            })

        # 4b. 是否在英文单词/数字中间
        if pos > 0 and text[pos - 1].isalnum() and text[pos - 1].isascii():
            issues.append({
                "type": "marker_in_word",
                "detail": f"{marker} 出现在英文单词中间: ...{text[max(0,pos-10):pos+15]}...",
                "severity": "medium",
            })

        # 4c. 两个连续标记之间是否有实质内容
        next_match = re.search(r'<图片\d+>', text[match.end():])
        if next_match:
            between = text[match.end():match.end() + next_match.start()]
            stripped = between.strip()
            if len(stripped) < 5:
                issues.append({
                    "type": "markers_too_close",
                    "detail": f"{marker} 与下一个标记之间内容过短 ({len(stripped)} 字符)",
                    "severity": "low",
                })

    # 5. 图片密度检查（标记占总文本的比例）
    if len(text) > 0:
        marker_chars = sum(len(m.group()) for m in re.finditer(r'<图片\d+>', text))
        density = marker_chars / len(text)
        if density > 0.05 and marker_count > 10:
            issues.append({
                "type": "high_marker_density",
                "detail": f"标记密度 {density:.1%}，{marker_count} 个标记 / {len(text)} 字符",
                "severity": "low",
            })

    return issues


# ═══════════════════════════════════════════════════════════════
# 第二层：抽样生成人工复核材料
# ═══════════════════════════════════════════════════════════════

def generate_review_sample(
    record: Dict,
    media_base: Path,
    max_context_lines: int = 3,
) -> str:
    """为单条记录生成一份人工复核材料。

    展示：标题 + 含 <图片N> 标记的正文（截取上下文） + 每张图片的本地路径。
    """
    pid = record.get("post_id", "?")
    title = record.get("title") or "(无标题)"
    text = record.get("text", "")
    media = record.get("media", [])
    orig_id = record.get("_migration_meta", {}).get("original_post_id", "?")

    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"post_id: {pid}")
    lines.append(f"原始 ID: {orig_id}")
    lines.append(f"标题:    {title[:100]}")
    lines.append(f"图片数:  {len(media)}")
    lines.append(f"{'='*70}")

    # 提取每个 <图片N> 标记的上下文
    if text:
        lines.append(f"\n【正文（含图片标记）】")
        # 找所有标记位置
        marker_positions = [(m.start(), m.group()) for m in re.finditer(r'<图片\d+>', text)]

        if marker_positions:
            for i, (pos, marker) in enumerate(marker_positions):
                # 上下文：标记前后各 N 行
                before = text[max(0, pos - 200):pos].strip()
                after = text[pos + len(marker):pos + len(marker) + 200].strip()
                lines.append(f"\n--- {marker} (第 {i+1}/{len(marker_positions)} 个标记) ---")
                lines.append(f"  ...{before[-150:]}")
                lines.append(f"  >>> {marker} <<<")
                lines.append(f"  {after[:150]}...")
        else:
            lines.append(f"  (正文中无 <图片N> 标记)")
            # 展示前 500 字符
            lines.append(f"  {text[:500]}...")

    # 图片列表（本地路径）
    if media:
        lines.append(f"\n【图片列表】")
        for i, m in enumerate(media[:10]):  # 最多显示 10 张
            ref = m.get("ref", "?")
            media_type = m.get("type", "?")
            caption = m.get("ocr_text") or "(无标注)"
            # 检查文件是否存在
            full_path = media_base / ref if ref else None
            exists = "存在" if (full_path and full_path.exists()) else "缺失"
            lines.append(f"  图{i+1}: [{media_type}] {ref} ({exists})")
            if caption:
                lines.append(f"         标注: {caption[:80]}")
        if len(media) > 10:
            lines.append(f"  ... 还有 {len(media) - 10} 张图片")

    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 第三层：汇总统计
# ═══════════════════════════════════════════════════════════════

def analyze(records: List[Dict], media_base: Path, needs_review_only: bool = False):
    """主分析流程。"""
    target = [r for r in records if r.get("_migration_meta", {}).get("llm_needs_review")] \
        if needs_review_only else records

    print(f"分析范围: {'仅 llm_needs_review=true' if needs_review_only else '全部记录'}")
    print(f"记录数: {len(target)}")

    all_issues: List[Dict] = []
    issue_counts = Counter()
    severity_counts = Counter()
    records_with_issues = 0
    records_no_markers = 0

    for record in target:
        text = record.get("text", "")
        media_count = len(record.get("media", []))
        issues = check_image_marker_sanity(text, media_count)

        if issues:
            records_with_issues += 1
            for issue in issues:
                issue["post_id"] = record.get("post_id", "?")
                all_issues.append(issue)
                issue_counts[issue["type"]] += 1
                severity_counts[issue.get("severity", "low")] += 1

        # 统计无标记的记录
        markers = re.findall(r'<图片\d+>', text)
        if not markers and media_count > 0:
            records_no_markers += 1

    # 抽样生成复核材料
    samples = []
    sample_records = [r for r in target if re.findall(r'<图片\d+>', r.get("text", ""))]
    # 优先选有问题 + 有标记的记录
    problem_ids = {i["post_id"] for i in all_issues if i.get("severity") in ("high", "medium")}
    priority = [r for r in sample_records if r.get("post_id") in problem_ids]
    others = [r for r in sample_records if r.get("post_id") not in problem_ids]

    # 最多 30 条样本：优先问题记录
    sample_pool = (priority + others)[:30]
    for record in sample_pool:
        samples.append(generate_review_sample(record, media_base))

    # 报告
    report = {
        "reviewed_at": datetime.now(CST).isoformat(),
        "scope": "needs_review_only" if needs_review_only else "all",
        "total_records": len(target),
        "records_with_issues": records_with_issues,
        "records_no_markers": records_no_markers,
        "total_issues_found": len(all_issues),
        "issue_type_distribution": dict(issue_counts.most_common()),
        "severity_distribution": dict(severity_counts),
        "high_severity_issues": [
            {"post_id": i["post_id"], "type": i["type"], "detail": i["detail"]}
            for i in all_issues if i.get("severity") == "high"
        ][:20],
    }

    return report, samples


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="图片位置复核工具")
    parser.add_argument("--input", default="data/interim/candidates_v1_dedup.jsonl")
    parser.add_argument("--output", default="data/reports/image_placement_review.json")
    parser.add_argument("--review-samples", default="data/reports/review_samples.txt")
    parser.add_argument("--needs-review-only", action="store_true",
                        help="仅检查 llm_needs_review=true 的记录")
    parser.add_argument("--media-base", default="data",
                        help="媒体文件基础目录")
    args = parser.parse_args()

    proj = Path(__file__).resolve().parent.parent.parent.parent
    input_path = proj / args.input
    output_path = proj / args.output
    samples_path = proj / args.review_samples
    media_base = proj / args.media_base

    # 加载数据
    records = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    print(f"加载记录: {len(records)}")

    # 分析
    report, samples = analyze(records, media_base, args.needs_review_only)

    # 保存报告
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告: {output_path}")

    # 保存复核样本
    with samples_path.open("w", encoding="utf-8") as f:
        f.write("图片位置人工复核样本\n")
        f.write(f"生成时间: {datetime.now(CST).isoformat()}\n")
        f.write(f"样本数: {len(samples)}\n")
        f.write("查看方法: 打开原始微信文章，对照 <图片N> 标记位置逐一核对\n")
        f.write("=" * 70 + "\n\n")
        f.write("\n".join(samples))
    print(f"复核样本: {samples_path} ({len(samples)} 条)")

    # 打印摘要
    print(f"\n{'='*60}")
    print(f"📊 复核摘要")
    print(f"{'='*60}")
    print(f"  检查记录:    {report['total_records']}")
    print(f"  有问题记录:  {report['records_with_issues']}")
    print(f"  无标记记录:  {report['records_no_markers']} (有图片但无 <图片N>)")
    print(f"  发现问题:    {report['total_issues_found']}")
    print(f"")
    print(f"  问题类型分布:")
    for itype, count in report["issue_type_distribution"].items():
        print(f"    {itype}: {count}")
    print(f"")
    print(f"  严重程度:")
    for sev, count in report["severity_distribution"].items():
        print(f"    {sev}: {count}")
    if report["high_severity_issues"]:
        print(f"\n  ⚠️  高严重性问题 (前5条):")
        for i in report["high_severity_issues"][:5]:
            print(f"    [{i['post_id'][:25]}] {i['type']}: {i['detail'][:80]}")


if __name__ == "__main__":
    main()

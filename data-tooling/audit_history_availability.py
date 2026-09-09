#!/usr/bin/env python3
"""只读聚合审计：评估 anonymized_posts.jsonl 的历史可用性。

本脚本镜像 baseline/features.py 中 _prepare_history_rows 的 10 项校验逻辑，
仅输出聚合计数与数据指纹，绝不输出 post_id、blogger_id 或正文文本。

用法：
    python data-tooling/audit_history_availability.py
    python data-tooling/audit_history_availability.py --output audit_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# 与 baseline/features.py 保持一致的常量
# ---------------------------------------------------------------------------
MINIMUM_HISTORY = 3  # mirror baseline.features.MINIMUM_HISTORY
VALID_HISTORY_BUCKETS = ("3-5", "6-10", "11-20", "21+")
PRIVACY_THRESHOLD = 5  # 低于此值的计数显示为 "<5"


# ---------------------------------------------------------------------------
# 加载器 — 支持 JSONL 和 JSON 数组两种格式
# ---------------------------------------------------------------------------
def load_json_stream(path: Path) -> list[dict[str, Any]]:
    """加载 JSONL、空格分隔的 JSON 对象流，或 JSON 数组。"""
    text = path.read_text(encoding="utf-8-sig").lstrip()

    # 检测 JSON 数组格式
    if text.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise TypeError("JSON top-level must be an array")
        for i, value in enumerate(data):
            if not isinstance(value, dict):
                raise TypeError(f"record {i} must be an object")
        return data

    # JSONL / 空格分隔格式
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position == len(text):
            break
        value, position = decoder.raw_decode(text, position)
        if not isinstance(value, dict):
            raise TypeError(f"record {len(records)} must be an object")
        records.append(value)
    return records


# ---------------------------------------------------------------------------
# 时区感知检查 — 镜像 baseline.features._is_aware
# ---------------------------------------------------------------------------
def _is_aware(value: object) -> bool:
    """检查 datetime 是否带有时区信息。"""
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _parse_datetime(raw: str | None) -> datetime | None:
    """将 ISO-8601 字符串解析为带时区的 datetime；失败或为 None 时返回 None。"""
    if raw is None:
        return None
    try:
        # Python ≥3.11 使用 fromisoformat；更早版本则手动处理 'Z' 后缀
        normalized = raw.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if not _is_aware(dt):
            return None
        return dt
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 历史引用解析 — 镜像 baseline.features._prepare_history_rows
# ---------------------------------------------------------------------------
def resolve_history_for_post(
    target: dict[str, Any],
    posts_index: dict[str, dict[str, Any]],
    ref_to_pid: dict[str, str],
) -> dict[str, Any]:
    """对单条目标帖子的历史引用执行完整校验。

    posts_index 以完整 post_id 为键（如 post_abc123...）。
    ref_to_pid 提供短哈希 → 完整 post_id 的映射，
    因为 blogger_history_refs 中存储的可能是去掉 post_ 前缀的短哈希。

    返回一个字典，包含已解析的历史帖子列表和排除原因统计，
    但不返回任何帖子 ID、博主 ID 或正文文本。
    """
    target_id = target.get("post_id", "")
    target_blogger = target.get("blogger_id", "")
    target_time = _parse_datetime(target.get("published_at"))

    result: dict[str, Any] = {
        "valid_history_count": 0,
        "excluded_refs_missing": 0,
        "excluded_refs_blogger_mismatch": 0,
        "excluded_refs_timestamp_unavailable": 0,
        "excluded_refs_not_earlier": 0,
        "excluded_refs_invalid_format": 0,
        "excluded_refs_self_reference": 0,
    }

    if target_time is None:
        return result  # 目标帖无时间戳 → 有效历史数 = 0

    history_refs = target.get("blogger_history_refs")
    if not isinstance(history_refs, (list, tuple)):
        return result

    seen: set[str] = set()
    for history_id in history_refs:
        # 检查 1：引用 ID 必须为非空字符串
        if not isinstance(history_id, str) or not history_id.strip():
            result["excluded_refs_invalid_format"] += 1
            continue

        # 检查 2：无重复引用
        if history_id in seen:
            result["excluded_refs_invalid_format"] += 1
            continue
        seen.add(history_id)

        # 检查 3：禁止自引用
        if history_id == target_id:
            result["excluded_refs_self_reference"] += 1
            continue

        # 检查 4：引用必须存在于全局索引中
        # 先尝试完整 post_id 直接查找，再通过短哈希映射查找
        history = posts_index.get(history_id)
        if history is None:
            resolved_pid = ref_to_pid.get(history_id)
            if resolved_pid is not None:
                history = posts_index.get(resolved_pid)
        if history is None:
            result["excluded_refs_missing"] += 1
            continue

        # 检查 5：blogger_id 必须匹配
        if history.get("blogger_id") != target_blogger:
            result["excluded_refs_blogger_mismatch"] += 1
            continue

        # 检查 6-7：历史帖时间戳必须可用且带时区
        history_time = _parse_datetime(history.get("published_at"))
        if history_time is None:
            result["excluded_refs_timestamp_unavailable"] += 1
            continue

        # 检查 8：历史帖时间戳必须严格早于目标帖
        if history_time >= target_time:
            result["excluded_refs_not_earlier"] += 1
            continue

        # 全部通过 → 计为有效历史
        result["valid_history_count"] += 1

    return result


# ---------------------------------------------------------------------------
# 聚合引擎
# ---------------------------------------------------------------------------
def _hash_scheme_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    """分析 post_id 与 blogger_history_refs 的哈希方案是否一致。"""
    pid_hash_lengths: Counter[int] = Counter()
    ref_hash_lengths: Counter[int] = Counter()
    pid_has_prefix = 0
    pid_no_prefix = 0

    for r in records:
        pid = r.get("post_id", "")
        if isinstance(pid, str):
            if pid.startswith("post_"):
                pid_has_prefix += 1
                pid_hash_lengths[len(pid) - 5] += 1
            else:
                pid_no_prefix += 1
                pid_hash_lengths[len(pid)] += 1

        refs = r.get("blogger_history_refs")
        if isinstance(refs, (list, tuple)):
            for ref in refs:
                if isinstance(ref, str):
                    ref_hash_lengths[len(ref)] += 1

    dominant_pid_len = pid_hash_lengths.most_common(1)
    dominant_ref_len = ref_hash_lengths.most_common(1)

    return {
        "post_id_has_prefix": pid_has_prefix > 0,
        "dominant_pid_hash_length": dominant_pid_len[0][0] if dominant_pid_len else 0,
        "dominant_ref_hash_length": dominant_ref_len[0][0] if dominant_ref_len else 0,
        "hash_schemes_match": (
            dominant_pid_len[0][0] == dominant_ref_len[0][0]
            if dominant_pid_len and dominant_ref_len
            else False
        ),
        "pid_hash_lengths": dict(pid_hash_lengths),
        "ref_hash_lengths": dict(ref_hash_lengths),
    }


def audit_posts(records: list[dict[str, Any]]) -> dict[str, Any]:
    """对所有帖子执行只读聚合审计。"""

    # ---- 哈希方案分析 ----
    hash_analysis = _hash_scheme_analysis(records)

    # ---- 构建全局索引 ----
    posts_index: dict[str, dict[str, Any]] = {}
    # 短哈希 → 完整 post_id 映射（blogger_history_refs 可能去掉了 post_ 前缀）
    ref_to_pid: dict[str, str] = {}
    duplicate_ids = 0
    for record in records:
        pid = record.get("post_id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        if pid in posts_index:
            duplicate_ids += 1
        posts_index[pid] = record
        # 同时注册短哈希映射（去掉 post_ 前缀）
        if pid.startswith("post_"):
            short = pid[5:]
            if short and short not in ref_to_pid:
                ref_to_pid[short] = pid

    # ---- 聚合计数器 ----
    total_posts = len(records)

    # 各平台计数
    platform_total: Counter[str] = Counter()
    platform_published_available: Counter[str] = Counter()
    platform_has_history_refs: Counter[str] = Counter()
    platform_all_refs_resolvable: Counter[str] = Counter()
    platform_valid_history_ge3: Counter[str] = Counter()

    # 全局排除原因
    exclusion_target_ts_unavailable = 0
    exclusion_no_history_refs = 0
    exclusion_incomplete_refs = 0
    exclusion_history_insufficient = 0

    # 有效历史分桶
    valid_bucket_counts: Counter[str] = Counter()

    # 按匿名创作者（blogger_id）统计通过/不通过（仅计数值）
    creator_pass_count = 0
    creator_fail_count = 0
    creator_buckets: Counter[str] = Counter()  # 按有效历史数分桶的创作者数

    seen_creators: set[str] = set()

    # 按平台 × 有效历史分桶的二维交叉表
    platform_bucket: dict[str, Counter[str]] = defaultdict(Counter)

    for record in records:
        platform = record.get("platform", "unknown")
        platform_total[platform] += 1

        # 步骤 A：published_at 可用？
        target_time = _parse_datetime(record.get("published_at"))
        if target_time is None:
            exclusion_target_ts_unavailable += 1
            continue
        platform_published_available[platform] += 1

        # 步骤 B：blogger_history_refs 非空？
        history_refs = record.get("blogger_history_refs")
        if not isinstance(history_refs, (list, tuple)) or len(history_refs) == 0:
            exclusion_no_history_refs += 1
            continue
        platform_has_history_refs[platform] += 1

        # 步骤 C：全部引用可解析？
        resolved = resolve_history_for_post(record, posts_index, ref_to_pid)
        total_excluded = sum(
            v for k, v in resolved.items() if k.startswith("excluded_")
        )
        if total_excluded > 0:
            exclusion_incomplete_refs += 1
            continue
        platform_all_refs_resolvable[platform] += 1

        # 步骤 D：有效历史 ≥ 3？
        valid_count = resolved["valid_history_count"]
        if valid_count < MINIMUM_HISTORY:
            exclusion_history_insufficient += 1
            continue
        platform_valid_history_ge3[platform] += 1

        # ---- 通过帖子 ----
        # 有效历史分桶
        bucket = _bucket_for_count(valid_count)
        valid_bucket_counts[bucket] += 1
        platform_bucket[platform][bucket] += 1

        # 匿名创作者统计
        blogger = record.get("blogger_id", "")
        if blogger and blogger not in seen_creators:
            seen_creators.add(blogger)
            creator_pass_count += 1
            creator_buckets[bucket] += 1

    # 统计未通过的创作者（至少有一条帖子但无任何通过帖）
    all_creators: set[str] = set()
    for record in records:
        bid = record.get("blogger_id", "")
        if bid:
            all_creators.add(bid)
    creator_fail_count = len(all_creators - seen_creators)

    return {
        "total_posts": total_posts,
        "unique_post_ids": len(posts_index),
        "duplicate_ids": duplicate_ids,
        "unique_creators": len(all_creators),
        "hash_analysis": hash_analysis,
        "platform_total": dict(platform_total),
        "platform_published_available": dict(platform_published_available),
        "platform_has_history_refs": dict(platform_has_history_refs),
        "platform_all_refs_resolvable": dict(platform_all_refs_resolvable),
        "platform_valid_history_ge3": dict(platform_valid_history_ge3),
        "exclusion_target_ts_unavailable": exclusion_target_ts_unavailable,
        "exclusion_no_history_refs": exclusion_no_history_refs,
        "exclusion_incomplete_refs": exclusion_incomplete_refs,
        "exclusion_history_insufficient": exclusion_history_insufficient,
        "valid_bucket_counts": dict(valid_bucket_counts),
        "platform_bucket": {
            plat: dict(buckets) for plat, buckets in sorted(platform_bucket.items())
        },
        "creator_pass_count": creator_pass_count,
        "creator_fail_count": creator_fail_count,
        "creator_buckets": dict(creator_buckets),
    }


def _bucket_for_count(count: int) -> str:
    if count <= 5:
        return "3-5"
    if count <= 10:
        return "6-10"
    if count <= 20:
        return "11-20"
    return "21+"


# ---------------------------------------------------------------------------
# SHA-256 文件指纹
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    """返回文件的 SHA-256 十六进制摘要。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------
def _privacy_count(value: int) -> str:
    """应用最小阈值保护：小于 PRIVACY_THRESHOLD 显示为 '<N'。"""
    if value < PRIVACY_THRESHOLD:
        return f"<{PRIVACY_THRESHOLD}"
    return str(value)


def format_report(stats: dict[str, Any], fingerprint: str) -> str:
    """生成人类可读的聚合审计报告。"""
    lines: list[str] = []
    sep = "━" * 78

    lines.append(sep)
    lines.append("  历史可用性聚合审计报告")
    lines.append(f"  生成时间：{datetime.now(timezone.utc).isoformat()}")
    lines.append(f"  数据指纹：{fingerprint}")
    lines.append(sep)

    # ---- 总览 ----
    lines.append("")
    lines.append("【一、数据总览】")
    lines.append(f"  总帖子数：{stats['total_posts']}")
    lines.append(f"  唯一 post_id 数：{stats['unique_post_ids']}")
    lines.append(f"  重复 post_id 数：{stats['duplicate_ids']}")
    lines.append(f"  唯一创作者数：{_privacy_count(stats['unique_creators'])}")
    lines.append("")

    # ---- 哈希方案分析 ----
    ha = stats.get("hash_analysis", {})
    if ha:
        lines.append("【二、哈希方案一致性检查】")
        pid_len = ha.get("dominant_pid_hash_length", "?")
        ref_len = ha.get("dominant_ref_hash_length", "?")
        match = ha.get("hash_schemes_match", False)
        lines.append(f"  post_id 哈希长度：{pid_len} 位")
        lines.append(f"  blogger_history_refs 哈希长度：{ref_len} 位")
        if match:
            lines.append("  ✓ 哈希方案一致")
        else:
            lines.append("  ⚠ 哈希方案不一致 — 历史引用无法通过简单哈希匹配解析")
            if pid_len and ref_len and pid_len != ref_len:
                lines.append(
                    f"    post_id 使用 {pid_len} 位哈希, "
                    f"history_refs 使用 {ref_len} 位哈希。"
                )
            lines.append(
                "    可能原因：匿名化过程中使用了不同的哈希函数/盐值，"
            )
            lines.append(
                "    或 blogger_history_refs 指向外部数据集的 ID。"
            )
            lines.append(
                "    建议：对 history_refs 重新执行与 post_id 一致的哈希映射。"
            )
        lines.append("")

    # ---- 各平台流水线统计 ----
    lines.append("【三、各平台流水线统计】")
    header = (
        f"  {'平台':<28s} {'总数':>6s} {'时间可用':>8s} "
        f"{'有历史引用':>10s} {'引用全解析':>10s} {'有效历史≥3':>10s}"
    )
    lines.append(header)
    lines.append("  " + "-" * 74)

    platforms = sorted(
        set(stats["platform_total"])
        | set(stats["platform_published_available"])
        | set(stats["platform_valid_history_ge3"])
    )
    for plat in platforms:
        total = stats["platform_total"].get(plat, 0)
        pub = stats["platform_published_available"].get(plat, 0)
        has_hist = stats["platform_has_history_refs"].get(plat, 0)
        all_res = stats["platform_all_refs_resolvable"].get(plat, 0)
        valid = stats["platform_valid_history_ge3"].get(plat, 0)
        lines.append(
            f"  {plat:<28s} {total:>6d} {pub:>8d} "
            f"{has_hist:>10d} {all_res:>10d} {valid:>10d}"
        )
    lines.append("")

    # ---- 排除原因 ----
    lines.append("【四、排除原因统计】")
    excl_total = (
        stats["exclusion_target_ts_unavailable"]
        + stats["exclusion_no_history_refs"]
        + stats["exclusion_incomplete_refs"]
        + stats["exclusion_history_insufficient"]
    )
    lines.append(f"  排除帖子总数：{excl_total}")
    lines.append(
        f"    - published_at 不可用：{stats['exclusion_target_ts_unavailable']}"
    )
    lines.append(
        f"    - blogger_history_refs 为空：{stats['exclusion_no_history_refs']}"
    )
    lines.append(
        f"    - 历史引用未全部解析：{stats['exclusion_incomplete_refs']}"
    )
    lines.append(
        f"    - 有效历史不足 {MINIMUM_HISTORY} 条：{stats['exclusion_history_insufficient']}"
    )
    lines.append("")

    # ---- 有效历史分桶 ----
    lines.append("【五、有效历史分桶分布（仅通过帖）】")
    total_pass = sum(stats["valid_bucket_counts"].values())
    lines.append(f"  通过帖子总数（有效历史 ≥ {MINIMUM_HISTORY}）：{total_pass}")
    for bucket in VALID_HISTORY_BUCKETS:
        count = stats["valid_bucket_counts"].get(bucket, 0)
        pct = f"{count / total_pass * 100:.1f}%" if total_pass > 0 else "0%"
        lines.append(f"    {bucket} 条：{count} ({pct})")
    lines.append("")

    # ---- 平台 × 分桶交叉表 ----
    lines.append("【六、平台 × 有效历史分桶交叉表】")
    plat_bucket = stats.get("platform_bucket", {})
    all_bucket_labels = VALID_HISTORY_BUCKETS
    header2 = f"  {'平台':<28s}"
    for bl in all_bucket_labels:
        header2 += f" {bl:>8s}"
    lines.append(header2)
    lines.append("  " + "-" * (28 + 9 * len(all_bucket_labels)))
    for plat in sorted(plat_bucket):
        buckets = plat_bucket[plat]
        row = f"  {plat:<28s}"
        for bl in all_bucket_labels:
            row += f" {buckets.get(bl, 0):>8d}"
        lines.append(row)
    lines.append("")

    # ---- 创作者统计 ----
    lines.append("【七、匿名创作者统计（仅计数值，含阈值保护）】")
    lines.append(
        f"  至少有一帖通过的创作者数：{_privacy_count(stats['creator_pass_count'])}"
    )
    lines.append(
        f"  无任何通过帖的创作者数：{_privacy_count(stats['creator_fail_count'])}"
    )
    if stats["creator_pass_count"] > 0:
        lines.append("  通过创作者按最大有效历史分桶：")
        for bucket in VALID_HISTORY_BUCKETS:
            count = stats["creator_buckets"].get(bucket, 0)
            lines.append(f"    {bucket} 条：{_privacy_count(count)}")
    lines.append("")

    # ---- 结论 ----
    lines.append("【八、结论摘要】")
    pass_rate = (
        f"{total_pass / stats['total_posts'] * 100:.1f}%"
        if stats["total_posts"] > 0
        else "N/A"
    )
    lines.append(f"  最终可用帖子数（有效历史 ≥ {MINIMUM_HISTORY}）：{total_pass}")
    lines.append(f"  通过率：{pass_rate}")
    coverage = (
        f"{stats['creator_pass_count'] / stats['unique_creators'] * 100:.1f}%"
        if stats["unique_creators"] > 0
        else "N/A"
    )
    lines.append(f"  创作者覆盖率（至少一帖通过）：{coverage}")
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


def build_json_report(stats: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    """构建仅包含聚合数据的 JSON 报告。"""
    return {
        "report_type": "history_availability_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint_sha256": fingerprint,
        "minimum_history_threshold": MINIMUM_HISTORY,
        "privacy_threshold": PRIVACY_THRESHOLD,
        "hash_analysis": stats.get("hash_analysis", {}),
        "summary": {
            "total_posts": stats["total_posts"],
            "unique_post_ids": stats["unique_post_ids"],
            "duplicate_ids": stats["duplicate_ids"],
            "unique_creators": stats["unique_creators"],
            "total_pass": sum(stats["valid_bucket_counts"].values()),
        },
        "platform_pipeline": {
            plat: {
                "total": stats["platform_total"].get(plat, 0),
                "published_available": stats["platform_published_available"].get(
                    plat, 0
                ),
                "has_history_refs": stats["platform_has_history_refs"].get(plat, 0),
                "all_refs_resolvable": stats["platform_all_refs_resolvable"].get(
                    plat, 0
                ),
                "valid_history_ge3": stats["platform_valid_history_ge3"].get(plat, 0),
            }
            for plat in sorted(
                set(stats["platform_total"])
                | set(stats["platform_valid_history_ge3"])
            )
        },
        "exclusions": {
            "target_timestamp_unavailable": stats["exclusion_target_ts_unavailable"],
            "no_history_refs": stats["exclusion_no_history_refs"],
            "incomplete_refs": stats["exclusion_incomplete_refs"],
            "history_insufficient": stats["exclusion_history_insufficient"],
        },
        "valid_history_buckets": {
            bucket: stats["valid_bucket_counts"].get(bucket, 0)
            for bucket in VALID_HISTORY_BUCKETS
        },
        "platform_bucket_cross": stats.get("platform_bucket", {}),
        "creator_summary": {
            "pass_count": stats["creator_pass_count"],
            "fail_count": stats["creator_fail_count"],
            "buckets": {
                bucket: stats["creator_buckets"].get(bucket, 0)
                for bucket in VALID_HISTORY_BUCKETS
            },
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_history_availability.py",
        description="只读聚合审计：评估 anonymized_posts.jsonl 的历史可用性。",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="anonymized_posts.jsonl 路径（默认自动探测 data/sheets/anonymized_posts.jsonl）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="可选：将聚合 JSON 报告写入指定路径",
    )
    return parser


def _resolve_input_path(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"输入文件不存在：{explicit}")
        return explicit

    # 自动探测：从脚本所在目录向上查找 workspace 根目录
    script_dir = Path(__file__).resolve().parent
    workspace_root = script_dir.parent
    candidate = workspace_root / "data" / "sheets" / "anonymized_posts.jsonl"
    if candidate.is_file():
        return candidate

    raise FileNotFoundError(
        f"未找到 anonymized_posts.jsonl，请使用 --input 指定路径"
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        input_path = _resolve_input_path(args.input)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"读取输入文件：{input_path}")
    records = load_json_stream(input_path)
    print(f"已加载 {len(records)} 条记录")

    print("计算 SHA-256 指纹...")
    fingerprint = sha256_file(input_path)

    print("执行审计...")
    stats = audit_posts(records)

    report = format_report(stats, fingerprint)
    print()
    print(report)

    if args.output is not None:
        json_report = build_json_report(stats, fingerprint)
        args.output.write_text(
            json.dumps(json_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"JSON 报告已写入：{args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

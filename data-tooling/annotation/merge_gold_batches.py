#!/usr/bin/env python3
"""合并多个单标注者批次导出，生成 M1 Gold 候选池。

与 build_gold_dataset.py 的分工：
  - build_gold_dataset.py 处理「双人标注 + 仲裁」生成 κ / 正式 Gold；
  - 本脚本处理「单人分批标注」的合并，保留来源批次与标注方式分层，
    不声称产出的是独立盲标 Gold。

分层字段 `gold_tier`：
  - `blind_human`    无 AI 建议的纯人工标注（annotation_method=human）
  - `human_assisted` 看过模型建议后人工确认（annotation_method=human_assisted）

输出：
  gold_all.jsonl      全部去重记录，附 status / exclusion_reason
  gold_tri.jsonl      三元标签（明广/暗广/非广），不含采集失败
  gold_excluded.jsonl uncertain / out_of_scope / 采集失败
  report.json         分布、分层、排除原因统计

注意：输出含真实 post_id 与人工判断，默认不进入版本库。
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

TRI_LABELS = ("明广", "暗广", "非广")
CAPTURE_FAILURE_MARKERS = ("采集失败", "采集错误", "爬虫采集失败", "invalid_capture_failed")
# 采集壳页面：验证码页、仅"分享图片"、公众号壳
SHELL_PATTERNS = (
    "智能验证检测中",
    "由极验提供技术支持",
    "微信公众平台运营中心",
    "该内容已被发布者删除",
)


def load_export(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict) and "annotations" in payload:
        return payload
    raise ValueError(f"{path} 不是 workbench 导出格式（缺少 annotations）")


def latest_records(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """同一 post_id 取 revision 最大的记录。"""
    latest: Dict[str, Dict[str, Any]] = {}
    for record in payload.get("annotations") or []:
        if not isinstance(record, dict):
            continue
        post_id = record.get("post_id")
        if not post_id:
            continue
        current = latest.get(post_id)
        if current is None or int(record.get("revision") or 1) >= int(current.get("revision") or 1):
            latest[post_id] = record
    return latest


def load_pool_text(pool_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if pool_path is None:
        return {}
    pool: Dict[str, Dict[str, Any]] = {}
    with pool_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            post_id = item.get("post_id") or item.get("id")
            if post_id:
                pool[post_id] = item
    return pool


def strip_boilerplate(text: str) -> str:
    text = re.sub(r"<图片\d+>|查看大图|向左旋转|向右旋转|请先登录", " ", str(text or ""))
    text = re.sub(r"评论\s*\d+|赞与转发|视频播放量\s*\d+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_capture_failure(record: Dict[str, Any], pool_item: Dict[str, Any]) -> Optional[str]:
    """返回确凿的采集失败原因；疑似但标注者已判断的情况不在此列。"""
    notes = str(record.get("notes") or "")
    if any(marker in notes for marker in CAPTURE_FAILURE_MARKERS):
        return "notes_marked_capture_failure"

    body = str(pool_item.get("text") or pool_item.get("content") or "")
    if any(pattern in body for pattern in SHELL_PATTERNS):
        return "shell_page_captcha"
    return None


def detect_thin_content(record: Dict[str, Any], pool_item: Dict[str, Any]) -> bool:
    """正文过短且无本地媒体：证据薄弱，但标注者已给出判断，只标记不排除。

    这类典型是 B站「分享图片」动态或纯图片帖，图片未采集，标注者按作者与语境判了非广。
    是否作废属于方法学决定，交人工裁定，脚本不得替标注者推翻标签。
    """
    title = str(pool_item.get("title") or "")
    body = str(pool_item.get("text") or pool_item.get("content") or "")
    cleaned = strip_boilerplate(body)
    if len(cleaned) >= 40:
        return False
    has_media = bool(pool_item.get("media"))
    return not has_media or title.strip().lower() in ("", "none")


def classify(record: Dict[str, Any], capture_reason: Optional[str], thin: bool) -> Dict[str, Any]:
    label = record.get("label")
    confidence = float(record.get("confidence") or 0.0)
    if capture_reason:
        status, reason = "excluded", "invalid_capture_failed"
    elif label == "uncertain":
        status, reason = "excluded", "uncertain"
    elif label == "out_of_scope":
        status, reason = "excluded", "out_of_scope"
    elif label in TRI_LABELS:
        status, reason = "gold_candidate", ""
    else:
        status, reason = "excluded", "unknown_label"
    review_flags: List[str] = []
    if status == "gold_candidate" and confidence < 0.6:
        review_flags.append("low_confidence")
    if status == "gold_candidate" and thin:
        review_flags.append("thin_content_no_media")
    return {
        "status": status,
        "exclusion_reason": reason,
        "capture_failure_reason": capture_reason or "",
        "thin_content": thin,
        "review_flags": review_flags,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="合并单标注者批次导出为 Gold 候选池")
    parser.add_argument("--input", action="append", required=True, metavar="TIER=PATH",
                        help="批次导出文件，格式 tier=path，可重复")
    parser.add_argument("--pool", help="候选池 JSONL，用于检测采集失败")
    parser.add_argument("--out-dir", required=True, help="输出目录")
    parser.add_argument("--allow-tier", action="append", default=None,
                        help="允许进入 Gold 候选的分层，默认全部")
    args = parser.parse_args(list(argv) if argv is not None else None)

    pool = load_pool_text(Path(args.pool) if args.pool else None)
    allowed_tiers = set(args.allow_tier) if args.allow_tier else None

    merged: Dict[str, Dict[str, Any]] = {}
    batch_stats: Dict[str, Dict[str, Any]] = {}
    conflicts: List[Dict[str, Any]] = []

    for spec in args.input:
        if "=" not in spec:
            parser.error(f"--input 需要 tier=path 格式：{spec}")
        tier, raw_path = spec.split("=", 1)
        path = Path(raw_path)
        payload = load_export(path)
        records = latest_records(payload)
        export_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        batch_id = payload.get("batch_id", path.stem)
        stats = {
            "batch_id": batch_id,
            "tier": tier,
            "path": str(path),
            "sha256": export_sha,
            "annotator_id": payload.get("annotator_id"),
            "guide_version": payload.get("guide_version"),
            "guide_sha256": payload.get("guide_sha256"),
            "formal_gold_allowed": payload.get("formal_gold_allowed"),
            "record_count": len(payload.get("annotations") or []),
            "unique_post_count": len(records),
        }
        labels = collections.Counter(rec.get("label") for rec in records.values())
        stats["labels"] = dict(labels)
        batch_stats[f"{batch_id}:{tier}"] = stats

        for post_id, record in records.items():
            pool_item = pool.get(post_id, {})
            capture_reason = detect_capture_failure(record, pool_item)
            thin = detect_thin_content(record, pool_item)
            verdict = classify(record, capture_reason, thin)
            if allowed_tiers is not None and tier not in allowed_tiers and verdict["status"] == "gold_candidate":
                verdict["status"] = "excluded"
                verdict["exclusion_reason"] = f"tier_not_allowed:{tier}"
            merged_record = {
                "post_id": post_id,
                "label": record.get("label"),
                "confidence": float(record.get("confidence") or 0.0),
                "evidence_codes": record.get("evidence_codes") or [],
                "evidence": record.get("evidence") or [],
                "notes": record.get("notes"),
                "uncertain_reason": record.get("uncertain_reason"),
                "annotator_id": record.get("annotator_id"),
                "annotation_method": record.get("annotation_method"),
                "saw_model_advice": record.get("saw_model_advice"),
                "model_advice_label": record.get("model_advice_label"),
                "model_advice_status": record.get("model_advice_status"),
                "revision": record.get("revision"),
                "annotated_at": record.get("annotated_at"),
                "updated_at": record.get("updated_at"),
                "guide_version": record.get("guide_version"),
                "guide_sha256": record.get("guide_sha256"),
                "batch_id": batch_id,
                "gold_tier": tier,
                "dataset_id": record.get("dataset_id"),
                "manifest_role": record.get("manifest_role"),
                "formal_gold_allowed": record.get("formal_gold_allowed"),
                **verdict,
            }
            existing = merged.get(post_id)
            if existing is not None:
                conflicts.append({
                    "post_id": post_id,
                    "kept": f"{existing['batch_id']}:{existing['gold_tier']}",
                    "dropped": f"{batch_id}:{tier}",
                })
                continue
            merged[post_id] = merged_record

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    order = {"gold_candidate": 0, "excluded": 1}
    all_records = sorted(
        merged.values(),
        key=lambda rec: (order.get(rec["status"], 9), rec.get("exclusion_reason", ""), rec["post_id"]),
    )
    tri_records = [rec for rec in all_records if rec["status"] == "gold_candidate"]
    excluded_records = [rec for rec in all_records if rec["status"] == "excluded"]

    def write_jsonl(name: str, records: List[Dict[str, Any]]) -> str:
        path = out_dir / name
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    hashes = {
        "gold_all.jsonl": write_jsonl("gold_all.jsonl", all_records),
        "gold_tri.jsonl": write_jsonl("gold_tri.jsonl", tri_records),
        "gold_excluded.jsonl": write_jsonl("gold_excluded.jsonl", excluded_records),
    }

    def distribution(records: List[Dict[str, Any]], key: str) -> Dict[str, int]:
        return dict(collections.Counter(str(rec.get(key)) for rec in records))

    report = {
        "schema_version": "m1_gold_merge_v1",
        "gold_count": len(tri_records),
        "batches": batch_stats,
        "totals": {
            "input_unique": len(merged),
            "gold_candidate": len(tri_records),
            "excluded": len(excluded_records),
            "duplicate_conflicts": len(conflicts),
        },
        "gold_distribution": distribution(tri_records, "label"),
        "gold_by_tier": {
            tier: distribution([rec for rec in tri_records if rec["gold_tier"] == tier], "label")
            for tier in sorted({rec["gold_tier"] for rec in tri_records})
        },
        "gold_by_batch": {
            batch: distribution([rec for rec in tri_records if rec["batch_id"] == batch], "label")
            for batch in sorted({rec["batch_id"] for rec in tri_records})
        },
        "exclusion_reasons": distribution(excluded_records, "exclusion_reason"),
        "capture_failure_reasons": distribution(
            [rec for rec in excluded_records if rec["exclusion_reason"] == "invalid_capture_failed"],
            "capture_failure_reason",
        ),
        "review_queue": {
            "low_confidence": sum(1 for rec in tri_records if "low_confidence" in rec["review_flags"]),
            "low_confidence_post_ids": [rec["post_id"] for rec in tri_records if "low_confidence" in rec["review_flags"]],
            "thin_content_no_media": sum(1 for rec in tri_records if "thin_content_no_media" in rec["review_flags"]),
            "thin_content_post_ids": [rec["post_id"] for rec in tri_records if "thin_content_no_media" in rec["review_flags"]],
        },
        "conflicts": conflicts,
        "outputs": hashes,
        "note": (
            "gold_tier 区分盲标与 AI 辅助人工确认，两者不可等同："
            "blind_human 可用于一致性统计，human_assisted 仅进入 Gold 候选池。"
        ),
    }
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "out_dir": str(out_dir),
        "input_unique": len(merged),
        "gold_candidate": len(tri_records),
        "excluded": len(excluded_records),
        "gold_distribution": report["gold_distribution"],
        "gold_by_tier": report["gold_by_tier"],
        "exclusion_reasons": report["exclusion_reasons"],
        "low_confidence": report["review_queue"]["low_confidence"],
        "duplicate_conflicts": len(conflicts),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

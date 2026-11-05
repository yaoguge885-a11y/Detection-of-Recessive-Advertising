#!/usr/bin/env python3
"""标注前置采集：爬虫回填元数据。

契约：
  - 只写入爬虫负责的字段，绝不覆盖 intake.* 中的人工观察结果；
  - 回填失败不使样本作废，只把 backfill.status 置 failed 并重算完整性；
  - 重算后的 collection_complete 反映「人是否看全」与「爬虫是否补全」两个事实。

当前实现不绑定具体平台爬虫；传入 --fetch-impl 可注入自定义抓取函数，
默认用 --offline 模式仅重算完整性，便于先验证流程再接入真实抓取。
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BACKFILL_OWNED_FIELDS = (
    "title",
    "text",
    "media",
    "comments",
    "blogger_id",
    "published_at",
    "blogger_history_refs",
)


def derive_collection_complete(viewed_media: str, backfill_status: str) -> str:
    """采集完整性由人工观察与回填结果共同推导。"""
    if viewed_media == "full" and backfill_status == "ok":
        return "complete"
    if viewed_media in ("full", "partial"):
        return "incomplete"
    return "unknown"


def _intake_field(record: Dict[str, Any], key: str, default: Any = None) -> Any:
    intake = record.get("intake")
    if isinstance(intake, dict) and key in intake:
        return intake[key]
    return default


def apply_backfill(
    record: Dict[str, Any],
    fetched: Optional[Dict[str, Any]],
    *,
    error: Optional[str] = None,
    now: str,
) -> Dict[str, Any]:
    """把抓取结果写入 record，保留 intake。

    fetched 为 None 表示抓取失败或未尝试，此时只记状态，不改内容字段。
    """
    updated = dict(record)
    updated["intake"] = dict(record.get("intake") or {})

    if fetched is None:
        filled: List[str] = []
        status = "failed" if error else "pending"
    else:
        filled = []
        for field in BACKFILL_OWNED_FIELDS:
            if field not in fetched:
                continue
            value = fetched[field]
            if value in (None, "", [], {}):
                continue
            updated[field] = value
            filled.append(field)
        if not filled:
            status = "failed"
            error = error or "抓取结果为空"
        elif len(filled) == len(BACKFILL_OWNED_FIELDS):
            status = "ok"
        else:
            status = "partial"

    updated["backfill"] = {
        "status": status,
        "attempted_at": now,
        "error": error,
        "fields_filled": sorted(filled),
    }
    updated["collection_complete"] = derive_collection_complete(
        str(_intake_field(record, "viewed_media", "none")), status
    )
    disclosure = _intake_field(record, "disclosure_status")
    if disclosure:
        updated["disclosure_status"] = disclosure
    return updated


def load_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno} JSON 解析失败：{exc}") from exc
    return records


def resolve_fetcher(spec: str) -> Callable[[str], Dict[str, Any]]:
    """把 "module:function" 解析成抓取函数。"""
    if ":" not in spec:
        raise SystemExit("--fetch-impl 需要 module:function 格式")
    module_name, func_name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name, None)
    if not callable(func):
        raise SystemExit(f"{spec} 不可调用")
    return func


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="回填 intake 记录的爬虫字段")
    parser.add_argument("--intake", required=True, help="intake JSONL 输入")
    parser.add_argument("--out", required=True, help="回填后 JSONL 输出")
    parser.add_argument(
        "--fetch-impl",
        default="",
        help="抓取函数 module:function，接收 URL 返回字段 dict；留空则只重算完整性",
    )
    parser.add_argument(
        "--now",
        default="",
        help="固定回填时间戳（便于测试复现）",
    )
    args = parser.parse_args(argv)

    from datetime import datetime, timedelta, timezone

    now = args.now or datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    records = load_records(Path(args.intake))
    fetcher = resolve_fetcher(args.fetch_impl) if args.fetch_impl else None

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    counts: Dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            url = str(_intake_field(record, "source_url", "") or "")
            fetched: Optional[Dict[str, Any]] = None
            error: Optional[str] = None
            if fetcher is not None and url:
                try:
                    fetched = fetcher(url)
                except Exception as exc:  # 抓取异常不使样本作废
                    error = f"{type(exc).__name__}: {exc}"
            updated = apply_backfill(record, fetched, error=error, now=now)
            counts[updated["backfill"]["status"]] = counts.get(updated["backfill"]["status"], 0) + 1
            handle.write(json.dumps(updated, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"输入 {len(records)} 条 → {out_path}")
    print(f"回填状态: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

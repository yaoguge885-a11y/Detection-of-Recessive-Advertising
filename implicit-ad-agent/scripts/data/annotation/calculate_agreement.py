#!/usr/bin/env python3
"""计算两名标注者之间的 Cohen's κ 及 95% bootstrap 置信区间。

v1.1 改进：
  - κ 只基于两人原始三元标签（明广/暗广/非广）
  - uncertain/out_of_scope 单独统计，不计入 κ
  - 输出完整分歧分析
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

LABELS = ["明广", "暗广", "非广"]
LABEL_INDEX = {label: idx for idx, label in enumerate(LABELS)}
SPECIAL_LABELS = {"uncertain", "out_of_scope"}


def load_annotations(path: Path) -> Dict[str, Dict[str, Any]]:
    """从 JSONL 加载标注，保留判断独立人工标注所需的元数据。

    兼容两种格式：
      - 标准 JSONL（每行一个完整 JSON 对象）
      - 美化打印拼接的 JSON（每个对象跨多行）
    """
    data: Dict[str, Dict[str, Any]] = {}
    raw_text = path.read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    idx = 0
    content_len = len(raw_text)
    while idx < content_len:
        while idx < content_len and raw_text[idx] in " \t\n\r":
            idx += 1
        if idx >= content_len:
            break
        try:
            obj, end = decoder.raw_decode(raw_text, idx)
            if isinstance(obj, dict) and "post_id" in obj and "label" in obj:
                data[str(obj["post_id"])] = dict(obj)
            idx = end
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(
                f"failed to decode annotation JSON at position {idx}: {exc.msg}",
                exc.doc,
                exc.pos,
            ) from exc
    return data


def _label(record: Mapping[str, Any]) -> str:
    return str(record.get("label", ""))


def _pair_ineligibility_reason(
    record_a: Mapping[str, Any],
    record_b: Mapping[str, Any],
) -> Optional[str]:
    methods = (record_a.get("annotation_method"), record_b.get("annotation_method"))
    raw_annotators = (record_a.get("annotator_id"), record_b.get("annotator_id"))
    annotators = tuple(
        annotator.strip() if isinstance(annotator, str) else ""
        for annotator in raw_annotators
    )
    if "auto_accepted" in methods or any(
        annotator.casefold() == "system" for annotator in annotators
    ):
        return "automated_annotation"
    if any(method != "human" for method in methods):
        return "non_human_method"
    if any(not annotator for annotator in annotators):
        return "missing_annotator_id"
    if annotators[0] == annotators[1]:
        return "same_annotator"
    return None


def _cohen_kappa_from_arrays(a: List[int], b: List[int]) -> float:
    """计算 Cohen's κ。"""
    n = len(a)
    if n == 0:
        return 0.0
    conf = Counter(zip(a, b))
    p0 = sum(conf[(i, i)] for i in range(len(LABELS))) / n
    pa = [sum(conf[(i, j)] for j in range(len(LABELS))) / n for i in range(len(LABELS))]
    pb = [sum(conf[(i, j)] for i in range(len(LABELS))) / n for j in range(len(LABELS))]
    pe = sum(pa[i] * pb[i] for i in range(len(LABELS)))
    if pe == 1.0:
        return 1.0
    return (p0 - pe) / (1 - pe)


def cohen_kappa_ci(a: List[int], b: List[int], n_bootstrap: int = 2000) -> Tuple[float, float, float]:
    """返回 (kappa, lower_95, upper_95)。"""
    kappa = _cohen_kappa_from_arrays(a, b)
    n = len(a)
    if n == 0:
        return kappa, kappa, kappa
    pairs = list(zip(a, b))
    bootstraps = []
    rng = random.Random(42)
    for _ in range(n_bootstrap):
        sample = [pairs[rng.randint(0, n - 1)] for _ in range(n)]
        sa, sb = zip(*sample)
        bootstraps.append(_cohen_kappa_from_arrays(list(sa), list(sb)))
    bootstraps.sort()
    lower = bootstraps[int(0.025 * n_bootstrap)]
    upper = bootstraps[int(0.975 * n_bootstrap)]
    return kappa, lower, upper


def build_confusion_matrix(a: List[int], b: List[int]) -> List[List[int]]:
    matrix = [[0] * len(LABELS) for _ in LABELS]
    for i, j in zip(a, b):
        matrix[i][j] += 1
    return matrix


def analyze_disagreements(
    a_labels: List[str], b_labels: List[str], common_ids: List[str]
) -> Dict:
    """分析分歧集中的模式。"""
    disagreements = []
    for pid, la, lb in zip(common_ids, a_labels, b_labels):
        if la != lb:
            disagreements.append({
                "post_id": pid,
                "label_a": la,
                "label_b": lb,
            })

    # 分歧类型分布
    type_counts = defaultdict(int)
    for d in disagreements:
        pair = tuple(sorted([d["label_a"], d["label_b"]]))
        type_counts[str(pair)] += 1

    return {
        "total_disagreements": len(disagreements),
        "disagreement_types": dict(type_counts),
        "disagreement_samples": disagreements[:20],  # 前 20 条
    }


def calculate_agreement(
    a: Mapping[str, Mapping[str, Any]],
    b: Mapping[str, Mapping[str, Any]],
    *,
    formal_second_round: bool = False,
) -> Dict[str, Any]:
    """Return an aggregate agreement report without record identifiers."""
    common_ids = sorted(set(a) & set(b))

    ineligible_reasons = {
        post_id: reason
        for post_id in common_ids
        if (reason := _pair_ineligibility_reason(a[post_id], b[post_id]))
    }

    valid_ids = [
        post_id
        for post_id in common_ids
        if post_id not in ineligible_reasons
        and _label(a[post_id]) in LABEL_INDEX
        and _label(b[post_id]) in LABEL_INDEX
    ]
    excluded_ids = [post_id for post_id in common_ids if post_id not in valid_ids]
    labels_a = [LABEL_INDEX[_label(a[pid])] for pid in valid_ids]
    labels_b = [LABEL_INDEX[_label(b[pid])] for pid in valid_ids]
    if valid_ids:
        kappa, ci_low, ci_high = cohen_kappa_ci(labels_a, labels_b)
    else:
        kappa = ci_low = ci_high = None
    matrix = build_confusion_matrix(labels_a, labels_b)
    raw_agreement = (
        sum(1 for i, j in zip(labels_a, labels_b) if i == j) / len(valid_ids)
        if valid_ids
        else None
    )
    per_class: Dict[str, Dict[str, Any]] = {}
    for i, label in enumerate(LABELS):
        total_a = sum(matrix[i])
        agreed = matrix[i][i]
        per_class[label] = {
            "agreed": agreed,
            "annotator_a_total": total_a,
            "rate": agreed / total_a if total_a else None,
        }

    excluded_label_counts: Counter[str] = Counter()
    for post_id in excluded_ids:
        if post_id in ineligible_reasons:
            continue
        label_a = _label(a[post_id])
        label_b = _label(b[post_id])
        if label_a not in LABEL_INDEX:
            excluded_label_counts[f"a:{label_a}"] += 1
        if label_b not in LABEL_INDEX:
            excluded_label_counts[f"b:{label_b}"] += 1

    requested_formal = bool(formal_second_round)

    return {
        "common_pair_count": len(common_ids),
        "valid_pair_count": len(valid_ids),
        "excluded_pair_count": len(excluded_ids),
        "ineligible_pair_count": len(ineligible_reasons),
        "excluded_reason_counts": dict(
            sorted(Counter(ineligible_reasons.values()).items())
        ),
        "excluded_label_counts": dict(sorted(excluded_label_counts.items())),
        "kappa": kappa,
        "kappa_ci_95": {"lower": ci_low, "upper": ci_high},
        "raw_agreement": raw_agreement,
        "labels": LABELS,
        "confusion_matrix": matrix,
        "per_class_agreement": per_class,
        "formal_second_round_requested": requested_formal,
        "formal_second_round": requested_formal and not ineligible_reasons,
    }


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="计算双人标注 Cohen's kappa")
    parser.add_argument("annotator_a")
    parser.add_argument("annotator_b")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--formal-second-round",
        action="store_true",
        help="仅在本次输入确为第二轮盲标时使用",
    )
    args = parser.parse_args(argv)

    report = calculate_agreement(
        load_annotations(Path(args.annotator_a)),
        load_annotations(Path(args.annotator_b)),
        formal_second_round=args.formal_second_round,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

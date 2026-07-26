#!/usr/bin/env python3
"""按 blogger/creator 分组划分 train/dev/test，含 content_group 约束防泄漏。

v1.1 改进：
  - 以 blogger_id 为最小分组单位
  - 同一 content_group_id 的帖子强制分配到同一划分，防止跨平台转载泄漏
  - 输出划分报告

用法：
  python scripts/data/split_by_blogger.py gold_v1.jsonl train_ids.txt dev_ids.txt test_ids.txt
  python scripts/data/split_by_blogger.py gold_v1.jsonl train_ids.txt dev_ids.txt test_ids.txt --report data/reports/split_report.json
"""
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def load_jsonl(path: Path) -> Iterable[Dict]:
    """加载 JSONL 文件，兼容标准 JSONL 和美化打印拼接格式。"""
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
            yield obj
            idx = end
        except json.JSONDecodeError:
            next_brace = raw_text.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace


def write_ids(post_ids: List[str], path: Path) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for post_id in post_ids:
            stream.write(post_id + "\n")


def build_split_groups(records: List[Dict]) -> Dict[str, List[str]]:
    """Build creator/content-group connected components for leakage-safe splits."""
    parent: Dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        if parent[node] != node:
            parent[node] = find(parent[node])
        return parent[node]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for record in records:
        post_id = str(record.get("post_id", ""))
        if not post_id:
            continue
        creator_node = f"creator:{_creator_key(record, post_id)}"
        find(creator_node)
        content_group = record.get("content_group_id")
        if content_group:
            union(creator_node, f"content:{content_group}")

    groups: Dict[str, List[str]] = defaultdict(list)
    for record in records:
        post_id = str(record.get("post_id", ""))
        if not post_id:
            continue
        creator_node = f"creator:{_creator_key(record, post_id)}"
        groups[find(creator_node)].append(post_id)

    return {
        group_key: sorted(post_ids)
        for group_key, post_ids in sorted(groups.items())
    }


def _creator_key(record: Dict, post_id: str) -> str:
    creator = (
        record.get("blogger_id")
        or record.get("creator_id_hash")
        or record.get("creator_id")
    )
    return str(creator) if creator else f"missing:{post_id}"


def validate_split_leakage(
    records: List[Dict],
    assignments: Dict[str, List[str]],
) -> Dict[str, int]:
    """Count post, creator, and near-duplicate groups spanning split names."""
    post_splits: Dict[str, set] = defaultdict(set)
    for split_name, post_ids in assignments.items():
        for post_id in post_ids:
            post_splits[str(post_id)].add(split_name)

    creator_splits: Dict[str, set] = defaultdict(set)
    content_group_splits: Dict[str, set] = defaultdict(set)
    for record in records:
        post_id = str(record.get("post_id", ""))
        for split_name in post_splits.get(post_id, set()):
            creator_splits[_creator_key(record, post_id)].add(split_name)
            content_group = record.get("content_group_id")
            if content_group:
                content_group_splits[str(content_group)].add(split_name)

    post_leakage = sum(len(splits) > 1 for splits in post_splits.values())
    creator_leakage = sum(
        len(splits) > 1 for splits in creator_splits.values()
    )
    content_group_leakage = sum(
        len(splits) > 1 for splits in content_group_splits.values()
    )
    return {
        "post_leakage_count": post_leakage,
        "creator_leakage_count": creator_leakage,
        "content_group_leakage_count": content_group_leakage,
        "near_duplicate_leakage_count": content_group_leakage,
    }


def split_groups(
    groups: Dict[str, List[str]],
    ratios: Tuple[float, float, float] = (0.7, 0.15, 0.15),
    seed: int = 42,
) -> Tuple[Dict[str, List[str]], Dict]:
    """按比例划分组到 train/dev/test。
    
    使用贪心算法：每次将当前最小的划分分配新组。
    """
    random.seed(seed)
    target_train, target_dev, target_test = ratios

    assignments = {"train": [], "dev": [], "test": []}
    group_items = list(groups.items())
    random.shuffle(group_items)

    for group_key, post_ids in group_items:
        # 选择当前占比最小的划分
        current = {key: len(ids) for key, ids in assignments.items()}
        target = {"train": target_train, "dev": target_dev, "test": target_test}
        
        # 计算当前偏差
        total = sum(current.values()) + len(post_ids)
        if total == 0:
            to_assign = "train"
        else:
            deviations = {
                key: abs(
                    (current[key] + len(post_ids)) / max(total, 1)
                    - target[key]
                )
                for key in assignments
            }
            to_assign = min(deviations, key=deviations.get)
        
        assignments[to_assign].extend(post_ids)

    # 统计
    stats = {
        "total_posts": sum(len(v) for v in assignments.values()),
        "total_groups": len(groups),
        "train_posts": len(assignments["train"]),
        "dev_posts": len(assignments["dev"]),
        "test_posts": len(assignments["test"]),
        "train_pct": round(len(assignments["train"]) / max(sum(len(v) for v in assignments.values()), 1) * 100, 1),
        "dev_pct": round(len(assignments["dev"]) / max(sum(len(v) for v in assignments.values()), 1) * 100, 1),
        "test_pct": round(len(assignments["test"]) / max(sum(len(v) for v in assignments.values()), 1) * 100, 1),
    }

    return assignments, stats


def main(input_path: str, train_path: str, dev_path: str, test_path: str,
         report_path: Optional[str] = None, seed: int = 42) -> None:
    records = list(load_jsonl(Path(input_path)))
    groups = build_split_groups(records)

    # 输出 content_group 约束信息
    cg_count = sum(1 for r in records if r.get("content_group_id"))
    print(f"📊 划分前分析:")
    print(f"   总帖子:     {len(records)}")
    print(f"   博主组:     {len(groups)}")
    print(f"   content_group 约束: {cg_count} 条帖子受约束")

    splits, stats = split_groups(groups, seed=seed)
    write_ids(splits["train"], Path(train_path))
    write_ids(splits["dev"], Path(dev_path))
    write_ids(splits["test"], Path(test_path))

    print(f"\n✅ 划分完成:")
    print(f"   train: {stats['train_posts']} ({stats['train_pct']}%)")
    print(f"   dev:   {stats['dev_posts']} ({stats['dev_pct']}%)")
    print(f"   test:  {stats['test_posts']} ({stats['test_pct']}%)")

    leakage = validate_split_leakage(records, splits)
    if any(leakage.values()):
        print(f"\n⚠️  泄漏警告: {leakage}")

    # 保存报告
    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        report = {
            **stats,
            "content_group_constrained_posts": cg_count,
            "blogger_groups": len(groups),
            **leakage,
            "seed": seed,
        }
        with rp.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"📝 报告: {rp}")


if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser(description="按博主+content_group分组划分 train/dev/test")
    parser.add_argument("input", help="金标 JSONL 输入文件")
    parser.add_argument("train", help="train ID 输出文件")
    parser.add_argument("dev", help="dev ID 输出文件")
    parser.add_argument("test", help="test ID 输出文件")
    parser.add_argument("--report", default=None, help="划分报告输出路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    main(args.input, args.train, args.dev, args.test, args.report, args.seed)

"""
合并多个 run_output 目录的数据集。
将四个来源的 JSONL 记录和 media 文件合并为一个统一数据集。

用法：
  python merge_datasets.py

配置：修改下面的 SOURCE_DIRS 和 OUTPUT_DIR。
"""
import json
import os
import re
import shutil
from pathlib import Path

# ============ 配置 ============
BASE = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs")

SOURCE_DIRS = [
    "wechat_20260728_100314",
    "wechat_20260728_012504",
    "bilibili_20260728_130630",
    "bilibili_20260727_162733",
]

OUTPUT_DIR = BASE / "merged_20260728"
# =============================


def parse_jsonl_pretty(filepath: Path) -> list[dict]:
    """
    解析格式化的多行 JSON 文件。
    每个顶层记录以 { 开始（depth=0），以匹配的 } 结束。
    使用 raw_decode 逐个提取顶层 JSON 对象。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    decoder = json.JSONDecoder()
    records = []
    idx = 0
    content_len = len(content)
    
    while idx < content_len:
        # 跳过空白字符
        while idx < content_len and content[idx] in " \t\n\r":
            idx += 1
        if idx >= content_len:
            break
        
        try:
            obj, end = decoder.raw_decode(content, idx)
            records.append(obj)
            idx = end
        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON 解析错误 at pos {idx}: {e}")
            # 尝试跳到下一个 { 
            next_brace = content.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace

    return records


def count_jsonl_records(filepath: Path) -> int:
    """快速统计 JSONL 记录数（通过数顶层 { ）"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    depth = 0
    count = 0
    for ch in content:
        if ch == "{":
            if depth == 0:
                count += 1
            depth += 1
        elif ch == "}":
            depth -= 1
    return count


def ensure_schema_v1_2(record: dict) -> dict:
    """确保记录符合 schema v1.2 标准（从 v1.1 升级）"""
    version = record.get("schema_version", "1.1")
    if version == "1.2":
        return record  # 已是最新
    
    # 从 1.1 升级到 1.2
    record["schema_version"] = "1.2"
    
    # 为 media 项补充 v1.2 新增字段（如果缺失）
    for m in record.get("media", []):
        if "source_url" not in m:
            m["source_url"] = None
        if "caption" not in m:
            m["caption"] = None
        if "is_content" not in m:
            m["is_content"] = None
    
    # 补充 v1.2 可选字段
    record.setdefault("comments", [])
    record.setdefault("blogger_history_refs", [])
    
    # provenance 补充
    if "provenance" in record:
        record["provenance"].setdefault("llm_summary", None)
        record["provenance"].setdefault("llm_extracted_at", None)
    
    # _collected 补充（如果缺失）
    if "_collected" not in record and "provenance" in record:
        record["_collected"] = {
            "source_ref_hash": record["provenance"].get("source_ref_hash", ""),
            "collected_at": record["provenance"].get("collected_at"),
            "collector": record["provenance"].get("collector"),
            "terms_checked_at": record["provenance"].get("terms_checked_at"),
        }
    
    return record


def validate_media_refs(record: dict, source_dir: Path) -> list[str]:
    """
    验证 media ref 指向的文件是否存在。
    返回缺失文件的列表。
    """
    missing = []
    for m in record.get("media", []):
        ref = m.get("ref")
        if ref:
            full_path = source_dir / ref
            if not full_path.exists():
                missing.append(ref)
    return missing


def main():
    print("=" * 60)
    print("数据集合并工具")
    print("=" * 60)
    
    # 创建输出目录
    output_media = OUTPUT_DIR / "media"
    output_media.mkdir(parents=True, exist_ok=True)
    
    all_records = []
    total_media_copied = 0
    total_media_skipped = 0
    missing_refs_total = 0
    
    for src_name in SOURCE_DIRS:
        src_dir = BASE / src_name
        jsonl_path = src_dir / "anonymized_posts.jsonl"
        media_src = src_dir / "media"
        
        if not jsonl_path.exists():
            print(f"\n[SKIP] {src_name}: anonymized_posts.jsonl 不存在")
            continue
        
        print(f"\n{'─' * 50}")
        print(f"处理: {src_name}")
        
        # 统计
        record_count = count_jsonl_records(jsonl_path)
        print(f"  记录数: {record_count}")
        
        # 解析
        print(f"  解析 JSONL...")
        records = parse_jsonl_pretty(jsonl_path)
        print(f"  成功解析: {len(records)} 条记录")
        
        # 复制 media 文件
        media_copied = 0
        media_skipped = 0
        if media_src.is_dir():
            for subdir in os.listdir(media_src):
                subdir_path = media_src / subdir
                if not subdir_path.is_dir():
                    continue
                dest_path = output_media / subdir
                if dest_path.exists():
                    # 目录已存在，跳过（不应发生，因为不同来源的命名空间不同）
                    print(f"  [WARN] media 目录冲突: {subdir}，跳过")
                    media_skipped += 1
                    continue
                shutil.copytree(subdir_path, dest_path)
                media_copied += 1
        
        print(f"  复制 media 目录: {media_copied} 个")
        if media_skipped:
            print(f"  跳过 (冲突): {media_skipped} 个")
        total_media_copied += media_copied
        total_media_skipped += media_skipped
        
        # 升级 schema 并验证
        schema_upgraded = 0
        for record in records:
            old_version = record.get("schema_version", "1.1")
            record = ensure_schema_v1_2(record)
            if old_version != "1.2":
                schema_upgraded += 1
        
        if schema_upgraded:
            print(f"  Schema 升级 (1.1→1.2): {schema_upgraded} 条")
        
        # 验证 media refs
        missing_count = 0
        for record in records:
            missing = validate_media_refs(record, src_dir)
            if missing:
                missing_count += len(missing)
                if missing_count <= 5:  # 只打印前几个
                    print(f"  [WARN] 缺失 media: {record.get('post_id')} -> {missing}")
        if missing_count > 5:
            print(f"  [WARN] 还有更多缺失 media... 总计 {missing_count}")
        missing_refs_total += missing_count
        
        all_records.extend(records)
    
    # 去重检查 (按 post_id)
    print(f"\n{'─' * 50}")
    print("去重检查...")
    seen_ids = set()
    duplicates = []
    unique_records = []
    for r in all_records:
        pid = r.get("post_id")
        if pid in seen_ids:
            duplicates.append(pid)
        else:
            seen_ids.add(pid)
            unique_records.append(r)
    
    if duplicates:
        print(f"  发现 {len(duplicates)} 个重复 post_id，已去除: {duplicates}")
    else:
        print(f"  无重复 post_id")
    
    # 写入合并后的 JSONL
    output_jsonl = OUTPUT_DIR / "anonymized_posts.jsonl"
    print(f"\n写入合并数据: {output_jsonl}")
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for i, record in enumerate(unique_records):
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")
    
    # 汇总报告
    print(f"\n{'=' * 60}")
    print("合并完成！汇总：")
    print(f"  总输入记录: {len(all_records)}")
    print(f"  去重后记录: {len(unique_records)}")
    print(f"  重复去除: {len(duplicates)}")
    print(f"  复制 media 目录: {total_media_copied}")
    print(f"  缺失 media refs: {missing_refs_total}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  输出 JSONL: {output_jsonl}")
    print(f"  输出 media: {output_media}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()

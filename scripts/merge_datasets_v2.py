"""
简化版数据集合并 - 直接拼接 + 后续 schema 升级
分两步：
  Step 1: 合并原始 JSON 内容 + 复制 media 文件
  Step 2: 统一 schema 版本到 1.2
"""
import json
import os
import shutil
from pathlib import Path
import sys

BASE = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs")
OUTPUT = BASE / "merged_20260728"

SOURCE_DIRS = [
    "wechat_20260728_100314",
    "wechat_20260728_012504",
    "bilibili_20260728_130630",
    "bilibili_20260727_162733",
]

LOG_FILE = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\scripts\merge_log.txt")

def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def step1_merge_raw():
    """Step 1: 拼接原始 JSON 文本 + 复制 media"""
    log("=" * 60)
    log("Step 1: 原始文件合并 + media 复制")
    log("=" * 60)
    
    # 清空并重建输出目录
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    output_media = OUTPUT / "media"
    output_media.mkdir(parents=True, exist_ok=True)
    
    merged_raw_path = OUTPUT / "merged_raw.json"
    total_records = 0
    total_media_dirs = 0
    
    with open(merged_raw_path, "w", encoding="utf-8") as out_f:
        for src_name in SOURCE_DIRS:
            src_dir = BASE / src_name
            jsonl_path = src_dir / "anonymized_posts.jsonl"
            media_src = src_dir / "media"
            
            if not jsonl_path.exists():
                log(f"[SKIP] {src_name}: 无 anonymized_posts.jsonl")
                continue
            
            # 统计
            raw_text = jsonl_path.read_text(encoding="utf-8-sig")
            record_count = raw_text.count('"schema_version"')
            log(f"\n处理: {src_name} ({record_count} 条记录)")
            
            # 拼接 JSON 内容
            out_f.write(raw_text)
            # 确保记录之间有换行分隔
            if not raw_text.endswith("\n"):
                out_f.write("\n")
            total_records += record_count
            
            # 复制 media 目录
            if media_src.is_dir():
                subdirs = [d for d in os.listdir(media_src) 
                          if os.path.isdir(media_src / d)]
                for subdir in subdirs:
                    src_path = media_src / subdir
                    dst_path = output_media / subdir
                    if not dst_path.exists():
                        shutil.copytree(src_path, dst_path)
                        total_media_dirs += 1
                    else:
                        log(f"  [WARN] media 目录冲突: {subdir}")
                log(f"  复制 media: {len(subdirs)} 个目录")
    
    log(f"\n合并完成: {total_records} 条记录, {total_media_dirs} 个 media 目录")
    log(f"原始合并文件: {merged_raw_path}")
    return merged_raw_path


def step2_upgrade_schema(raw_path: Path):
    """Step 2: 解析合并文件，升级 schema，写为标准 JSONL"""
    log("\n" + "=" * 60)
    log("Step 2: Schema 升级 + 写入标准 JSONL")
    log("=" * 60)
    
    raw_text = raw_path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    
    output_jsonl = OUTPUT / "anonymized_posts.jsonl"
    
    total = 0
    upgraded = 0
    errors = 0
    seen_ids = set()
    duplicates = 0
    
    with open(output_jsonl, "w", encoding="utf-8") as out_f:
        idx = 0
        content_len = len(raw_text)
        
        while idx < content_len:
            # 跳过空白
            while idx < content_len and raw_text[idx] in " \t\n\r":
                idx += 1
            if idx >= content_len:
                break
            
            try:
                obj, end = decoder.raw_decode(raw_text, idx)
                idx = end
                
                if not isinstance(obj, dict):
                    log(f"  [WARN] 非对象记录 at pos {idx}, 跳过")
                    continue
                
                pid = obj.get("post_id", "")
                if pid in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(pid)
                
                # Schema 升级: 1.1 → 1.2
                old_ver = obj.get("schema_version", "1.1")
                if old_ver != "1.2":
                    obj["schema_version"] = "1.2"
                    # 补充 v1.2 字段
                    for m in obj.get("media", []):
                        m.setdefault("source_url", None)
                        m.setdefault("caption", None)
                        m.setdefault("is_content", None)
                    obj.setdefault("comments", [])
                    obj.setdefault("blogger_history_refs", [])
                    if "provenance" in obj:
                        obj["provenance"].setdefault("llm_summary", None)
                        obj["provenance"].setdefault("llm_extracted_at", None)
                    upgraded += 1
                
                out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                total += 1
                
                if total % 1000 == 0:
                    log(f"  已处理 {total} 条...")
                    
            except json.JSONDecodeError as e:
                log(f"  [ERROR] JSON 解析错误 at pos {idx}: {e}")
                errors += 1
                # 跳到下一个 {
                next_brace = raw_text.find("{", idx + 1)
                if next_brace == -1:
                    break
                idx = next_brace
    
    log(f"\n写入完成:")
    log(f"  总记录数: {total}")
    log(f"  Schema 升级: {upgraded}")
    log(f"  去重 (重复 post_id): {duplicates}")
    log(f"  解析错误: {errors}")
    log(f"  输出: {output_jsonl}")
    
    # 删除原始合并文件 (可选)
    # raw_path.unlink()
    
    return total


def main():
    # 清空日志
    LOG_FILE.write_text("", encoding="utf-8")
    
    log("数据集合并开始...")
    
    # Step 1: 原始合并
    raw_path = step1_merge_raw()
    
    # Step 2: Schema 升级
    total = step2_upgrade_schema(raw_path)
    
    log(f"\n{'=' * 60}")
    log(f"全部完成! 最终数据集: {OUTPUT / 'anonymized_posts.jsonl'}")
    log(f"Media 目录: {OUTPUT / 'media'}")
    log(f"{'=' * 60}")
    
    print(f"\nDone. See {LOG_FILE} for details.")


if __name__ == "__main__":
    main()

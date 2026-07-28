"""
增量合并脚本 - 不清除已有数据
只复制缺失的 media + 生成合并 JSONL
"""
import json
import os
import shutil
from pathlib import Path

BASE = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs")
OUTPUT = BASE / "merged_20260728"

SOURCE_DIRS = [
    "wechat_20260728_100314",
    "wechat_20260728_012504",
    "bilibili_20260728_130630",
    "bilibili_20260727_162733",
]

def log(msg):
    print(msg, flush=True)

def main():
    output_media = OUTPUT / "media"
    output_media.mkdir(parents=True, exist_ok=True)
    
    # ====== Step 1: 增量复制 media (跳过已存在的) ======
    log("=" * 60)
    log("Step 1: 增量复制 media 文件")
    log("=" * 60)
    
    for src_name in SOURCE_DIRS:
        src_dir = BASE / src_name
        media_src = src_dir / "media"
        
        if not media_src.is_dir():
            continue
        
        existing = set(os.listdir(output_media))
        subdirs = [d for d in os.listdir(media_src) if os.path.isdir(media_src / d)]
        new_dirs = [d for d in subdirs if d not in existing]
        
        if new_dirs:
            log(f"{src_name}: 复制 {len(new_dirs)} 个新 media 目录...")
            for i, subdir in enumerate(new_dirs):
                src_path = media_src / subdir
                dst_path = output_media / subdir
                shutil.copytree(src_path, dst_path)
                if (i + 1) % 100 == 0:
                    log(f"  已复制 {i+1}/{len(new_dirs)}...")
        else:
            log(f"{src_name}: 所有 media 目录已存在，跳过")
    
    # ====== Step 2: 合并 JSONL ======
    log("\n" + "=" * 60)
    log("Step 2: 合并 JSONL 记录")
    log("=" * 60)
    
    all_records = []
    seen_ids = set()
    dupes = 0
    
    for src_name in SOURCE_DIRS:
        jsonl_path = BASE / src_name / "anonymized_posts.jsonl"
        if not jsonl_path.exists():
            continue
        
        log(f"读取: {src_name} ...")
        raw_text = jsonl_path.read_text(encoding="utf-8-sig")
        decoder = json.JSONDecoder()
        
        idx = 0
        content_len = len(raw_text)
        count = 0
        errors = 0
        
        while idx < content_len:
            while idx < content_len and raw_text[idx] in " \t\n\r":
                idx += 1
            if idx >= content_len:
                break
            
            try:
                obj, end = decoder.raw_decode(raw_text, idx)
                idx = end
                
                if not isinstance(obj, dict):
                    continue
                
                pid = obj.get("post_id", "")
                if pid in seen_ids:
                    dupes += 1
                    continue
                seen_ids.add(pid)
                
                # Schema 升级 1.1 → 1.2
                if obj.get("schema_version") != "1.2":
                    obj["schema_version"] = "1.2"
                    for m in obj.get("media", []):
                        m.setdefault("source_url", None)
                        m.setdefault("caption", None)
                        m.setdefault("is_content", None)
                    obj.setdefault("comments", [])
                    obj.setdefault("blogger_history_refs", [])
                    if "provenance" in obj:
                        obj["provenance"].setdefault("llm_summary", None)
                        obj["provenance"].setdefault("llm_extracted_at", None)
                
                all_records.append(obj)
                count += 1
                
            except json.JSONDecodeError as e:
                errors += 1
                if errors <= 3:
                    log(f"  [WARN] JSON 错误 at pos {idx}: {e}")
                next_brace = raw_text.find("{", idx + 1)
                if next_brace == -1:
                    break
                idx = next_brace
        
        log(f"  读取: {count} 条 (错误: {errors})")
    
    # ====== Step 3: 写入 ======
    log(f"\n去重: 移除 {dupes} 条重复")
    output_jsonl = OUTPUT / "anonymized_posts.jsonl"
    log(f"写入: {output_jsonl} ({len(all_records)} 条记录)")
    
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # 统计
    log(f"\n{'=' * 60}")
    log(f"合并完成!")
    log(f"  总记录数: {len(all_records)}")
    log(f"  输出: {output_jsonl}")
    log(f"  Media: {output_media}")
    
    # 按平台统计
    platforms = {}
    for r in all_records:
        p = r.get("platform", "unknown")
        platforms[p] = platforms.get(p, 0) + 1
    for p, c in sorted(platforms.items()):
        log(f"  {p}: {c}")
    
    log(f"{'=' * 60}")

if __name__ == "__main__":
    main()

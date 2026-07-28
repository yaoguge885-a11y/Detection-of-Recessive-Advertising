"""
纯 JSONL 合并脚本 - 只合并 JSONL 文件，不复制 media
Media 复制使用 robocopy 单独处理
"""
import json
from pathlib import Path

BASE = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs")
OUTPUT = BASE / "merged_20260728"

SOURCE_DIRS = [
    ("wechat_20260728_100314", "wechat_official_account"),
    ("wechat_20260728_012504", "wechat_official_account"),
    ("bilibili_20260728_130630", "bilibili"),
    ("bilibili_20260727_162733", "bilibili"),
]

def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_jsonl = OUTPUT / "anonymized_posts.jsonl"
    
    all_records = []
    seen_ids = set()
    dupes = 0
    errors = 0
    
    for src_name, platform in SOURCE_DIRS:
        jsonl_path = BASE / src_name / "anonymized_posts.jsonl"
        if not jsonl_path.exists():
            print(f"[SKIP] {src_name}: not found")
            continue
        
        print(f"Reading: {src_name} ...", flush=True)
        raw_text = jsonl_path.read_text(encoding="utf-8-sig")
        decoder = json.JSONDecoder()
        
        idx = 0
        content_len = len(raw_text)
        count = 0
        
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
                
                # Schema upgrade 1.1 -> 1.2
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
                    if "_collected" not in obj:
                        p = obj.get("provenance", {})
                        obj["_collected"] = {
                            "source_ref_hash": p.get("source_ref_hash", ""),
                            "collected_at": p.get("collected_at"),
                            "collector": p.get("collector"),
                            "terms_checked_at": p.get("terms_checked_at"),
                        }
                
                all_records.append(obj)
                count += 1
                
            except json.JSONDecodeError as e:
                errors += 1
                if errors <= 5:
                    print(f"  [WARN] JSON error at pos {idx}: {e}")
                next_brace = raw_text.find("{", idx + 1)
                if next_brace == -1:
                    break
                idx = next_brace
        
        print(f"  -> {count} records (errors: {errors})", flush=True)
    
    # Write standard JSONL
    print(f"\nWriting: {output_jsonl} ({len(all_records)} records)", flush=True)
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # Summary
    print(f"\n=== Summary ===")
    print(f"Total records: {len(all_records)}")
    print(f"Duplicates removed: {dupes}")
    print(f"Parse errors: {errors}")
    
    from collections import Counter
    platforms = Counter(r.get("platform", "?") for r in all_records)
    for p, c in sorted(platforms.items()):
        print(f"  {p}: {c}")
    
    print(f"\nOutput: {output_jsonl}")
    print("Done! (Media files still need to be copied separately)")

if __name__ == "__main__":
    main()

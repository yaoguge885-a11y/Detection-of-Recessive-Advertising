"""
修复合并后 JSONL 的 schema 合规性问题:
1. is_content 字段从 null 改为 false
2. 从 provenance 中移除 llm_summary 和 llm_extracted_at (这些字段应在 _collected 中)
"""
import json
from pathlib import Path

INPUT = Path(r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs\merged_20260728\anonymized_posts.jsonl")
OUTPUT = INPUT  # 原地修复
BACKUP = INPUT.with_suffix(".jsonl.bak")

def main():
    # 备份
    print(f"Backing up to {BACKUP}")
    BACKUP.write_text(INPUT.read_text(encoding="utf-8"), encoding="utf-8")
    
    fixed = 0
    is_content_fixed = 0
    provenance_fixed = 0
    missing_platform = 0
    
    with open(INPUT, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                f.write(line + "\n")
                continue
            
            # Fix 1: is_content should be boolean, not null
            for m in record.get("media", []):
                if "is_content" in m and m["is_content"] is None:
                    m["is_content"] = False
                    is_content_fixed += 1
            
            # Fix 2: Remove llm_summary and llm_extracted_at from provenance
            if "provenance" in record:
                p = record["provenance"]
                if "llm_summary" in p:
                    del p["llm_summary"]
                    provenance_fixed += 1
                if "llm_extracted_at" in p:
                    del p["llm_extracted_at"]
                    provenance_fixed += 1
            
            # Fix 3: Ensure platform is valid
            if "platform" not in record or not record.get("platform"):
                record["platform"] = "other"
                missing_platform += 1
            
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            fixed += 1
    
    print(f"\nFixed {fixed} records:")
    print(f"  is_content: {is_content_fixed} media items fixed (null -> false)")
    print(f"  provenance llm fields removed: {provenance_fixed}")
    print(f"  missing platform: {missing_platform}")
    print(f"\nOutput: {OUTPUT}")
    print(f"Backup: {BACKUP}")

if __name__ == "__main__":
    main()

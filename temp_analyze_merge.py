"""分析四个 run_output 目录的数据结构，为合并做准备"""
import json
import os
import re

BASE = r"d:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs"

SOURCES = [
    "wechat_20260728_100314",
    "wechat_20260728_012504",
    "bilibili_20260728_130630",
    "bilibili_20260727_162733",
]

def parse_jsonl_pretty(filepath):
    """解析格式化的多行 JSON 文件（每个记录以 { 开始，以 } 结束）"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    records = []
    depth = 0
    start = None
    for i, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                records.append(json.loads(content[start:i+1]))
                start = None
    return records

def main():
    for src in SOURCES:
        jsonl_path = os.path.join(BASE, src, "anonymized_posts.jsonl")
        if not os.path.exists(jsonl_path):
            print(f"[SKIP] {src}: anonymized_posts.jsonl not found")
            continue
        
        records = parse_jsonl_pretty(jsonl_path)
        
        # Count media directories
        media_dir = os.path.join(BASE, src, "media")
        media_subdirs = []
        if os.path.isdir(media_dir):
            media_subdirs = [d for d in os.listdir(media_dir) 
                           if os.path.isdir(os.path.join(media_dir, d))]
        
        # Find a record with image refs
        sample_with_images = None
        for r in records:
            if any(m.get("ref") and m.get("type") == "image" for m in r.get("media", [])):
                sample_with_images = r
                break
        
        print(f"\n=== {src} ===")
        print(f"  Records: {len(records)}")
        print(f"  Media subdirs: {len(media_subdirs)}")
        if records:
            r0 = records[0]
            print(f"  Schema: {r0.get('schema_version')}")
            print(f"  Platform: {r0.get('platform')}")
            print(f"  First post_id: {r0.get('post_id')}")
            print(f"  Media items: {len(r0.get('media', []))}")
            for m in r0.get("media", [])[:3]:
                print(f"    - type={m.get('type')}, ref={m.get('ref')}")
        
        if sample_with_images:
            print(f"  Sample with images (post_id={sample_with_images['post_id']}):")
            for m in sample_with_images.get("media", [])[:5]:
                print(f"    - type={m.get('type')}, ref={m.get('ref')}")
        
        if media_subdirs:
            sd0 = media_subdirs[0]
            sd_path = os.path.join(media_dir, sd0)
            files = os.listdir(sd_path)
            print(f"  First media dir: {sd0} -> {files[:5]}...")

if __name__ == "__main__":
    main()

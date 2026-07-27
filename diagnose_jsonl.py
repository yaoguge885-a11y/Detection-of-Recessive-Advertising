"""Diagnose the JSONL structure."""
import json, re
path = r'd:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs\bilibili_20260727_162733\anonymized_posts.jsonl'
raw = open(path, encoding='utf-8-sig').read()
print(f"File size: {len(raw)} chars, {len(raw.encode('utf-8'))} bytes")

# Test: parse with raw_decode, report each result
decoder = json.JSONDecoder()
idx = 0
n = len(raw)
obj_count = 0
while idx < n:
    while idx < n and raw[idx] in ' \t\n\r':
        idx += 1
    if idx >= n:
        break
    try:
        obj, end = decoder.raw_decode(raw, idx)
        t = type(obj).__name__
        if isinstance(obj, dict):
            keys = list(obj.keys())[:3]
            pid = obj.get('post_id', '')
            has_media = 'media' in obj
            print(f"  [{obj_count}] dict keys={keys}... | post_id={pid[:30] if pid else 'NONE'} | has_media={has_media}")
        else:
            print(f"  [{obj_count}] {t}: {str(obj)[:80]}")
        obj_count += 1
        idx = end
    except json.JSONDecodeError as e:
        # Show context around error
        ctx = raw[idx:idx+100]
        print(f"  ERROR at char {idx}: {e}")
        print(f"    context: {repr(ctx[:80])}")
        next_brace = raw.find('{', idx + 1)
        if next_brace == -1:
            break
        idx = next_brace

print(f"\nTotal objects parsed: {obj_count}")
print(f"Remaining unparsed: {n - idx} chars")

# Now test with the regex fix
print("\n=== After regex fix ===")
fixed = re.sub(r'(\S)\s*\n\s*\],\s*\n(\s*)"comments"', r'\1,\n\2"comments"', raw)
print(f"Regex made {'changes' if fixed != raw else 'NO changes'}")
decoder2 = json.JSONDecoder()
idx = 0
n2 = len(fixed)
obj_count2 = 0
while idx < n2:
    while idx < n2 and fixed[idx] in ' \t\n\r':
        idx += 1
    if idx >= n2:
        break
    try:
        obj, end = decoder2.raw_decode(fixed, idx)
        if isinstance(obj, dict):
            pid = obj.get('post_id', '')
            print(f"  [{obj_count2}] post_id={pid[:30] if pid else 'NONE'} | keys={list(obj.keys())[:4]}")
        obj_count2 += 1
        idx = end
    except json.JSONDecodeError as e:
        ctx = fixed[idx:idx+100]
        print(f"  ERROR at char {idx}: {e} | ctx={repr(ctx[:60])}")
        next_brace = fixed.find('{', idx + 1)
        if next_brace == -1:
            break
        idx = next_brace
print(f"Total after fix: {obj_count2}")

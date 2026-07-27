import json
raw = open(r'd:\projectsnew\Detection-of-Recessive-Advertising\data\run_outputs\bilibili_20260727_162733\anonymized_posts.jsonl', 'r', encoding='utf-8-sig').read()
decoder = json.JSONDecoder()
idx = 0
n = len(raw)
posts = []
while idx < n:
    while idx < n and raw[idx] in ' \t\n\r': idx += 1
    if idx >= n: break
    try:
        obj, end = decoder.raw_decode(raw, idx)
        posts.append(obj)
        idx = end
    except:
        idx = raw.find('{', idx + 1)
        if idx == -1: break

for i, p in enumerate(posts[:5]):
    media = p.get('media', [])
    pid = p.get('post_id', '?')
    title = p.get('title', '')[:60]
    print(f'Post {i}: {pid[:30]} | title={title}')
    for j, m in enumerate(media):
        t = m.get('type')
        ref = m.get('ref')
        url = (m.get('source_url') or '')[:80]
        print(f'  media[{j}]: type={t} | ref={ref} | source_url={url}')
    print()

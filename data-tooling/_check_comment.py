"""Find aid for a B站 video and test comment API."""
from playwright.sync_api import sync_playwright
import re, json, requests

bvid = "BV1e7gD6FEZt"
aid = None

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto(f"https://www.bilibili.com/video/{bvid}", timeout=20000)
    page.wait_for_timeout(3000)
    html = page.content()
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*\(function', html, re.DOTALL)
    if m:
        state = json.loads(m.group(1))
        v = state.get("videoData", {})
        aid = v.get("aid")
        print(f"aid={aid}, bvid={v.get('bvid')}, title={v.get('title','')[:40]}")
    b.close()

if aid:
    print(f"\nTesting comment API with aid={aid}...")
    r = requests.get(
        f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn=1&ps=3&sort=1",
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"})
    d = r.json()
    print(f"code={d.get('code')} msg={d.get('message','')}")
    replies = d.get("data", {}).get("replies", [])
    print(f"Comment count: {len(replies)}")
    for rp in replies[:3]:
        uname = rp.get("member", {}).get("uname", "?")
        msg = rp.get("content", {}).get("message", "")[:80]
        pics = rp.get("content", {}).get("pictures", [])
        print(f"  [{uname}] {msg}{' [有'+str(len(pics))+'图]' if pics else ''}")

"""Find what API loads opus/dynamic list from B站 space."""
from playwright.sync_api import sync_playwright
import json

mid = "277975006"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled','--no-sandbox'])
    ctx = b.new_context(viewport={'width':1366,'height':768},locale='zh-CN')
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page = ctx.new_page()
    
    apis = {}
    def on_resp(resp):
        url = resp.url
        if 'api.bilibili.com' not in url:
            return
        # Focus on dynamic/opus related APIs
        if any(k in url for k in ['dynamic', 'opus', 'feed/space', 'polymer']):
            try:
                body = resp.json()
                code = body.get('code', -1)
                data = body.get('data', {})
                # Check what's inside
                items_key = None
                item_count = 0
                for key, val in data.items():
                    if isinstance(val, list) and len(val) > 0:
                        items_key = key
                        item_count = len(val)
                if items_key:
                    path = url.split('api.bilibili.com/')[1].split('?')[0] if 'api.bilibili.com/' in url else url
                    apis[path] = f'code={code} data.{items_key}=[{item_count}] | sample_keys={list(data.get(items_key,[{}])[0].keys())[:8] if isinstance(data.get(items_key,[{}])[0], dict) else "?"}'
            except:
                pass
    page.on('response', on_resp)
    
    print(f'Loading space/{mid}/dynamic ...')
    page.goto(f'https://space.bilibili.com/{mid}/dynamic', wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(3000)
    # Scroll to trigger more loading
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 500)")
        page.wait_for_timeout(1000)
    
    if apis:
        print(f'\nFound {len(apis)} dynamic-related APIs:')
        for path, info in apis.items():
            print(f'  {path}')
            print(f'    {info}')
    else:
        print('\nNo dynamic APIs found')
    
    b.close()

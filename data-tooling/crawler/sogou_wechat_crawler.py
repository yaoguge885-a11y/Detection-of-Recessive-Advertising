#!/usr/bin/env python3
"""
Sogou WeChat article crawler using Playwright.
Search for articles by account name, visit every article, match author field inside the article.
"""
import time, re, sys, argparse
from urllib.parse import urljoin, quote
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


def extract_author_from_article(html: str) -> tuple:
    """从微信文章 HTML 提取 (公众号名称, 文章作者)。

    微信公众号文章页面中：
      - var nickname = "xxx"  → 公众号注册名称（#js_name 元素亦可）
      - var author = "xxx"    → 单篇文章自定义作者（可不同于公众号名）
    Returns: (nickname, author) —— 提取不到为空字符串。
    """
    nickname = ""
    author = ""

    # var nickname = "xxx"
    m = re.search(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']', html)
    if m:
        nickname = m.group(1).strip()

    # var author = "xxx"
    m = re.search(r'var\s+author\s*=\s*["\']([^"\']*)["\']', html)
    if m:
        author = m.group(1).strip()

    # <meta name="author" content="xxx"> 兜底
    if not author:
        m = re.search(
            r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if m:
            author = m.group(1).strip()

    # id="js_name" 兜底（页脚公众号名元素）
    if not nickname:
        m = re.search(r'id=["\']js_name["\'][^>]*>([^<]+)<', html)
        if m:
            nickname = m.group(1).strip()

    return nickname, author


def crawl_sogou_wechat(account_name: str, max_articles: int = 50, max_pages: int = 10,
                       greedy: bool = False):
    """Crawl Sogou WeChat search for articles from a specific account.

    策略：搜索页只提取候选链接（不再依赖搜狗 HTML 中的发布者 span），
    对每一页的每一篇文章都实际访问，在文章页面内提取
    var nickname（公众号名）/ var author（文章作者）字段进行匹配。
    匹配通过的文章才进入结果；输出结构与之前保持一致。

    greedy=True 时：上限大幅提高、遍历更多页、早停阈值放宽，尽可能多抓。
    """
    # 贪婪模式：大幅放宽上限与页数
    if greedy:
        max_articles = max(max_articles, 10000)
        max_pages = max(max_pages, 100)

    query = quote(account_name)
    results = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        consecutive_empty = 0  # 连续空页计数器
        # 贪婪模式放宽连续空页阈值
        empty_limit = 10 if greedy else 5

        for page_num in range(1, max_pages + 1):
            if len(results) >= max_articles:
                break

            search_url = f"https://weixin.sogou.com/weixin?type=2&query={query}&page={page_num}"
            print(f"\n[Page {page_num}] Loading...")

            try:
                page.goto(search_url, wait_until="networkidle", timeout=30000)
                time.sleep(3)
            except Exception as e:
                print(f"  Failed: {e}")
                consecutive_empty += 1
                if consecutive_empty >= empty_limit:
                    print(f"  连续 {consecutive_empty} 页加载失败，终止搜索")
                    break
                continue

            soup = BeautifulSoup(page.content(), "html.parser")

            # 提取候选文章链接（不依赖 publisher span，全部作为候选）
            entries = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "link?url=" not in href:
                    continue
                title = a.get_text(strip=True)
                if not title or len(title) <= 3:
                    continue
                link = urljoin("https://weixin.sogou.com", href)
                entries.append({"title": title, "link": link})

            # 早停：连续 N 页没有任何条目时终止
            if not entries:
                consecutive_empty += 1
                print(f"  本页无任何条目（连续空页 {consecutive_empty}/{empty_limit}）")
                if consecutive_empty >= empty_limit:
                    print(f"  连续 {consecutive_empty} 页无内容，终止搜索")
                    break
                continue
            else:
                consecutive_empty = 0  # 有内容则重置

            print(f"  {len(entries)} 条候选文章，逐篇访问并匹配作者字段...")

            # 逐篇访问，在文章内匹配作者字段
            for entry in entries:
                if len(results) >= max_articles:
                    break
                if entry["link"] in seen_links:
                    continue
                seen_links.add(entry["link"])

                try:
                    new_page = context.new_page()
                    new_page.goto(entry["link"], wait_until="domcontentloaded", timeout=20000)
                    try:
                        new_page.wait_for_url("**mp.weixin.qq.com**", timeout=10000)
                    except:
                        pass
                    time.sleep(1.5)
                    final_url = new_page.url

                    # 仅在跳转到真实微信文章页后，才读取文章内容提取作者字段
                    matched_publisher = ""
                    if "mp.weixin.qq.com" in final_url:
                        article_html = new_page.content()
                        nickname, author = extract_author_from_article(article_html)
                        acc = account_name.lower()
                        if nickname and acc in nickname.lower():
                            matched_publisher = nickname
                        elif author and acc in author.lower():
                            matched_publisher = author
                    new_page.close()

                    if matched_publisher:
                        results.append({
                            "title": entry["title"],
                            "url": final_url,
                            "publisher": matched_publisher,
                        })
                        print(f"  [{len(results)}] {entry['title'][:50]} | 匹配:{matched_publisher}")
                    else:
                        print(f"  [skip] 作者字段不匹配: {entry['title'][:40]}")
                except Exception as e:
                    print(f"  [err] {str(e)[:60]}")
                    try: new_page.close()
                    except: pass

            time.sleep(1)

        browser.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="Sogou WeChat article crawler (Playwright)")
    parser.add_argument("--account", required=True, help="Public account name")
    parser.add_argument("--max-articles", type=int, default=50, help="Max articles to fetch")
    parser.add_argument("--max-pages", type=int, default=10, help="Max search pages")
    parser.add_argument("--greedy", action="store_true",
                        help="贪婪模式：上限提至 10000 篇、遍历 100 页、早停阈值放宽，尽可能多抓")
    parser.add_argument("--output", default="data/run_outputs/urls_from_sogou.txt", help="Output file")
    args = parser.parse_args()

    print(f"Searching Sogou for: {args.account}{' (贪婪模式)' if args.greedy else ''}")
    articles = crawl_sogou_wechat(args.account, args.max_articles, args.max_pages, args.greedy)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for a in articles:
            f.write(f"{a['url']}\t{a['title']}\t{a['publisher']}\n")

    print(f"\n{'='*60}")
    print(f"Done! {len(articles)} articles saved to {out_path}")
    for a in articles:
        print(f"  {a['title'][:50]}")
        print(f"  -> {a['url'][:100]}")


if __name__ == "__main__":
    main()

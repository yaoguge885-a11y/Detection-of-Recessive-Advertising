"""Regression tests for semantic HTML cleanup in the structure extractor."""
from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

from html_structure_extractor import extract_from_html  # noqa: E402


def test_body_fallback_drops_page_chrome_recommendations_and_hidden_media():
    result = extract_from_html(
        """
        <html><body>
          <nav>
            <p>导航推荐广告商品</p>
            <img src="https://example.test/nav.jpg" width="640" height="480">
          </nav>
          <main>
            <p>正文保留商业合作说明与商品链接：
              <a href="https://shop.example.test/item">商品详情</a>
            </p>
            <img src="data:image/png;base64,not-a-source" width="640" height="480">
            <img src="/relative.jpg" width="640" height="480">
            <figure>
            <img src="https://example.test/article.jpg?token=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" width="640" height="480">
              <figcaption>正文图片说明</figcaption>
            </figure>
            <aside role="complementary"><p>主体内披露：品牌方赞助。</p></aside>
            <footer><p>主体内披露：本篇属于广告合作。</p></footer>
          </main>
          <div class="recommendations">
            <p>猜你喜欢广告商品</p>
            <img src="https://example.test/recommendation.jpg" width="640" height="480">
          </div>
          <aside role="complementary">
            <p>相关阅读商业内容</p>
            <img src="https://example.test/aside.jpg" width="640" height="480">
          </aside>
          <footer>
            <p>页脚广告商品</p>
            <img src="https://example.test/footer.jpg" width="640" height="480">
          </footer>
          <div style="display: none">
            <p>隐藏广告商品</p>
            <img src="https://example.test/hidden-style.jpg" width="640" height="480">
          </div>
          <div aria-hidden="true">
            <p>辅助隐藏广告商品</p>
            <img src="https://example.test/hidden-aria.jpg" width="640" height="480">
          </div>
        </body></html>
        """
    )

    assert "正文保留商业合作说明" in result["clean_text"]
    assert "商品详情" in result["clean_text"]
    assert "<图片1>" in result["clean_text"]
    assert "<图片2>" not in result["clean_text"]
    assert "主体内披露：品牌方赞助" in result["clean_text"]
    assert "主体内披露：本篇属于广告合作" in result["clean_text"]
    assert "导航推荐广告商品" not in result["clean_text"]
    assert "猜你喜欢广告商品" not in result["clean_text"]
    assert "隐藏广告商品" not in result["clean_text"]
    assert result["image_urls"] == [
        "https://example.test/article.jpg?token=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    ]
    assert len(result["media_enrichments"]) == 1
    assert result["media_enrichments"][0]["index"] == 0
    assert result["media_enrichments"][0]["is_content"] is True
    assert result["media_enrichments"][0]["caption"] == "正文图片说明"


def test_in_article_sponsor_disclosure_is_not_removed_by_word_matching():
    result = extract_from_html(
        """
        <article>
          <p>本文由品牌合作方赞助，广告合作内容已按要求披露。</p>
          <p>推荐购买这件商品的理由写在正文中，不是页面推荐模块。</p>
          <aside role="complementary">
            <p>正文内补充披露：品牌合作方已提供赞助。</p>
          </aside>
          <footer>
            <p>正文内声明：本内容属于付费合作。</p>
          </footer>
          <aside role="complementary" aria-label="相关推荐">
            <p>无关推荐模块的购买链接。</p>
          </aside>
        </article>
        """
    )

    assert "品牌合作方赞助" in result["clean_text"]
    assert "广告合作内容已按要求披露" in result["clean_text"]
    assert "推荐购买这件商品的理由" in result["clean_text"]
    assert "品牌合作方已提供赞助" in result["clean_text"]
    assert "本内容属于付费合作" in result["clean_text"]
    assert "无关推荐模块的购买链接" not in result["clean_text"]


def test_js_content_keeps_structural_disclosures():
    result = extract_from_html(
        """
        <div id="js_content">
          <p>正文主体。</p>
          <aside role="complementary"><p>本文由品牌方赞助。</p></aside>
          <footer><p>本篇属于广告合作。</p></footer>
        </div>
        """
    )

    assert "本文由品牌方赞助" in result["clean_text"]
    assert "本篇属于广告合作" in result["clean_text"]


def test_hidden_class_and_visibility_style_drop_entire_subtrees():
    result = extract_from_html(
        """
        <div id="js_content">
          <p>正文</p>
          <div class="is-hidden">
            <p>隐藏类文字</p>
            <img src="https://example.test/hidden-class.jpg" width="640" height="480">
          </div>
          <div style="visibility: hidden !important">
            <p>隐藏样式文字</p>
            <img src="https://example.test/hidden-visibility.jpg" width="640" height="480">
          </div>
        </div>
        """
    )

    assert result["clean_text"] == "正文"
    assert result["image_urls"] == []
    assert result["media_enrichments"] == []


def test_empty_cleanup_result_is_reviewable_instead_of_raw_body_fallback():
    result = extract_from_html(
        """
        <html><body>
          <nav><p>站点推荐广告</p></nav>
          <aside><p>相关推荐商品</p></aside>
          <footer><p>页脚商业内容</p></footer>
        </body></html>
        """
    )

    assert result["clean_text"] == ""
    assert result["needs_review"] is True

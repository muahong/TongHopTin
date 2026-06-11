"""Lao Dong scraper (laodong.vn) - RSS-based via Playwright.

laodong.vn guards every URL with a JS cookie challenge: the first response is a
tiny HTML shell that sets ``document.cookie="D1N=..."`` and calls
``window.location.reload()``. Playwright runs the JS, accepts the cookie, and
the reload then serves the real RSS -- so listing must use Playwright. The
Fetcher exports the solved cookie into its aiohttp jar, after which detail
pages are fetched over plain HTTP (a browser round-trip per article made this
site the slowest in the crawl by far).
"""

from __future__ import annotations

from tonghoptin.models import Article, ArticleStub, FetchMethod
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("laodong.vn")
class LaoDongScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/home.rss", "Trang chủ"),
        ("/rss/thoi-su.rss", "Thời sự"),
        ("/rss/kinh-doanh.rss", "Kinh doanh"),
        ("/rss/xa-hoi.rss", "Xã hội"),
        ("/rss/phap-luat.rss", "Pháp luật"),
        ("/rss/the-gioi.rss", "Thế giới"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
        ("/rss/giao-duc.rss", "Giáo dục"),
        ("/rss/cong-doan.rss", "Công đoàn"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article-title, h1.title-detail, h1"
    DETAIL_DATE_SELECTOR = "time[datetime], div.article-date, span.time, time"
    DETAIL_BODY_SELECTOR = "div.article-content, div.detail-content, article"
    DETAIL_AUTHOR_SELECTOR = "div.author-info, span.author, meta[name='author']"

    def detail_fetch_method(self) -> FetchMethod:
        # Plain HTTP works once the listing fetch exported the challenge
        # cookie into the aiohttp jar (see Fetcher._export_cookies).
        return FetchMethod.REQUESTS

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        # If the challenge shell came back, the cookie didn't transfer --
        # raise so the failure is recorded instead of publishing an empty
        # article.
        if "document.cookie" in html[:2000] and len(html) < 4000:
            raise ValueError("laodong cookie challenge not passed")
        return super().parse_article_detail(html, stub)

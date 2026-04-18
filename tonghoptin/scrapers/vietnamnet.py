"""VietnamNet scraper.

Uses VietnamNet's RSS feeds for listing discovery. RSS items carry a reliable
``<pubDate>`` so the base class drops non-target-date stubs before detail
fetch. The previous DOM-pagination path discovered ~2170 stubs, deduped to
433, and fetched every one -- the detail-page date selector often failed,
falling back to ``datetime.now()``, which made the target-date filter a no-op.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("vietnamnet.vn")
class VietnamNetScraper(BaseScraper):

    RSS_FEEDS = [
        ("/rss/thoi-su.rss", "Thời sự"),
        ("/rss/chinh-tri.rss", "Chính trị"),
        ("/rss/the-gioi.rss", "Thế giới"),
        ("/rss/kinh-doanh.rss", "Kinh doanh"),
        ("/rss/giao-duc.rss", "Giáo dục"),
        ("/rss/doi-song.rss", "Đời sống"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
        ("/rss/giai-tri.rss", "Giải trí"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/oto-xe-may.rss", "Ô tô - Xe máy"),
        ("/rss/bat-dong-san.rss", "Bất động sản"),
        ("/rss/du-lich.rss", "Du lịch"),
        ("/rss/phap-luat.rss", "Pháp luật"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.RSS_FEEDS]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        stubs: list[ArticleStub] = []
        for item in re.findall(r"<item>(.*?)</item>", html, re.DOTALL):
            url_m = re.search(r"<link>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</link>", item, re.DOTALL)
            title_m = re.search(r"<title>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</title>", item, re.DOTALL)
            pub_m = re.search(r"<pubDate>\s*(.*?)\s*</pubDate>", item, re.DOTALL)

            if not url_m or not title_m:
                continue
            url = url_m.group(1).strip()
            title = title_m.group(1).strip()
            if not url or not title:
                continue

            pub_date = None
            if pub_m:
                try:
                    dt = parsedate_to_datetime(pub_m.group(1).strip())
                    pub_date = dt.replace(tzinfo=None) if dt.tzinfo else dt
                except (TypeError, ValueError):
                    pub_date = None

            thumb = None
            desc_m = re.search(r"<description>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</description>", item, re.DOTALL)
            if desc_m:
                img_m = re.search(r'<img[^>]+src="([^"]+)"', desc_m.group(1))
                if img_m:
                    thumb = img_m.group(1)

            stubs.append(ArticleStub(
                url=url,
                title=title,
                source_site=self.config.domain,
                source_category=category,
                thumbnail_url=thumb,
                published_date=pub_date,
            ))
        return stubs

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        return None

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("h1.content-detail-title, h1.article-title, h1")
        title = title_el.get_text(strip=True) if title_el else stub.title

        date_el = soup.select_one("span.bread-crumb-detail__time, div.bread-crumb-detail span, time")
        pub_date = None
        if date_el:
            dt_attr = date_el.get("datetime")
            pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author_el = soup.select_one("span.author-name, p.author-name, span.article-author")
        author = author_el.get_text(strip=True) if author_el else None

        body = soup.select_one("div.maincontent, div.content-detail-body, div.ArticleContent")
        content_html = str(body) if body else ""

        return Article(
            url=stub.url,
            title=title,
            source_site=self.config.domain,
            source_category=stub.source_category,
            published_date=pub_date,
            content_html=content_html,
            content_text="",
            author=author,
        )

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        body = soup.select_one("div.maincontent, div.content-detail-body")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

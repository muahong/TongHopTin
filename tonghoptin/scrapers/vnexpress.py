"""VnExpress scraper.

Uses VnExpress's RSS feeds for listing discovery. RSS items carry a reliable
<pubDate>, which lets the base class drop stubs outside the target date before
fetching detail pages -- historically the dominant cost for this site.
"""

from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from typing import Optional

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date, to_vn_naive


@register_scraper("vnexpress.net")
class VnExpressScraper(BaseScraper):

    # (RSS feed path, display category)
    RSS_FEEDS = [
        ("/rss/thoi-su.rss", "Thời sự"),
        ("/rss/the-gioi.rss", "Thế giới"),
        ("/rss/kinh-doanh.rss", "Kinh doanh"),
        ("/rss/giai-tri.rss", "Giải trí"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/phap-luat.rss", "Pháp luật"),
        ("/rss/giao-duc.rss", "Giáo dục"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
        ("/rss/doi-song.rss", "Đời sống"),
        ("/rss/khoa-hoc-cong-nghe.rss", "Khoa học"),
        ("/rss/so-hoa.rss", "Số hóa"),
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
                    pub_date = to_vn_naive(dt)
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

        title_el = soup.select_one("h1.title-detail")
        title = title_el.get_text(strip=True) if title_el else stub.title

        date_el = soup.select_one("span.date")
        pub_date = None
        if date_el:
            pub_date = parse_vietnamese_date(date_el.get_text())
        if not pub_date and stub.published_date:
            pub_date = stub.published_date
        if not pub_date:
            from tonghoptin.vietnamese import now_vn
            pub_date = now_vn()

        author_el = soup.select_one("p.author_mail strong, span.author, p.Normal[style*='right'] strong")
        author = author_el.get_text(strip=True) if author_el else None

        body = soup.select_one("article.fck_detail")
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
        body = soup.select_one("article.fck_detail")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

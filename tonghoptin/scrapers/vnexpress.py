"""VnExpress scraper."""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("vnexpress.net")
class VnExpressScraper(BaseScraper):

    CATEGORIES = [
        ("/thoi-su", "Thời sự"),
        ("/the-gioi", "Thế giới"),
        ("/kinh-doanh", "Kinh doanh"),
        ("/giai-tri", "Giải trí"),
        ("/the-thao", "Thể thao"),
        ("/phap-luat", "Pháp luật"),
        ("/giao-duc", "Giáo dục"),
        ("/suc-khoe", "Sức khỏe"),
        ("/doi-song", "Đời sống"),
        ("/khoa-hoc", "Khoa học"),
        ("/so-hoa", "Số hóa"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        for article in soup.select("article.item-news"):
            link = article.select_one("h3.title-news a, h2.title-news a")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get_text(strip=True)
            if not url or not title:
                continue

            # Make URL absolute
            if url.startswith("/"):
                url = self.config.base_url + url

            # Try to parse date from listing
            date_el = article.select_one("span.time-public, span.date, span.time")
            pub_date = None
            if date_el:
                pub_date = parse_vietnamese_date(date_el.get_text())

            # Thumbnail
            thumb = None
            img = article.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("src")

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
        # VnExpress pagination: /thoi-su -> /thoi-su-p2 -> /thoi-su-p3
        match = re.search(r"-p(\d+)$", current_url)
        if match:
            current_page = int(match.group(1))
            next_page = current_page + 1
            return re.sub(r"-p\d+$", f"-p{next_page}", current_url)
        else:
            return current_url + "-p2"

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        # Title
        title_el = soup.select_one("h1.title-detail")
        title = title_el.get_text(strip=True) if title_el else stub.title

        # Date
        date_el = soup.select_one("span.date")
        pub_date = None
        if date_el:
            pub_date = parse_vietnamese_date(date_el.get_text())
        if not pub_date and stub.published_date:
            pub_date = stub.published_date
        if not pub_date:
            from datetime import datetime
            pub_date = datetime.now()

        # Author
        author_el = soup.select_one("p.author_mail strong, span.author, p.Normal[style*='right'] strong")
        author = author_el.get_text(strip=True) if author_el else None

        # Content body
        body = soup.select_one("article.fck_detail")
        content_html = str(body) if body else ""

        return Article(
            url=stub.url,
            title=title,
            source_site=self.config.domain,
            source_category=stub.source_category,
            published_date=pub_date,
            content_html=content_html,
            content_text="",  # Will be set by cleaner
            author=author,
        )

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        # Try og:image meta tag first
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        # Try first image in article body
        body = soup.select_one("article.fck_detail")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

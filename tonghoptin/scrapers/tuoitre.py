"""Tuoi Tre Online scraper."""

from __future__ import annotations

import re
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("tuoitre.vn")
class TuoiTreScraper(BaseScraper):

    CATEGORIES = [
        ("/thoi-su.htm", "Thời sự"),
        ("/the-gioi.htm", "Thế giới"),
        ("/phap-luat.htm", "Pháp luật"),
        ("/kinh-doanh.htm", "Kinh doanh"),
        ("/nhip-song-so.htm", "Công nghệ"),
        ("/xe.htm", "Xe"),
        ("/nhip-song-tre.htm", "Nhịp sống trẻ"),
        ("/van-hoa.htm", "Văn hóa"),
        ("/giai-tri.htm", "Giải trí"),
        ("/the-thao.htm", "Thể thao"),
        ("/giao-duc.htm", "Giáo dục"),
        ("/khoa-hoc.htm", "Khoa học"),
        ("/suc-khoe.htm", "Sức khỏe"),
        ("/du-lich.htm", "Du lịch"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        # Tuoi Tre uses box-category-item for article cards
        for item in soup.select("li.news-item, div.box-category-item, article"):
            link = item.select_one("a.box-category-link-title, h3 a, h2 a, a[title]")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get("title", "") or link.get_text(strip=True)
            if not url or not title:
                continue

            if url.startswith("/"):
                url = self.config.base_url + url

            # Skip non-article links
            if not re.search(r"\d{8,}", url) and ".htm" not in url:
                continue

            date_el = item.select_one("span.time, span.date, time")
            pub_date = None
            if date_el:
                dt_attr = date_el.get("datetime")
                pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())

            thumb = None
            img = item.select_one("img")
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
        # tuoitre.vn/thoi-su.htm -> tuoitre.vn/thoi-su/trang-2.htm
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one("a.page-next, a[rel='next'], li.next a")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if href.startswith("/"):
                return self.config.base_url + href
            return href

        # Manual page increment
        match = re.search(r"trang-(\d+)", current_url)
        if match:
            page = int(match.group(1)) + 1
            return re.sub(r"trang-\d+", f"trang-{page}", current_url)
        else:
            # First page -> page 2
            base = current_url.replace(".htm", "")
            return f"{base}/trang-2.htm"

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("h1.article-title, h1.detail-title, h1")
        title = title_el.get_text(strip=True) if title_el else stub.title

        date_el = soup.select_one("div.detail-time span, span.date-time, time.detail-time")
        pub_date = None
        if date_el:
            dt_attr = date_el.get("datetime")
            pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author_el = soup.select_one("div.author-info span.name, span.author, div.detail-author")
        author = author_el.get_text(strip=True) if author_el else None

        body = soup.select_one("div#main-detail-body, div.detail-content, div.content-detail")
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
        body = soup.select_one("div#main-detail-body, div.detail-content")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

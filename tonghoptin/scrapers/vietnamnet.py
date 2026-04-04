"""VietnamNet scraper (parses embedded JSON from script tags)."""

from __future__ import annotations

import json
import re
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("vietnamnet.vn")
class VietnamNetScraper(BaseScraper):

    CATEGORIES = [
        ("/thoi-su", "Thời sự"),
        ("/chinh-tri", "Chính trị"),
        ("/the-gioi", "Thế giới"),
        ("/kinh-doanh", "Kinh doanh"),
        ("/giao-duc", "Giáo dục"),
        ("/doi-song", "Đời sống"),
        ("/suc-khoe", "Sức khỏe"),
        ("/giai-tri", "Giải trí"),
        ("/the-thao", "Thể thao"),
        ("/cong-nghe", "Công nghệ"),
        ("/oto-xe-may", "Ô tô - Xe máy"),
        ("/bat-dong-san", "Bất động sản"),
        ("/du-lich", "Du lịch"),
        ("/phap-luat", "Pháp luật"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        # Method 1: Try parsing embedded JSON data from Countly.q.push()
        stubs.extend(self._parse_from_json(html, category))

        # Method 2: Parse from DOM if JSON didn't yield results
        if not stubs:
            stubs.extend(self._parse_from_dom(soup, category))

        return stubs

    def _parse_from_json(self, html: str, category: str) -> list[ArticleStub]:
        """Parse article data embedded in JavaScript."""
        stubs = []
        # Look for JSON article data in script blocks
        for match in re.finditer(r'"detailUrl"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]*)"', html):
            url = match.group(1)
            title = match.group(2)
            if url.startswith("/"):
                url = self.config.base_url + url
            if title and url:
                stubs.append(ArticleStub(
                    url=url,
                    title=title,
                    source_site=self.config.domain,
                    source_category=category,
                ))
        return stubs

    def _parse_from_dom(self, soup: BeautifulSoup, category: str) -> list[ArticleStub]:
        """Parse articles from DOM elements."""
        stubs = []
        for item in soup.select("div.horizontalPost, div.verticalPost, article, div.item-news"):
            link = item.select_one("a.vnn-title, h3 a, h2 a, a[title]")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get("title", "") or link.get_text(strip=True)
            if not url or not title:
                continue

            if url.startswith("/"):
                url = self.config.base_url + url

            date_el = item.select_one("span.time, time, span.date")
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
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one("a.next-page, a[rel='next'], a.btn-loadmore")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if href.startswith("/"):
                return self.config.base_url + href
            return href

        match = re.search(r"[?&]page=(\d+)", current_url)
        if match:
            page = int(match.group(1)) + 1
            return re.sub(r"page=\d+", f"page={page}", current_url)
        else:
            sep = "&" if "?" in current_url else "?"
            return f"{current_url}{sep}page=2"

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

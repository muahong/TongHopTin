"""VietnamBusinessInsider.vn scraper - Vietnamese business analysis."""

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


@register_scraper("vietnambusinessinsider.vn")
class VietnamBusinessInsiderScraper(BaseScraper):

    CATEGORIES = [
        ("/tin-tuc/noi-bat", "Nổi bật"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        for item in soup.select(".item-news, .item-news-common, .box-news, article"):
            link = item.select_one(".title a, h3 a, h2 a, a[title]")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get("title", "") or link.get_text(strip=True)
            if not url or not title or len(title) < 10:
                continue

            if url.startswith("/"):
                url = self.config.base_url + url
            if not url.endswith(".html"):
                continue

            date_el = item.select_one(".meta-news time, span.time, time")
            pub_date = None
            if date_el:
                dt_attr = date_el.get("datetime")
                pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())

            thumb = None
            img = item.select_one(".thumb-art img, img")
            if img:
                thumb = img.get("data-src") or img.get("src")

            stubs.append(ArticleStub(
                url=url, title=title, source_site=self.config.domain,
                source_category=category, thumbnail_url=thumb, published_date=pub_date,
            ))

        return stubs

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one("a[rel='next'], .pagination a.next")
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
        jsonld = self._parse_jsonld(soup)

        title = (jsonld.get("headline") if jsonld else None) or stub.title
        if not jsonld:
            title_el = soup.select_one("h1, .article-title")
            if title_el:
                title = title_el.get_text(strip=True)

        pub_date = None
        if jsonld and jsonld.get("datePublished"):
            pub_date = parse_vietnamese_date(jsonld["datePublished"])
        if not pub_date:
            date_el = soup.select_one("time, .meta-news .date, span.date")
            if date_el:
                pub_date = parse_vietnamese_date(date_el.get("datetime", "") or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author = None
        if jsonld and jsonld.get("author"):
            a = jsonld["author"]
            author = a.get("name") if isinstance(a, dict) else str(a)
        if not author:
            author_el = soup.select_one(".author-meta, .author-name")
            if author_el:
                author = author_el.get_text(strip=True)

        body = soup.select_one(".the-article-body, .post-content, .detail-content")
        content_html = str(body) if body else ""

        return Article(
            url=stub.url, title=title, source_site=self.config.domain,
            source_category=stub.source_category, published_date=pub_date,
            content_html=content_html, content_text="", author=author,
        )

    def _parse_jsonld(self, soup: BeautifulSoup) -> Optional[dict]:
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") in ("NewsArticle", "Article"):
                            return item
                elif data.get("@type") in ("NewsArticle", "Article"):
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        # Try JSON-LD image first
        jsonld = self._parse_jsonld(soup)
        if jsonld and jsonld.get("image"):
            img = jsonld["image"]
            if isinstance(img, dict):
                return img.get("url")
            elif isinstance(img, str):
                return img
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        return None

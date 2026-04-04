"""VietnamBusinessInsider.vn scraper - Vietnamese business analysis."""

from __future__ import annotations

import json
import re
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("vietnambusinessinsider.vn")
class VietnamBusinessInsiderScraper(BaseScraper):

    # Use homepage - the site is small and homepage shows all recent articles
    CATEGORIES = [
        ("", "Nổi bật"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []
        seen_urls = set()

        # VBI uses .box-news containers and also standalone links
        # Find all links that match the article URL pattern: /{slug}-a{id}.html
        for link in soup.find_all("a", href=True):
            url = link.get("href", "")
            if not url:
                continue

            # Make absolute
            if url.startswith("/"):
                url = self.config.base_url + url

            # Must match article URL pattern: ends with -a{digits}.html
            if not re.search(r"-a\d+\.html$", url):
                continue

            # Must be same domain
            if urlparse(url).netloc != self.config.domain:
                continue

            # Deduplicate
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get title from link text or title attribute
            title = link.get("title", "") or link.get_text(strip=True)
            if not title or len(title) < 10:
                # Try parent element's title
                parent = link.parent
                if parent:
                    title_el = parent.select_one(".title, h3, h2")
                    if title_el:
                        title = title_el.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # Try to find image
            thumb = None
            img = link.select_one("img")
            if not img and link.parent:
                img = link.parent.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("src")

            stubs.append(ArticleStub(
                url=url, title=title, source_site=self.config.domain,
                source_category=category, thumbnail_url=thumb, published_date=None,
            ))

        return stubs

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        # Small site - homepage only, no pagination
        return None

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
            # Try meta tag
            meta = soup.select_one('meta[property="article:published_time"]')
            if meta and meta.get("content"):
                pub_date = parse_vietnamese_date(meta["content"])
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
            author_el = soup.select_one(".author-meta, .author-name, .post-author")
            if author_el:
                author = author_el.get_text(strip=True)

        body = soup.select_one(".the-article-body, .post-content, .detail-content, .entry-content, article")
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
                        if item.get("@type") in ("NewsArticle", "Article", "BlogPosting"):
                            return item
                elif data.get("@type") in ("NewsArticle", "Article", "BlogPosting"):
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
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

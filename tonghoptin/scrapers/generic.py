"""Generic fallback scraper using readability-lxml for unknown sites."""

from __future__ import annotations

import re
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


class GenericScraper(BaseScraper):
    """Best-effort scraper for sites without a dedicated scraper class.

    Uses homepage link analysis for discovery and readability-lxml for extraction.
    No pagination support - homepage only.
    """

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(self.config.base_url, "Trang chủ")]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []
        seen_urls = set()
        base_domain = urlparse(self.config.base_url).netloc

        for link in soup.find_all("a", href=True):
            url = link["href"]
            title = link.get("title", "") or link.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            # Make absolute
            if url.startswith("/"):
                url = urljoin(self.config.base_url, url)
            elif not url.startswith("http"):
                continue

            # Must be same domain
            if urlparse(url).netloc != base_domain:
                continue

            # Heuristic: article URLs usually have path segments with dates or long slugs
            path = urlparse(url).path
            if not self._looks_like_article_url(path):
                continue

            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Try to find date near the link
            parent = link.parent
            date_el = parent.find("time") if parent else None
            pub_date = None
            if date_el:
                dt_attr = date_el.get("datetime")
                pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())

            stubs.append(ArticleStub(
                url=url,
                title=title,
                source_site=self.config.domain,
                source_category=category,
                published_date=pub_date,
            ))

        return stubs

    def _looks_like_article_url(self, path: str) -> bool:
        """Heuristic: article URLs usually have date patterns or long slugs."""
        # Contains date-like patterns: /2026/04/04/ or /20260404/
        if re.search(r"/\d{4}/\d{2}/", path):
            return True
        # Has a long slug (multiple words separated by hyphens)
        segments = path.strip("/").split("/")
        if segments:
            last = segments[-1]
            if last.count("-") >= 3 and len(last) > 20:
                return True
        # Ends in common article extensions
        if re.search(r"\.(html?|htm|php|aspx)$", path):
            if len(path) > 20:
                return True
        return False

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        # No pagination for generic scraper
        return None

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        """Use readability-lxml for generic article extraction."""
        from readability import Document

        doc = Document(html)
        title = doc.short_title() or stub.title
        content_html = doc.summary()

        # Parse date from original HTML
        soup = BeautifulSoup(html, "lxml")
        pub_date = self._extract_date(soup)
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        # Author from meta tags
        author = None
        author_meta = soup.select_one('meta[name="author"], meta[property="article:author"]')
        if author_meta:
            author = author_meta.get("content")

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

    def _extract_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Try multiple strategies to find article publication date."""
        # 1. <meta property="article:published_time">
        meta = soup.select_one('meta[property="article:published_time"]')
        if meta and meta.get("content"):
            dt = parse_vietnamese_date(meta["content"])
            if dt:
                return dt

        # 2. <time datetime="...">
        time_el = soup.select_one("time[datetime]")
        if time_el:
            dt = parse_vietnamese_date(time_el["datetime"])
            if dt:
                return dt

        # 3. Any <time> element
        time_el = soup.select_one("time")
        if time_el:
            dt = parse_vietnamese_date(time_el.get_text())
            if dt:
                return dt

        return None

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        return None

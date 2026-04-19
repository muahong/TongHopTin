"""Shared RSS-based scraper base class.

Most modern Vietnamese news sites expose per-category RSS feeds with a reliable
<pubDate>. Subclasses only need to declare RSS_FEEDS and a handful of detail-page
selectors; listing-parse, pagination, and detail extraction are handled here.
"""

from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from typing import Optional

from datetime import datetime

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import now_vn, parse_vietnamese_date, to_vn_naive


def parse_rss_pubdate(raw: str) -> Optional[datetime]:
    """Parse an RSS <pubDate> into a naive GMT+7 wall-clock datetime.

    Normalizes malformed TZ offsets before handing to email.utils:
      "+07"     → parsed as +00:07 (seven minutes!) - rewrite to +0700
      "+07:00"  → parsed as naive (silently dropped) - rewrite to +0700
    """
    normalized = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", raw)
    normalized = re.sub(r"([+-]\d{2})$", r"\g<1>00", normalized)
    try:
        dt = parsedate_to_datetime(normalized)
        return to_vn_naive(dt) if dt else None
    except (TypeError, ValueError):
        return None


class BaseRssScraper(BaseScraper):
    """RSS-driven listing + HTML detail scraper.

    Subclasses set:
      RSS_FEEDS: list[(path, category_name)] relative to base_url
      DETAIL_TITLE_SELECTOR, DETAIL_BODY_SELECTOR: required for extraction
      DETAIL_DATE_SELECTOR, DETAIL_AUTHOR_SELECTOR: optional refinement

    Override _parse_pub_date for feeds with non-RFC-2822 date strings.
    """

    RSS_FEEDS: list[tuple[str, str]] = []
    DETAIL_TITLE_SELECTOR: str = "h1"
    DETAIL_DATE_SELECTOR: str = "time[datetime], time, span.date, span.time"
    DETAIL_BODY_SELECTOR: str = "article, div.detail-content, div.content-detail, div.article-content"
    DETAIL_AUTHOR_SELECTOR: str = 'meta[name="author"]'

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

            pub_date = self._parse_pub_date(pub_m.group(1).strip()) if pub_m else None

            thumb = None
            desc_m = re.search(
                r"<description>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</description>",
                item, re.DOTALL,
            )
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

    def _parse_pub_date(self, raw: str) -> Optional[datetime]:
        return parse_rss_pubdate(raw)

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        return None

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one(self.DETAIL_TITLE_SELECTOR)
        title = title_el.get_text(strip=True) if title_el else stub.title

        pub_date = None
        date_el = soup.select_one(self.DETAIL_DATE_SELECTOR)
        if date_el:
            dt_attr = date_el.get("datetime") if date_el.name == "time" else None
            pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or now_vn()

        author = None
        author_el = soup.select_one(self.DETAIL_AUTHOR_SELECTOR)
        if author_el:
            author = (
                author_el.get("content") if author_el.name == "meta"
                else author_el.get_text(strip=True)
            )

        body = soup.select_one(self.DETAIL_BODY_SELECTOR)
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
        body = soup.select_one(self.DETAIL_BODY_SELECTOR)
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

"""CafeBiz.vn scraper - Vietnamese business news."""

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


@register_scraper("cafebiz.vn")
class CafeBizScraper(BaseScraper):

    CATEGORIES = [
        ("/cau-chuyen-kinh-doanh.chn", "Kinh doanh"),
        ("/cong-nghe.chn", "Công nghệ"),
        ("/vi-mo.chn", "Vĩ mô"),
        ("/bizmoney.chn", "Bizmoney"),
        ("/xa-hoi.chn", "Xã hội"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        for item in soup.select(".listtimeline ul li, .cfbiznews_box, .item-news"):
            link = item.select_one("h3 a, .cfbiznews_title a, h2 a, a[title]")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get("title", "") or link.get_text(strip=True)
            if not url or not title or len(title) < 10:
                continue

            if url.startswith("/"):
                url = self.config.base_url + url
            if not url.endswith(".chn"):
                continue

            date_el = item.select_one("span.time, .time, span.date")
            pub_date = None
            if date_el:
                pub_date = parse_vietnamese_date(date_el.get_text())

            thumb = None
            img = item.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("src")

            stubs.append(ArticleStub(
                url=url, title=title, source_site=self.config.domain,
                source_category=category, thumbnail_url=thumb, published_date=pub_date,
            ))

        return stubs

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one(".page ul li.next a, a[rel='next']")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if href.startswith("/"):
                return self.config.base_url + href
            return href
        match = re.search(r"/trang-(\d+)", current_url)
        if match:
            page = int(match.group(1)) + 1
            return re.sub(r"/trang-\d+", f"/trang-{page}", current_url)
        else:
            base = current_url.replace(".chn", "")
            return f"{base}/trang-2.chn"

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")
        jsonld = self._parse_jsonld(soup)

        title = (jsonld.get("headline") if jsonld else None) or stub.title
        if not jsonld:
            title_el = soup.select_one("h1")
            if title_el:
                title = title_el.get_text(strip=True)

        pub_date = None
        if jsonld and jsonld.get("datePublished"):
            pub_date = parse_vietnamese_date(jsonld["datePublished"])
        if not pub_date:
            date_el = soup.select_one(".pdate, time, .detail-time")
            if date_el:
                pub_date = parse_vietnamese_date(date_el.get("datetime", "") or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author = None
        if jsonld and jsonld.get("author"):
            a = jsonld["author"]
            author = a.get("name") if isinstance(a, dict) else str(a)

        body = soup.select_one(".detail-content, #cbnewscontent, .newscontent")
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
                        if item.get("@type") == "NewsArticle":
                            return item
                elif data.get("@type") == "NewsArticle":
                    return data
            except (json.JSONDecodeError, AttributeError):
                continue
        return None

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        return None

"""Thanh Nien scraper."""

from __future__ import annotations

import re
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("thanhnien.vn")
class ThanhNienScraper(BaseScraper):

    # Note: thanhnien.vn category pages use .htm, not .html.
    # The .html variants 301-redirect to tag pages with a different layout.
    CATEGORIES = [
        ("/thoi-su.htm", "Thời sự"),
        ("/the-gioi.htm", "Thế giới"),
        ("/kinh-te.htm", "Kinh tế"),
        ("/doi-song.htm", "Đời sống"),
        ("/suc-khoe.htm", "Sức khỏe"),
        ("/gioi-tre.htm", "Giới trẻ"),
        ("/giao-duc.htm", "Giáo dục"),
        ("/du-lich.htm", "Du lịch"),
        ("/van-hoa.htm", "Văn hóa"),
        ("/giai-tri.htm", "Giải trí"),
        ("/the-thao.htm", "Thể thao"),
        ("/cong-nghe.htm", "Công nghệ"),
        ("/xe.htm", "Xe"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        for item in soup.select("div.box-category-item, article.story, div.story"):
            link = item.select_one("a.box-category-link-title, h3 a, h2 a, a[data-vr-headline]")
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
        next_link = soup.select_one("div.layout__pagination a.next, a[rel='next']")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if href.startswith("/"):
                return self.config.base_url + href
            return href

        # Manual: ?page=N
        match = re.search(r"[?&]page=(\d+)", current_url)
        if match:
            page = int(match.group(1)) + 1
            return re.sub(r"page=\d+", f"page={page}", current_url)
        else:
            sep = "&" if "?" in current_url else "?"
            return f"{current_url}{sep}page=2"

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one(
            "h1.detail-title, h1.detail__title, h1.article-title, h1"
        )
        title = title_el.get_text(strip=True) if title_el else stub.title

        # Prefer ISO timestamp from <meta property="article:published_time">,
        # then on-page Vietnamese-formatted div.detail-time text.
        pub_date = None
        meta_time = soup.select_one('meta[property="article:published_time"]')
        if meta_time and meta_time.get("content"):
            pub_date = parse_vietnamese_date(meta_time["content"])
        if not pub_date:
            date_el = soup.select_one(
                "div.detail-time, div.detail__meta time, span.detail-time, div.detail__date"
            )
            if date_el:
                dt_attr = date_el.get("datetime")
                pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author_el = soup.select_one(
            "div.detail-author, div.author-info, "
            "div.detail__author a, span.author, div.detail__source"
        )
        author = author_el.get_text(strip=True) if author_el else None

        body = soup.select_one(
            "div.detail-content.afcbc-body, div.detail-content, "
            "div.detail__content, div.content-detail, article.detail"
        )
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
        body = soup.select_one(
            "div.detail-content.afcbc-body, div.detail-content, div.detail__content"
        )
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("src")
        return None

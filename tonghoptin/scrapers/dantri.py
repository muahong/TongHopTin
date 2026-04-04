"""Dan Tri scraper (uses Playwright for JS-heavy rendering)."""

from __future__ import annotations

import re
from typing import Optional
from datetime import datetime

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import parse_vietnamese_date


@register_scraper("dantri.com.vn")
class DanTriScraper(BaseScraper):

    CATEGORIES = [
        ("/xa-hoi.htm", "Xã hội"),
        ("/the-gioi.htm", "Thế giới"),
        ("/kinh-doanh.htm", "Kinh doanh"),
        ("/bat-dong-san.htm", "Bất động sản"),
        ("/the-thao.htm", "Thể thao"),
        ("/lao-dong-viec-lam.htm", "Lao động - Việc làm"),
        ("/tam-long-nhan-ai.htm", "Tâm lòng nhân ái"),
        ("/suc-khoe.htm", "Sức khỏe"),
        ("/giao-duc.htm", "Giáo dục"),
        ("/an-sinh.htm", "An sinh"),
        ("/phap-luat.htm", "Pháp luật"),
        ("/doi-song.htm", "Đời sống"),
        ("/van-hoa.htm", "Văn hóa"),
        ("/giai-tri.htm", "Giải trí"),
        ("/suc-manh-so.htm", "Sức mạnh số"),
        ("/o-to-xe-may.htm", "Ô tô - Xe máy"),
        ("/du-lich.htm", "Du lịch"),
    ]

    def get_category_urls(self) -> list[tuple[str, str]]:
        return [(f"{self.config.base_url}{path}", name) for path, name in self.CATEGORIES]

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        soup = BeautifulSoup(html, "lxml")
        stubs = []

        # Dan Tri article items
        for item in soup.select("article, div.article-item, h3.article-title"):
            # Find the link
            if item.name == "h3":
                link = item.select_one("a")
            else:
                link = item.select_one("h3 a, h2 a, a.article-title, a[data-type='title']")
            if not link:
                continue

            url = link.get("href", "")
            title = link.get("title", "") or link.get_text(strip=True)
            if not url or not title:
                continue

            if url.startswith("/"):
                url = self.config.base_url + url

            # Skip non-article links
            if not url.endswith(".htm"):
                continue

            date_el = item.select_one("time, span.date, span.time")
            pub_date = None
            if date_el:
                dt_attr = date_el.get("datetime")
                pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())

            thumb = None
            img = item.select_one("img")
            if img:
                thumb = img.get("data-src") or img.get("data-original") or img.get("src")

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
        # Dan Tri: /xa-hoi.htm -> /xa-hoi/trang-2.htm
        soup = BeautifulSoup(html, "lxml")
        next_link = soup.select_one("a.page-item.next, a[rel='next']")
        if next_link and next_link.get("href"):
            href = next_link["href"]
            if href.startswith("/"):
                return self.config.base_url + href
            return href

        match = re.search(r"trang-(\d+)", current_url)
        if match:
            page = int(match.group(1)) + 1
            return re.sub(r"trang-\d+", f"trang-{page}", current_url)
        else:
            base = current_url.replace(".htm", "")
            return f"{base}/trang-2.htm"

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("h1.title-page, h1.article-title, h1")
        title = title_el.get_text(strip=True) if title_el else stub.title

        date_el = soup.select_one("time.author-time, span.author-time, time")
        pub_date = None
        if date_el:
            dt_attr = date_el.get("datetime")
            pub_date = parse_vietnamese_date(dt_attr or date_el.get_text())
        if not pub_date:
            pub_date = stub.published_date or datetime.now()

        author_el = soup.select_one("span.author-name, b.author-name, span.author")
        author = author_el.get_text(strip=True) if author_el else None

        body = soup.select_one("div.singular-content, div.detail-content, article.singular-container")
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
        body = soup.select_one("div.singular-content, div.detail-content")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("data-original") or img.get("src")
        return None

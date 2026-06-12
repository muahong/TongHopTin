"""Dan Tri scraper - RSS-based.

Dan Tri exposes per-category RSS feeds with reliable <pubDate>, so neither
listings nor details need a browser. (The old HTML listing pages were
JS-rendered and required Playwright.) Dan Tri URLs also embed the publish
timestamp (``...-YYYYMMDDHHMMSSsss.htm``), used as a date fallback.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from tonghoptin.models import Article, ArticleStub
from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper
from tonghoptin.vietnamese import now_vn


_URL_TIMESTAMP_RE = re.compile(r"-(\d{14,17})\.htm(?:l)?(?:$|[?#])")


def _date_from_dantri_url(url: str) -> Optional[datetime]:
    """Extract the publish datetime embedded in a Dan Tri article URL.

    Dan Tri URLs end with ``-YYYYMMDDHHMMSSsss.htm``; the first 14 digits
    are a local (GMT+7) timestamp.
    """
    m = _URL_TIMESTAMP_RE.search(url)
    if not m:
        return None
    s = m.group(1)[:14]
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S")
    except ValueError:
        return None


@register_scraper("dantri.com.vn")
class DanTriScraper(BaseRssScraper):

    RSS_FEEDS = [
        ("/rss/home.rss", "Trang chủ"),
        ("/rss/xa-hoi.rss", "Xã hội"),
        ("/rss/the-gioi.rss", "Thế giới"),
        ("/rss/kinh-doanh.rss", "Kinh doanh"),
        ("/rss/bat-dong-san.rss", "Bất động sản"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/lao-dong-viec-lam.rss", "Lao động - Việc làm"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
        ("/rss/giao-duc.rss", "Giáo dục"),
        ("/rss/an-sinh.rss", "An sinh"),
        ("/rss/phap-luat.rss", "Pháp luật"),
        ("/rss/doi-song.rss", "Đời sống"),
        ("/rss/van-hoa.rss", "Văn hóa"),
        ("/rss/giai-tri.rss", "Giải trí"),
        ("/rss/suc-manh-so.rss", "Sức mạnh số"),
        ("/rss/o-to-xe-may.rss", "Ô tô - Xe máy"),
        ("/rss/du-lich.rss", "Du lịch"),
    ]

    DETAIL_TITLE_SELECTOR = "h1.title-page, h1.article-title, h1"
    DETAIL_DATE_SELECTOR = "time.author-time, span.author-time, time"
    # Legacy layouts. The 2026 redesign uses Tailwind-style utility classes
    # with no stable body class -- handled by _extract_redesign_body().
    DETAIL_BODY_SELECTOR = (
        'div.singular-content, div.e-magazine__body, div.dnews__body, '
        'div.detail-content, [itemprop="articleBody"]'
    )
    DETAIL_AUTHOR_SELECTOR = "span.author-name, b.author-name, span.author"

    @staticmethod
    def _extract_redesign_body(soup: BeautifulSoup) -> str:
        """Body extraction for the 2026 dantri redesign.

        Structure: <article class="dt-flex ..."> with children h1 (title),
        meta div, h2 (lede), and an unclassed div holding the paragraphs.
        The body div has no stable class, so take the direct child div with
        the most text.
        """
        h1 = soup.find("h1")
        art = h1.find_parent("article") if h1 else None
        if art is None:
            return ""
        parts = []
        lede = art.find("h2", recursive=False)
        if lede is not None:
            lede_text = lede.get_text(" ", strip=True)
            if lede_text:
                parts.append(f"<p><strong>{lede_text}</strong></p>")
        body, body_len = None, 0
        for child in art.find_all("div", recursive=False):
            n = len(child.get_text(strip=True))
            if n > body_len:
                body, body_len = child, n
        if body is not None and body_len > 100:
            parts.append(str(body))
        return "".join(parts) if body is not None else ""

    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        stubs = super().parse_article_listing(html, category)
        for stub in stubs:
            if stub.published_date is None:
                stub.published_date = _date_from_dantri_url(stub.url)
        return stubs

    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        article = super().parse_article_detail(html, stub)
        if not article.content_html:
            soup = BeautifulSoup(html, "lxml")
            article.content_html = self._extract_redesign_body(soup)
        # Prefer the URL-embedded timestamp when the page date is missing or
        # was defaulted to "now".
        if article.published_date is None or (
            stub.published_date is None
            and abs((article.published_date - now_vn()).total_seconds()) < 60
        ):
            url_date = _date_from_dantri_url(stub.url)
            if url_date:
                article.published_date = url_date
        return article

    def extract_hero_image_url(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        og = soup.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            return og["content"]
        body = soup.select_one("div.singular-content, div.detail-content, div.dt-font-arial")
        if body:
            img = body.select_one("img")
            if img:
                return img.get("data-src") or img.get("data-original") or img.get("src")
        return None

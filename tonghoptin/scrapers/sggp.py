"""Sai Gon Giai Phong scraper (sggp.org.vn) - RSS-based."""

from __future__ import annotations

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("sggp.org.vn", "www.sggp.org.vn")
class SggpScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/home.rss", "Trang chủ"),
        ("/rss/chinhtri-1.rss", "Chính trị"),
        ("/rss/kinhte-9.rss", "Kinh tế"),
        ("/rss/xahoi-42.rss", "Xã hội"),
        ("/rss/phapluat-8.rss", "Pháp luật"),
        ("/rss/quocte-2.rss", "Quốc tế"),
        ("/rss/thethao-10.rss", "Thể thao"),
        ("/rss/giaoduc-6.rss", "Giáo dục"),
        ("/rss/vanhoa-11.rss", "Văn hóa"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article__title, h1.detail-title, h1"
    DETAIL_DATE_SELECTOR = "time[datetime], div.article__meta time, span.date, time"
    DETAIL_BODY_SELECTOR = "div.article__body, div.article-content, div.detail-content, article"
    DETAIL_AUTHOR_SELECTOR = "div.article__author, span.author-info, meta[name='author']"

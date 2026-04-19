"""Tien Phong scraper (tienphong.vn) - RSS-based."""

from __future__ import annotations

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("tienphong.vn")
class TienPhongScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/home.rss", "Trang chủ"),
        ("/rss/xa-hoi-2.rss", "Xã hội"),
        ("/rss/the-gioi-5.rss", "Thế giới"),
        ("/rss/kinh-te-3.rss", "Kinh tế"),
        ("/rss/phap-luat-12.rss", "Pháp luật"),
        ("/rss/the-thao-7.rss", "Thể thao"),
        ("/rss/giao-duc-9.rss", "Giáo dục"),
        ("/rss/suc-khoe-55.rss", "Sức khỏe"),
        ("/rss/cong-nghe-110.rss", "Công nghệ"),
        ("/rss/giai-tri-6.rss", "Giải trí"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article__title, h1.article-title, h1"
    DETAIL_DATE_SELECTOR = "div.article__meta time, time[datetime], time"
    DETAIL_BODY_SELECTOR = "div.article__body, div.article-content, article"
    DETAIL_AUTHOR_SELECTOR = "div.article__author, span.article-author, meta[name='author']"

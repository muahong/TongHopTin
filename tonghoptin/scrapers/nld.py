"""Nguoi Lao Dong scraper (nld.com.vn) - RSS-based."""

from __future__ import annotations

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("nld.com.vn")
class NldScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/home.rss", "Trang chủ"),
        ("/rss/thoi-su.rss", "Thời sự"),
        ("/rss/kinh-te.rss", "Kinh tế"),
        ("/rss/quoc-te.rss", "Quốc tế"),
        ("/rss/phap-luat.rss", "Pháp luật"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
        ("/rss/giao-duc-khoa-hoc.rss", "Giáo dục - Khoa học"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/giai-tri.rss", "Giải trí"),
        ("/rss/van-hoa-van-nghe.rss", "Văn hóa"),
        ("/rss/lao-dong.rss", "Lao động"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article-title, h1.title-detail, h1"
    DETAIL_DATE_SELECTOR = "time[datetime], span.time, div.post-time, time"
    DETAIL_BODY_SELECTOR = "div.detail-content, div.article-content, div#ContentDetail, article"
    DETAIL_AUTHOR_SELECTOR = "div.author, span.author, p.author, meta[name='author']"

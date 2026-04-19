"""Nhan Dan scraper (nhandan.vn) - RSS-based."""

from __future__ import annotations

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("nhandan.vn")
class NhanDanScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/trangchu.rss", "Trang chủ"),
        ("/rss/chinhtri.rss", "Chính trị"),
        ("/rss/kinhte.rss", "Kinh tế"),
        ("/rss/xahoi.rss", "Xã hội"),
        ("/rss/phapluat.rss", "Pháp luật"),
        ("/rss/quocte.rss", "Quốc tế"),
        ("/rss/thethao.rss", "Thể thao"),
        ("/rss/giaoduc.rss", "Giáo dục"),
        ("/rss/ykien.rss", "Ý kiến"),
        ("/rss/vanhoa.rss", "Văn hóa"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article__title, h1.detail__title, h1"
    DETAIL_DATE_SELECTOR = "time.article__publish, time[datetime], span.box-date, time"
    DETAIL_BODY_SELECTOR = "div.article__body, div.detail-content, div.article-content, article"
    DETAIL_AUTHOR_SELECTOR = "div.article__author, span.article-author, meta[name='author']"

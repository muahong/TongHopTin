"""Vietnam Plus scraper (vietnamplus.vn) - RSS-based."""

from __future__ import annotations

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


@register_scraper("vietnamplus.vn", "www.vietnamplus.vn")
class VietnamPlusScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss/tin-moi-nhat.rss", "Mới nhất"),
        ("/rss/chinh-tri.rss", "Chính trị"),
        ("/rss/kinh-te.rss", "Kinh tế"),
        ("/rss/xa-hoi.rss", "Xã hội"),
        ("/rss/the-gioi.rss", "Thế giới"),
        ("/rss/van-hoa.rss", "Văn hóa"),
        ("/rss/the-thao.rss", "Thể thao"),
        ("/rss/cong-nghe.rss", "Công nghệ"),
        ("/rss/giao-duc.rss", "Giáo dục"),
        ("/rss/suc-khoe.rss", "Sức khỏe"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.article__title, h1.cms-title, h1"
    DETAIL_DATE_SELECTOR = "time[datetime], span.publish-date, div.publish-date, time"
    DETAIL_BODY_SELECTOR = "div.article__body, div.cms-body, div.article-body, article"
    DETAIL_AUTHOR_SELECTOR = "div.article__author, span.author-name, meta[name='author']"

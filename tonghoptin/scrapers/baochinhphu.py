"""Bao Chinh Phu scraper (baochinhphu.vn) - RSS-based.

baochinhphu.vn emits pubDates in US-locale format (e.g. "4/19/2026 11:04:00 AM"),
which email.utils.parsedate_to_datetime cannot parse, so we override _parse_pub_date.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from tonghoptin.scrapers import register_scraper
from tonghoptin.scrapers.rss_base import BaseRssScraper


_PUBDATE_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)?$",
    re.IGNORECASE,
)


@register_scraper("baochinhphu.vn")
class BaoChinhPhuScraper(BaseRssScraper):
    RSS_FEEDS = [
        ("/rss", "Mới nhất"),
    ]
    DETAIL_TITLE_SELECTOR = "h1.detail-title, h1.article-title, h1"
    DETAIL_DATE_SELECTOR = "time[datetime], div.detail-time, span.date, time"
    DETAIL_BODY_SELECTOR = "div.detail-content, div.article-content, div#abody, article"
    DETAIL_AUTHOR_SELECTOR = "div.detail-author, span.author, meta[name='author']"

    def _parse_pub_date(self, raw: str) -> Optional[datetime]:
        m = _PUBDATE_RE.match(raw.strip())
        if not m:
            return super()._parse_pub_date(raw)
        month, day, year, hour, minute, second, ampm = m.groups()
        h = int(hour)
        if ampm:
            if ampm.upper() == "PM" and h != 12:
                h += 12
            elif ampm.upper() == "AM" and h == 12:
                h = 0
        try:
            return datetime(int(year), int(month), int(day), h, int(minute), int(second))
        except ValueError:
            return None

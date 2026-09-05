"""Extract publication evidence without substituting crawl or update time."""
import json
import re
from bs4 import BeautifulSoup
from tonghoptin.vietnamese import parse_vietnamese_date


def publication_date(html):
    soup = BeautifulSoup(html.split("</head>", 1)[0], "lxml")
    for selector in ('meta[property="article:published_time"]', 'meta[itemprop="datePublished"]', 'meta[name="pubdate"]', 'meta[name="pub_date"]', 'meta[name="dc.date.issued"]'):
        element = soup.select_one(selector)
        if element:
            parsed = parse_vietnamese_date(element.get("content", ""))
            if parsed:
                return parsed
    def visit(value):
        if isinstance(value, dict):
            if value.get("datePublished"):
                parsed = parse_vietnamese_date(str(value["datePublished"]))
                if parsed:
                    return parsed
            for nested in value.values():
                parsed = visit(nested)
                if parsed:
                    return parsed
        if isinstance(value, list):
            for nested in value:
                parsed = visit(nested)
                if parsed:
                    return parsed
        return None
    for element in re.finditer(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            parsed = visit(json.loads(element.group(1)))
            if parsed:
                return parsed
        except (ValueError, TypeError, RecursionError):
            continue
    return None

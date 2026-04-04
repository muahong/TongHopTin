"""HTML content cleaning pipeline."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


REMOVE_TAGS = frozenset({
    "script", "style", "iframe", "form", "nav", "aside", "footer",
    "header", "noscript", "svg", "button", "input", "select", "textarea",
})

# CSS selectors for common clutter elements
CLUTTER_SELECTORS = [
    ".related", ".related-news", ".box-related",
    ".social-share", ".social-plugin", ".share-buttons",
    ".ads", ".ad", ".advertisement", "[class*='quangcao']",
    ".comment", ".comments", "#comments",
    ".author-info", ".author-box",
    ".breadcrumb", ".breadcrumbs",
    ".banner", "[class*='banner']",
    ".popup", ".modal",
    ".newsletter", ".subscribe",
    ".tags-container",
]

ALLOWED_ATTRS = frozenset({"src", "href", "alt", "title"})


class ContentCleaner:
    """Cleans raw article HTML for embedding in the digest.

    Pipeline:
    1. Remove unwanted tags (script, style, iframe, etc.)
    2. Remove site clutter (related articles, social widgets, ads)
    3. Normalize lazy-loaded images
    4. Strip non-whitelisted attributes
    5. Unwrap empty containers
    6. Convert relative URLs to absolute
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    def clean(self, html: str) -> tuple[str, str]:
        """Clean HTML and return (cleaned_html, plain_text)."""
        soup = BeautifulSoup(html, "lxml")

        self._remove_unwanted_tags(soup)
        self._remove_clutter(soup)
        self._normalize_images(soup)
        self._strip_attributes(soup)
        self._unwrap_empty(soup)
        self._absolutize_urls(soup)

        cleaned_html = str(soup)
        plain_text = soup.get_text(separator=" ", strip=True)
        # Normalize whitespace in plain text
        plain_text = re.sub(r"\s+", " ", plain_text).strip()

        return cleaned_html, plain_text

    def _remove_unwanted_tags(self, soup: BeautifulSoup) -> None:
        for tag_name in REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

    def _remove_clutter(self, soup: BeautifulSoup) -> None:
        for selector in CLUTTER_SELECTORS:
            for el in soup.select(selector):
                el.decompose()

    def _normalize_images(self, soup: BeautifulSoup) -> None:
        """Convert lazy-loaded data-src attributes to src."""
        for img in soup.find_all("img"):
            # Try common lazy-load attributes
            for attr in ("data-src", "data-original", "data-lazy-src"):
                if img.get(attr):
                    img["src"] = img[attr]
                    break

            # Remove tracking pixels (1x1 images)
            width = img.get("width", "")
            height = img.get("height", "")
            if width in ("1", "0") or height in ("1", "0"):
                img.decompose()

    def _strip_attributes(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(True):
            attrs_to_remove = [a for a in tag.attrs if a not in ALLOWED_ATTRS]
            for attr in attrs_to_remove:
                del tag[attr]

    def _unwrap_empty(self, soup: BeautifulSoup) -> None:
        """Remove empty divs, spans, and paragraphs."""
        for tag in soup.find_all(["div", "span", "p", "section"]):
            if not tag.get_text(strip=True) and not tag.find(["img", "video", "picture"]):
                tag.decompose()

    def _absolutize_urls(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(["a", "img"]):
            for attr in ("href", "src"):
                val = tag.get(attr, "")
                if val and not val.startswith(("http://", "https://", "data:", "#")):
                    tag[attr] = urljoin(self.base_url, val)

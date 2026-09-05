"""HTML content cleaning pipeline."""

from __future__ import annotations

import re
import hashlib
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag


REMOVE_TAGS = frozenset({
    "script", "style", "iframe", "form", "nav", "aside", "footer",
    "header", "noscript", "svg", "button", "input", "select", "textarea",
    "object", "embed", "base", "link", "meta", "math", "template",
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
SANITIZER_VERSION = 1
ALLOWED_TAGS = frozenset("p div span section article h1 h2 h3 h4 h5 h6 a img figure figcaption blockquote ul ol li table thead tbody tfoot tr th td br hr strong em b i u s sup sub pre code picture".split())


def is_sanitized(article):
    return article.sanitizer_version == SANITIZER_VERSION and article.sanitized_digest == hashlib.sha256(article.content_html.encode()).hexdigest()


def mark_sanitized(article):
    article.sanitizer_version = SANITIZER_VERSION
    article.sanitized_digest = hashlib.sha256(article.content_html.encode()).hexdigest()


def safe_url(value: str, base: str = "") -> str:
    """Only HTTP(S) publisher links; reject active schemes and credentials."""
    try:
        value = urljoin(base, value.strip())
        parts = urlsplit(value)
        if parts.scheme in ("http", "https") and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    return ""


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
        for tag in list(soup.find_all(True)):
            if tag.name not in ALLOWED_TAGS:
                tag.unwrap()

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
                if val:
                    clean = safe_url(val, self.base_url)
                    if clean:
                        tag[attr] = clean
                    else:
                        del tag[attr]

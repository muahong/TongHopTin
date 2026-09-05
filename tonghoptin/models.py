"""Data models for TongHopTin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FetchMethod(Enum):
    REQUESTS = "requests"
    PLAYWRIGHT = "playwright"


class CrawlStatus(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class ArticleStub:
    """Lightweight article reference discovered from listing pages."""
    url: str
    title: str
    source_site: str
    source_category: str
    thumbnail_url: Optional[str] = None
    published_date: Optional[datetime] = None


@dataclass
class Article:
    """Full article with extracted content."""
    url: str
    title: str
    source_site: str
    source_category: str
    published_date: Optional[datetime]
    content_html: str
    content_text: str
    author: Optional[str] = None
    hero_image_url: Optional[str] = None
    hero_image_path: Optional[str] = None  # local path relative to output dir
    estimated_reading_time_minutes: int = 0
    topics: list[str] = field(default_factory=list)
    interest_score: float = 0.0
    freshness_adjustment: float = 0.0
    final_score: float = 0.0
    is_new: bool = True
    sanitizer_version: int = 0
    sanitized_digest: str = ""
    scraped_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.content_text and self.estimated_reading_time_minutes == 0:
            # ~200 words/min; approximate Vietnamese by chars/1000
            self.estimated_reading_time_minutes = max(1, len(self.content_text) // 1000)

    @property
    def preview_text(self) -> str:
        """First 2-3 sentences for card preview."""
        text = self.content_text.strip()
        sentences = []
        for sep in [". ", "。", "! ", "? "]:
            if sep in text:
                parts = text.split(sep)
                return sep.join(parts[:3]) + sep.rstrip()
        # Fallback: first 300 chars
        return text[:300] + ("..." if len(text) > 300 else "")

    @property
    def url_hash(self) -> str:
        """Short hash of URL for dedup and image filenames."""
        import hashlib
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_cache_dict(self) -> dict:
        """Serialize content fields for the SQLite content cache.

        Topics and scores are cheap to recompute, so only fetched/cleaned
        content is persisted.
        """
        return {
            "url": self.url,
            "title": self.title,
            "source_site": self.source_site,
            "source_category": self.source_category,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "content_html": self.content_html,
            "content_text": self.content_text,
            "author": self.author,
            "hero_image_url": self.hero_image_url,
            "hero_image_path": self.hero_image_path,
            "scraped_at": self.scraped_at.isoformat(),
            "sanitizer_version": self.sanitizer_version,
            "sanitized_digest": self.sanitized_digest,
        }

    @classmethod
    def from_cache_dict(cls, data: dict) -> "Article":
        return cls(
            url=data["url"],
            title=data["title"],
            source_site=data["source_site"],
            source_category=data["source_category"],
            published_date=datetime.fromisoformat(data["published_date"]) if data.get("published_date") else None,
            content_html=data.get("content_html", ""),
            content_text=data.get("content_text", ""),
            author=data.get("author"),
            hero_image_url=data.get("hero_image_url"),
            hero_image_path=data.get("hero_image_path"),
            scraped_at=datetime.fromisoformat(data["scraped_at"]) if data.get("scraped_at") else datetime.min,
            sanitizer_version=data.get("sanitizer_version", 0),
            sanitized_digest=data.get("sanitized_digest", ""),
        )


@dataclass
class SiteCrawlResult:
    """Result from crawling one site."""
    site_name: str
    status: CrawlStatus
    articles: list[Article] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    stubs_discovered: int = 0
    stubs_filtered: int = 0
    duration_seconds: float = 0.0
    # Everything successfully parsed, including articles dropped by the date
    # filter. Cached so out-of-window stubs aren't re-fetched on every run.
    parsed_articles: list[Article] = field(default_factory=list)
    discovery: list[dict] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)


@dataclass
class SiteConfig:
    """Per-site configuration."""
    name: str
    base_url: str
    domain: str = ""
    enabled: bool = True
    fetch_method: FetchMethod = FetchMethod.REQUESTS
    request_delay: float = 1.0
    max_pages: int = 10
    max_concurrent: int = 5
    categories: list[str] = field(default_factory=list)
    sitemap_enabled: bool = True
    max_sitemaps: int = 12

    def __post_init__(self):
        if not 1 <= self.max_concurrent <= 16 or not 1 <= self.max_pages <= 100:
            raise ValueError("max_concurrent must be 1..16 and max_pages 1..100")
        if self.request_delay < 0.1 or not 1 <= self.max_sitemaps <= 100:
            raise ValueError("request_delay must be >= 0.1 and max_sitemaps 1..100")
        if not self.domain and self.base_url:
            from urllib.parse import urlparse
            self.domain = urlparse(self.base_url).netloc


@dataclass
class AppConfig:
    """Top-level application configuration."""
    # History
    chrome_history_path: str = ""
    brave_history_path: str = ""
    analysis_days: int = 30
    auto_detect_threshold: int = 5

    # Sites
    sites: list[SiteConfig] = field(default_factory=list)

    # Output
    output_directory: str = "./output"
    embed_images: bool = False  # False = separate folder
    image_max_width: int = 800
    theme: str = "auto"

    # Collection
    target_days: int = 1  # 1 = today only
    user_agent: str = "TongHopTin/1.0 (Vietnamese News Aggregator)"

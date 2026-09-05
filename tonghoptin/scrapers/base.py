"""Base scraper abstract class with crawl orchestration loop."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from typing import Optional

from tonghoptin.cleaning import ContentCleaner, is_sanitized, mark_sanitized
from tonghoptin.fetcher import Fetcher
from tonghoptin.discovery import discover_sitemaps, same_site
from tonghoptin.vietnamese import now_vn, to_vn_naive
from tonghoptin.models import (
    Article,
    ArticleStub,
    CrawlStatus,
    SiteConfig,
    SiteCrawlResult,
)

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base for all site scrapers.

    Subclasses MUST implement:
      - get_category_urls()
      - parse_article_listing()
      - get_next_page_url()
      - parse_article_detail()
      - extract_hero_image_url()

    The base class provides the crawl orchestration:
      1. For each category, paginate and collect ArticleStubs
      2. Filter stubs to target date
      3. Deduplicate by URL
      4. Fetch each article detail concurrently
      5. Return SiteCrawlResult
    """

    # Articles whose cleaned text is shorter than this are dropped: video and
    # podcast pages, photo-only posts, and extraction misses all land here.
    # Publishing them gives the reader an empty card.
    MIN_CONTENT_CHARS = 150

    def __init__(
        self,
        config: SiteConfig,
        fetcher: Fetcher,
        target_date: date,
        content_cache: Optional[dict[str, dict]] = None,
        start_date: Optional[date] = None,
    ):
        self.config = config
        self.discovery_domain = urlsplit(config.base_url).hostname or config.domain
        self.migrated_source = self.discovery_domain.removeprefix("www.") != config.domain.removeprefix("www.")
        self.fetcher = fetcher
        self.target_date = target_date
        # Use the exact inclusive Vietnam calendar window requested by the CLI.
        self.window_start = start_date or target_date
        self.content_cache = content_cache or {}
        self.cleaner = ContentCleaner(config.base_url)
        self.errors: list[dict] = []
        self.discovery: list[dict] = []
        self.outcomes: list[dict] = []
        self.completed_articles: list[Article] = []
        self.stubs_discovered = 0
        self._detail_tasks = {}
        self._detail_semaphore = asyncio.Semaphore(config.max_concurrent)
        self._parse_semaphore = getattr(fetcher, "parse_semaphore", asyncio.Semaphore(8))

    async def _parse(self, function, *args):
        async with self._parse_semaphore:
            return await asyncio.to_thread(function, *args)

    def _queue_stub(self, stub):
        if stub.url not in self._detail_tasks and self.in_scope(stub.url):
            self._detail_tasks[stub.url] = asyncio.create_task(self._fetch_article_with_semaphore(self._detail_semaphore, stub))
            self.stubs_discovered = len(self._detail_tasks)
        return self._detail_tasks.get(stub.url)

    def in_scope(self, url):
        return same_site(url, self.config.domain) or same_site(url, self.discovery_domain)

    @abstractmethod
    def get_category_urls(self) -> list[tuple[str, str]]:
        """Return list of (url, category_name) to start crawling."""
        ...

    @abstractmethod
    def parse_article_listing(self, html: str, category: str) -> list[ArticleStub]:
        """Parse a listing page and return ArticleStubs."""
        ...

    @abstractmethod
    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        """Return next page URL or None to stop pagination."""
        ...

    @abstractmethod
    def parse_article_detail(self, html: str, stub: ArticleStub) -> Article:
        """Parse a full article page into an Article object."""
        ...

    @abstractmethod
    def extract_hero_image_url(self, html: str) -> Optional[str]:
        """Extract the main article image URL."""
        ...

    def is_paywall(self, html: str) -> bool:
        """Override in subclasses to detect paywalls. Default: no paywall."""
        return False

    async def crawl(self) -> SiteCrawlResult:
        try:
            return await self._crawl()
        finally:
            for task in self._detail_tasks.values():
                if not task.done():
                    task.cancel()
            if self._detail_tasks:
                await asyncio.gather(*self._detail_tasks.values(), return_exceptions=True)

    async def _crawl(self) -> SiteCrawlResult:
        """Full crawl pipeline."""
        start = time.monotonic()
        all_stubs: list[ArticleStub] = []
        # A slow listing must not hide already discovered current-day news.
        if not self.migrated_source:
            for data in self.content_cache.values():
                try:
                    dt = datetime.fromisoformat(data["published_date"])
                    if data.get("source_site") == self.config.domain and self.window_start <= dt.date() <= self.target_date:
                        stub = ArticleStub(data["url"], data["title"], self.config.domain, data["source_category"], published_date=dt)
                        all_stubs.append(stub)
                        self._queue_stub(stub)
                except (KeyError, ValueError, TypeError):
                    continue

        categories = self.get_category_urls()
        if not any(url.rstrip("/") == self.config.base_url.rstrip("/") for url, _ in categories):
            categories.append((self.config.base_url, "Trang chủ"))
        logger.info(f"[{self.config.name}] Starting crawl: {len(categories)} categories")

        # Phase 1: Discover stubs from all categories
        listing_slots = asyncio.Semaphore(3)
        async def discover_category(cat_url, cat_name):
            async with listing_slots:
                try:
                    stubs = await self._discover_stubs_for_category(cat_url, cat_name)
                    for stub in stubs:
                        self._queue_stub(stub)
                    return stubs
                except Exception as e:
                    self._record_error(cat_url, e, "fetch_listing")
                    logger.error(f"[{self.config.name}] Category {cat_name} failed: {e}")
                    return []
        for stubs in await asyncio.gather(*(discover_category(url, name) for url, name in categories)):
            all_stubs.extend(stubs)

        if self.config.sitemap_enabled:
            all_stubs.extend(await discover_sitemaps(self))

        # Retain same-day stories discovered on earlier runs after feeds roll over.
        for data in self.content_cache.values():
            if self.migrated_source:
                continue  # legacy source URLs may now resolve to unrelated portal content
            if data.get("source_site") == self.config.domain:
                try:
                    dt = to_vn_naive(datetime.fromisoformat(data["published_date"]))
                    if self.window_start <= dt.date() <= self.target_date:
                        all_stubs.append(ArticleStub(data["url"], data["title"], self.config.domain, data["source_category"], published_date=dt))
                except (KeyError, ValueError, TypeError):
                    pass

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_stubs: list[ArticleStub] = []
        for stub in all_stubs:
            if not self.in_scope(stub.url):
                self.outcomes.append({"url": stub.url, "status": "offsite_rejected"})
                continue
            if stub.url not in seen_urls:
                seen_urls.add(stub.url)
                unique_stubs.append(stub)

        total_stubs = len(unique_stubs)
        self.stubs_discovered = total_stubs
        logger.info(f"[{self.config.name}] Discovered {total_stubs} unique stubs from {len(all_stubs)} total")

        # Phase 2: Fetch article details concurrently
        tasks = [self._queue_stub(stub) for stub in unique_stubs]
        results = await asyncio.gather(*tasks)
        articles = [a for a in results if a is not None]

        # Filter: confirm publish date from detail page falls in the window
        filtered = []
        for article in articles:
            if article.published_date and self.window_start <= to_vn_naive(article.published_date).date() <= self.target_date:
                filtered.append(article)
            else:
                self.outcomes.append({"url": article.url, "status": "outside_date_window"})

        duration = time.monotonic() - start
        status = CrawlStatus.SUCCESS if not self.errors else CrawlStatus.PARTIAL
        if not filtered or any(d.get("stop") in ("page_limit", "sitemap_limit", "failed", "unavailable") for d in self.discovery):
            status = CrawlStatus.PARTIAL
        if not filtered and self.errors:
            status = CrawlStatus.FAILED

        logger.info(
            f"[{self.config.name}] Done: {len(filtered)} articles, "
            f"{total_stubs - len(filtered)} filtered, {len(self.errors)} errors, "
            f"{duration:.1f}s"
        )

        return SiteCrawlResult(
            site_name=self.config.name,
            status=status,
            articles=filtered,
            errors=self.errors,
            stubs_discovered=total_stubs,
            stubs_filtered=total_stubs - len(filtered),
            duration_seconds=duration,
            parsed_articles=articles,
            discovery=self.discovery,
            outcomes=self.outcomes,
        )

    async def _discover_stubs_for_category(
        self, url: str, category: str
    ) -> list[ArticleStub]:
        """Paginate through a category, collecting stubs for target_date."""
        stubs: list[ArticleStub] = []
        current_url = url
        page = 0
        visited = set()

        while current_url and page < self.config.max_pages:
            if current_url in visited or not self.in_scope(current_url):
                self.discovery.append({"url": current_url, "stop": "loop_or_offsite"})
                break
            visited.add(current_url)
            logger.debug(f"[{self.config.name}] Fetching listing: {current_url}")
            html = await self.fetcher.fetch(
                current_url,
                method=self.config.fetch_method,
                delay=self.config.request_delay,
            )

            page_stubs = await self._parse(self.parse_article_listing, html, category)
            if not page_stubs and "<html" in html.lower():
                from tonghoptin.scrapers.generic import GenericScraper
                generic = GenericScraper(self.config, self.fetcher, self.target_date)
                page_stubs = await self._parse(generic.parse_article_listing, html, category)
            self.discovery.append({"url": current_url, "category": category, "count": len(page_stubs), "stop": "page_read"})
            if not page_stubs:
                self._record_error(current_url, ValueError("No article links found; listing may have changed"), "empty_listing")
                break

            # Categorize stubs by date
            today_stubs = []
            older_stubs = []
            unknown_stubs = []

            for stub in page_stubs:
                if stub.published_date is None:
                    unknown_stubs.append(stub)
                elif stub.published_date.date() >= self.window_start:
                    today_stubs.append(stub)
                else:
                    older_stubs.append(stub)

            stubs.extend(today_stubs)
            stubs.extend(unknown_stubs)  # Will be verified in detail fetch
            for stub in today_stubs + unknown_stubs:
                self._queue_stub(stub)

            # Stop if ALL stubs are older than target date
            if len(older_stubs) == len(page_stubs):
                logger.debug(f"[{self.config.name}] All stubs older than target, stopping pagination")
                break

            current_url = self.get_next_page_url(html, current_url)
            page += 1

        self.discovery.append({"url": url, "stop": "page_limit" if current_url and page >= self.config.max_pages else "listing_end"})

        return stubs

    async def _fetch_article_with_semaphore(
        self, semaphore: asyncio.Semaphore, stub: ArticleStub
    ) -> Optional[Article]:
        async with semaphore:
            return await self._fetch_and_parse_article(stub)

    def detail_fetch_method(self):
        """Which FetchMethod to use for article detail pages.

        Defaults to the site's configured method. Override when listing and
        detail pages need different tactics -- e.g. Dan Tri listings need
        Playwright but its detail pages are server-rendered plain HTML.
        """
        return self.config.fetch_method

    async def _fetch_and_parse_article(self, stub: ArticleStub) -> Optional[Article]:
        """Fetch detail page, parse article, download image."""
        # Cache hit: content was fetched and cleaned by an earlier run --
        # skip the network round-trip entirely. Thin entries (video pages,
        # extraction misses) are treated as misses so a live fetch gets a
        # chance to recover; if it comes back thin again it just won't be
        # published.
        fallback = None
        cached = None if self.migrated_source else self.content_cache.get(stub.url)
        if cached:
            try:
                article = Article.from_cache_dict(cached)
                if article.published_date and article.published_date.date() < self.window_start:
                    self.outcomes.append({"url": stub.url, "status": "cached_outside_date_window"})
                    return article
                if len(article.content_text.strip()) >= self.MIN_CONTENT_CHARS:
                    if not is_sanitized(article):
                        article.content_html, article.content_text = await self._parse(self.cleaner.clean, article.content_html)
                        mark_sanitized(article)
                    if article.published_date:
                        fallback = article
                    if fallback and (article.published_date.date() < self.window_start or
                            (now_vn() - to_vn_naive(article.scraped_at)).total_seconds() < 7200):
                        self.outcomes.append({"url": stub.url, "status": "cache_hit"})
                        self.completed_articles.append(article)
                        return article
            except (KeyError, ValueError):
                pass  # corrupt entry -- fall through to a live fetch

        try:
            html = await self.fetcher.fetch(
                stub.url,
                method=self.detail_fetch_method(),
                delay=self.config.request_delay,
            )
            final_url = getattr(self.fetcher, "final_urls", {}).get(stub.url, stub.url)
            if not self.in_scope(final_url):
                self._record_error(stub.url, ValueError(f"Publisher redirected to another domain: {final_url}"), "source_redirect")
                return None

            if self.is_paywall(html):
                self.outcomes.append({"url": stub.url, "status": "paywall"})
                logger.info(f"[{self.config.name}] Paywall detected: {stub.url}")
                return None

            article = await self._parse(self.parse_article_detail, html, stub)
            from tonghoptin.publication import publication_date
            article.published_date = await self._parse(publication_date, html) or article.published_date
            if article.published_date is None:
                self._record_error(stub.url, ValueError("Publication date unavailable; not assigned today's date"), "unknown_date")
                return None
            article.published_date = to_vn_naive(article.published_date)
            article.scraped_at = now_vn()

            # Clean content
            article.content_html, article.content_text = await self._parse(self.cleaner.clean,
                article.content_html
            )
            mark_sanitized(article)

            if len(article.content_text.strip()) < self.MIN_CONTENT_CHARS:
                self._record_error(stub.url, ValueError("Article body missing or too short"), "thin_content")
                logger.debug(
                    f"[{self.config.name}] Skipped (thin content, "
                    f"{len(article.content_text.strip())} chars): {stub.url}"
                )
                return None

            # Recalculate reading time now that content_text is set
            if article.content_text:
                article.estimated_reading_time_minutes = max(1, len(article.content_text) // 1000)

            # Extract and set hero image URL
            if not article.hero_image_url:
                article.hero_image_url = await self._parse(self.extract_hero_image_url, html)

            self.outcomes.append({"url": stub.url, "status": "parsed", "published_date": article.published_date.isoformat()})
            self.completed_articles.append(article)
            return article
        except Exception as e:
            self._record_error(stub.url, e, "fetch_detail")
            logger.error(f"[{self.config.name}] Article failed: {stub.url}: {e}")
            if fallback:
                self.outcomes.append({"url": stub.url, "status": "refresh_failed_cached_copy"})
                self.completed_articles.append(fallback)
                return fallback
            return None

    def _record_error(self, url: str, error: Exception, phase: str) -> None:
        self.errors.append({
            "url": url,
            "error": str(error) or type(error).__name__,
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
        })

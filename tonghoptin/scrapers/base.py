"""Base scraper abstract class with crawl orchestration loop."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from tonghoptin.cleaning import ContentCleaner
from tonghoptin.fetcher import Fetcher
from tonghoptin.models import (
    Article,
    ArticleStub,
    CrawlStatus,
    SiteConfig,
    SiteCrawlResult,
)
from tonghoptin.vietnamese import is_target_date, parse_vietnamese_date

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

    def __init__(self, config: SiteConfig, fetcher: Fetcher, target_date: date):
        self.config = config
        self.fetcher = fetcher
        self.target_date = target_date
        self.cleaner = ContentCleaner(config.base_url)
        self.errors: list[dict] = []

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
        """Full crawl pipeline."""
        start = time.monotonic()
        all_stubs: list[ArticleStub] = []

        categories = self.get_category_urls()
        logger.info(f"[{self.config.name}] Starting crawl: {len(categories)} categories")

        # Phase 1: Discover stubs from all categories
        for cat_url, cat_name in categories:
            try:
                stubs = await self._discover_stubs_for_category(cat_url, cat_name)
                all_stubs.extend(stubs)
            except Exception as e:
                self._record_error(cat_url, e, "fetch_listing")
                logger.error(f"[{self.config.name}] Category {cat_name} failed: {e}")

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique_stubs: list[ArticleStub] = []
        for stub in all_stubs:
            if stub.url not in seen_urls:
                seen_urls.add(stub.url)
                unique_stubs.append(stub)

        total_stubs = len(unique_stubs)
        logger.info(f"[{self.config.name}] Discovered {total_stubs} unique stubs from {len(all_stubs)} total")

        # Phase 2: Fetch article details concurrently
        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        tasks = [
            self._fetch_article_with_semaphore(semaphore, stub)
            for stub in unique_stubs
        ]
        results = await asyncio.gather(*tasks)
        articles = [a for a in results if a is not None]

        # Filter: confirm target date from detail page date
        filtered = []
        for article in articles:
            if article.published_date.date() == self.target_date:
                filtered.append(article)

        duration = time.monotonic() - start
        status = CrawlStatus.SUCCESS if not self.errors else CrawlStatus.PARTIAL
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
        )

    async def _discover_stubs_for_category(
        self, url: str, category: str
    ) -> list[ArticleStub]:
        """Paginate through a category, collecting stubs for target_date."""
        stubs: list[ArticleStub] = []
        current_url = url
        page = 0

        while current_url and page < self.config.max_pages:
            logger.debug(f"[{self.config.name}] Fetching listing: {current_url}")
            html = await self.fetcher.fetch(
                current_url,
                method=self.config.fetch_method,
                delay=self.config.request_delay,
            )

            page_stubs = self.parse_article_listing(html, category)
            if not page_stubs:
                break

            # Categorize stubs by date
            today_stubs = []
            older_stubs = []
            unknown_stubs = []

            for stub in page_stubs:
                result = is_target_date(stub.published_date, self.target_date)
                if result is True:
                    today_stubs.append(stub)
                elif result is False:
                    older_stubs.append(stub)
                else:
                    unknown_stubs.append(stub)

            stubs.extend(today_stubs)
            stubs.extend(unknown_stubs)  # Will be verified in detail fetch

            # Stop if ALL stubs are older than target date
            if len(older_stubs) == len(page_stubs):
                logger.debug(f"[{self.config.name}] All stubs older than target, stopping pagination")
                break

            current_url = self.get_next_page_url(html, current_url)
            page += 1

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
        try:
            html = await self.fetcher.fetch(
                stub.url,
                method=self.detail_fetch_method(),
                delay=self.config.request_delay,
            )

            if self.is_paywall(html):
                logger.info(f"[{self.config.name}] Paywall detected: {stub.url}")
                return None

            article = self.parse_article_detail(html, stub)

            # Clean content
            article.content_html, article.content_text = self.cleaner.clean(
                article.content_html
            )

            # Recalculate reading time now that content_text is set
            if article.content_text:
                article.estimated_reading_time_minutes = max(1, len(article.content_text) // 1000)

            # Extract and set hero image URL
            if not article.hero_image_url:
                article.hero_image_url = self.extract_hero_image_url(html)

            return article
        except Exception as e:
            self._record_error(stub.url, e, "fetch_detail")
            logger.error(f"[{self.config.name}] Article failed: {stub.url}: {e}")
            return None

    def _record_error(self, url: str, error: Exception, phase: str) -> None:
        self.errors.append({
            "url": url,
            "error": str(error),
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
        })

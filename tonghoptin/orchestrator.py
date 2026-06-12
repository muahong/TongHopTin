"""Crawl orchestrator - coordinates concurrent site crawling."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from tonghoptin.fetcher import Fetcher
from tonghoptin.models import (
    AppConfig,
    Article,
    CrawlStatus,
    SiteConfig,
    SiteCrawlResult,
)
from tonghoptin.scrapers import get_scraper_class
from tonghoptin.scrapers.base import BaseScraper
from tonghoptin.vietnamese import tag_article_topics, score_article, compute_freshness_adjustment, now_vn

logger = logging.getLogger(__name__)


class CrawlOrchestrator:
    """Coordinates crawling across all configured sites.

    - Sites are crawled concurrently via asyncio.gather
    - Per-site concurrency bounded by SiteConfig.max_concurrent
    - Rate limiting enforced per-domain in Fetcher
    - Results are deduplicated, tagged, and sorted
    """

    def __init__(
        self,
        config: AppConfig,
        target_date: Optional[date] = None,
        output_dir: Optional[Path] = None,
        timestamp_label: Optional[str] = None,
        content_cache: Optional[dict[str, dict]] = None,
    ):
        self.config = config
        self.target_date = target_date or date.today()
        self.output_dir = output_dir or Path(config.output_directory)
        self.timestamp_label = timestamp_label or now_vn().strftime("%Y-%m-%d_%H%M")
        # Shared images dir: hash-named files persist across runs, so images
        # for cached articles never need re-downloading.
        self.images_subdir = "images"
        self.content_cache = content_cache or {}
        self.fetcher = Fetcher(
            user_agent=config.user_agent,
            max_retries=3,
            timeout_seconds=30,
        )

    async def run(self) -> tuple[list[Article], list[SiteCrawlResult]]:
        """Run all site scrapers and return (articles, results)."""
        enabled_sites = [s for s in self.config.sites if s.enabled]
        if not enabled_sites:
            logger.warning("No enabled sites to crawl")
            return [], []

        logger.info(
            f"Starting crawl for {len(enabled_sites)} sites, "
            f"target date: {self.target_date}"
        )

        # Create scraper tasks
        tasks = []
        for site_cfg in enabled_sites:
            tasks.append(self._run_site(site_cfg))

        # Run all sites concurrently
        results: list[SiteCrawlResult] = await asyncio.gather(*tasks)

        # Collect all articles
        all_articles: list[Article] = []
        for result in results:
            self._log_site_result(result)
            all_articles.extend(result.articles)

        # Deduplicate across sites
        all_articles = self._deduplicate(all_articles)

        # Drop boilerplate: if several URLs from one site "extracted" the
        # same text (a footer or teaser list), none of them is an article.
        all_articles = self._drop_repeated_content(all_articles)

        # Apply topic tags, interest scores, and freshness
        for article in all_articles:
            article.topics = tag_article_topics(article.title, article.content_text)
            article.interest_score = score_article(article.title, article.content_text)
            article.freshness_adjustment = compute_freshness_adjustment(
                url=article.url,
                published_date=article.published_date,
                content_text=article.content_text,
            )
            article.final_score = round(article.interest_score + article.freshness_adjustment, 1)

        # Download hero images
        await self._download_images(all_articles)

        # Sort by final score descending, then by published_date descending
        all_articles.sort(key=lambda a: (a.final_score, a.published_date), reverse=True)

        await self.fetcher.close()

        # Print summary
        total_errors = sum(len(r.errors) for r in results)
        logger.info(
            f"Crawl complete: {len(all_articles)} articles, "
            f"{total_errors} errors across {len(results)} sites"
        )

        return all_articles, results

    async def _run_site(self, site_cfg: SiteConfig) -> SiteCrawlResult:
        """Run a single site scraper with error isolation."""
        try:
            scraper_cls = get_scraper_class(site_cfg.domain)
            scraper = scraper_cls(
                config=site_cfg,
                fetcher=self.fetcher,
                target_date=self.target_date,
                content_cache=self.content_cache,
            )
            return await scraper.crawl()
        except Exception as e:
            logger.error(f"Site {site_cfg.name} completely failed: {e}")
            return SiteCrawlResult(
                site_name=site_cfg.name,
                status=CrawlStatus.FAILED,
                articles=[],
                errors=[{
                    "url": site_cfg.base_url,
                    "error": str(e),
                    "phase": "site_crawl",
                    "timestamp": datetime.now().isoformat(),
                }],
            )

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Canonical form for cross-site URL dedup.

        Drops scheme, www prefix, query string (tracking params), fragment,
        and trailing slash, so e.g. http://www.x.vn/a/?utm=1 == https://x.vn/a
        """
        parts = urlsplit(url.strip())
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parts.path.rstrip("/")
        return f"{host}{path}".lower()

    @staticmethod
    def _drop_repeated_content(articles: list[Article]) -> list[Article]:
        """Remove same-site articles sharing identical extracted text.

        Three or more URLs with byte-identical content within one site means
        the extractor latched onto boilerplate (copyright footer, section
        teaser block), not article bodies.
        """
        from collections import Counter

        counts: Counter = Counter()
        for a in articles:
            if a.content_text:
                counts[(a.source_site, a.content_text[:1000])] += 1

        kept = []
        dropped = 0
        for a in articles:
            if a.content_text and counts[(a.source_site, a.content_text[:1000])] >= 3:
                dropped += 1
                continue
            kept.append(a)
        if dropped:
            logger.info(f"Dropped {dropped} boilerplate articles (repeated content)")
        return kept

    def _deduplicate(self, articles: list[Article]) -> list[Article]:
        """Remove duplicate articles by URL (normalized)."""
        seen: set[str] = set()
        unique: list[Article] = []
        for article in articles:
            url = self._normalize_url(article.url)
            if url not in seen:
                seen.add(url)
                unique.append(article)
        return unique

    async def _download_images(self, articles: list[Article]) -> None:
        """Download hero images for all articles (bounded concurrency)."""
        semaphore = asyncio.Semaphore(16)

        async def bounded(article: Article) -> None:
            async with semaphore:
                await self._download_article_image(article)

        tasks = [
            bounded(article)
            for article in articles
            if article.hero_image_url
        ]
        if tasks:
            await asyncio.gather(*tasks)

    async def _download_article_image(self, article: Article) -> None:
        """Download and save hero image for a single article."""
        if not article.hero_image_url:
            return
        path = await self.fetcher.download_image(
            url=article.hero_image_url,
            output_dir=self.output_dir,
            filename=article.url_hash,
            max_width=self.config.image_max_width,
            images_subdir=self.images_subdir,
        )
        article.hero_image_path = path

    def _log_site_result(self, result: SiteCrawlResult) -> None:
        status_emoji = {
            CrawlStatus.SUCCESS: "OK",
            CrawlStatus.PARTIAL: "PARTIAL",
            CrawlStatus.FAILED: "FAILED",
        }
        logger.info(
            f"  [{result.site_name}] {status_emoji.get(result.status, '?')} - "
            f"{len(result.articles)} articles, "
            f"{result.stubs_discovered} stubs, "
            f"{len(result.errors)} errors, "
            f"{result.duration_seconds:.1f}s"
        )

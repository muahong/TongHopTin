"""Async fetching layer with rate limiting, retries, and Playwright fallback."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from PIL import Image

from tonghoptin.models import FetchMethod

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


class Fetcher:
    """Unified async fetching layer.

    - Uses aiohttp for standard HTTP requests
    - Falls back to Playwright for JS-heavy sites
    - Enforces per-domain rate limiting and concurrency
    - Retries on transient errors with exponential backoff
    """

    def __init__(
        self,
        user_agent: str = "TongHopTin/1.0 (Vietnamese News Aggregator)",
        max_retries: int = 3,
        timeout_seconds: int = 30,
    ):
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._session: Optional[aiohttp.ClientSession] = None
        self._playwright = None
        self._browser = None
        self._last_request_time: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {**DEFAULT_HEADERS, "User-Agent": self.user_agent}
            self._session = aiohttp.ClientSession(headers=headers, timeout=self.timeout)
        return self._session

    async def _get_browser(self):
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    def _get_domain_lock(self, url: str) -> asyncio.Lock:
        domain = urlparse(url).netloc
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    async def _enforce_rate_limit(self, url: str, delay: float) -> None:
        domain = urlparse(url).netloc
        now = time.monotonic()
        last = self._last_request_time.get(domain, 0)
        wait = delay - (now - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_time[domain] = time.monotonic()

    async def fetch(
        self,
        url: str,
        method: FetchMethod = FetchMethod.REQUESTS,
        delay: float = 1.0,
    ) -> str:
        """Fetch URL and return HTML string.

        Retries on transient failures with exponential backoff.
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with self._get_domain_lock(url):
                    await self._enforce_rate_limit(url, delay)

                if method == FetchMethod.PLAYWRIGHT:
                    return await self._fetch_playwright(url)
                else:
                    return await self._fetch_aiohttp(url)
            except Exception as e:
                last_error = e
                status = getattr(e, "status", 0)
                # Only retry on transient errors
                if status in (429, 500, 502, 503, 504) or isinstance(e, (asyncio.TimeoutError, aiohttp.ClientConnectionError)):
                    wait = (2 ** attempt)
                    logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {url}: {e}. Waiting {wait}s")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise last_error  # type: ignore

    async def _fetch_aiohttp(self, url: str) -> str:
        session = await self._get_session()
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _fetch_playwright(self, url: str) -> str:
        browser = await self._get_browser()
        page = await browser.new_page(user_agent=self.user_agent)
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            return await page.content()
        finally:
            await page.close()

    async def download_image(
        self,
        url: str,
        output_dir: Path,
        filename: str,
        max_width: int = 800,
        images_subdir: str = "images",
    ) -> Optional[str]:
        """Download image, resize, save to output_dir/images_subdir/. Returns relative path or None.

        Uses Referer header spoofing to bypass CDN anti-hotlinking.
        Fails silently (no warning log) to reduce noise.
        """
        try:
            session = await self._get_session()
            # Spoof Referer to bypass CDN anti-hotlinking
            referer = urlparse(url)
            headers = {"Referer": f"{referer.scheme}://{referer.netloc}/"}
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                content_type = resp.content_type or ""
                if not content_type.startswith("image"):
                    return None
                data = await resp.read()

            if len(data) < 1000:  # Skip tiny/broken images
                return None

            img = Image.open(io.BytesIO(data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize if wider than max_width
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)

            images_dir = output_dir / images_subdir
            images_dir.mkdir(parents=True, exist_ok=True)

            filepath = images_dir / f"{filename}.jpg"
            img.save(filepath, "JPEG", quality=80, optimize=True)

            return f"{images_subdir}/{filename}.jpg"
        except Exception:
            # Silent failure — image placeholder will be used
            return None
            return None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

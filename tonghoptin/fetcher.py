"""Async fetching layer with rate limiting, retries, and Playwright fallback."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import ipaddress
import gzip
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin

import aiohttp
from PIL import Image

from tonghoptin.models import FetchMethod

logger = logging.getLogger(__name__)


def validate_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Only credential-free HTTP(S) URLs are allowed")
    if p.port not in (None, 80, 443):
        raise ValueError("Non-web ports are not allowed")
    try:
        addr = ipaddress.ip_address(p.hostname)
    except ValueError:
        if p.hostname.lower() == "localhost" or p.hostname.lower().endswith((".local", ".localhost", ".internal")):
            raise ValueError("Local network URL rejected")
    else:
        if not addr.is_global:
            raise ValueError("Non-public IP rejected")


class PublicResolver(aiohttp.resolver.DefaultResolver):
    async def resolve(self, host, port=0, family=0):
        addresses = await super().resolve(host, port, family)
        if any(not ipaddress.ip_address(item["host"]).is_global for item in addresses):
            raise ValueError("DNS resolved to a non-public address")
        return addresses

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
        self._browser_lock = asyncio.Lock()
        self._browser_slots = asyncio.Semaphore(4)
        self.parse_semaphore = asyncio.Semaphore(8)
        self.archive_dir = None
        self.final_urls = {}
        # Earliest time the next request for a domain is permitted to start.
        # Workers reserve a slot (monotonic value) without awaiting so
        # concurrent tasks space themselves out without serializing.
        self._next_request_time: dict[str, float] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {**DEFAULT_HEADERS, "User-Agent": self.user_agent}
            connector = aiohttp.TCPConnector(
                limit=64, limit_per_host=10, ttl_dns_cache=600, resolver=PublicResolver()
            )
            self._session = aiohttp.ClientSession(
                headers=headers, timeout=self.timeout, connector=connector
            )
        return self._session

    async def _get_browser(self):
        # Lock prevents a launch race: without it, a second task can observe
        # _playwright already set while _browser is still None and crash on
        # browser.new_page().
        async with self._browser_lock:
            if self._browser is None:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                try:
                    self._browser = await self._playwright.chromium.launch(headless=True)
                except BaseException:
                    await self._playwright.stop()
                    self._playwright = None
                    raise
        return self._browser

    async def _enforce_rate_limit(self, url: str, delay: float) -> None:
        """Reserve the next `delay`-second slot for this domain.

        Python asyncio is single-threaded: the read/write below is atomic across
        tasks, so no lock is needed. Each caller takes its own future slot and
        sleeps until that time, letting HTTP fetches run concurrently instead
        of serializing through one lock.
        """
        domain = urlparse(url).netloc
        now = time.monotonic()
        earliest = max(now, self._next_request_time.get(domain, 0.0))
        self._next_request_time[domain] = earliest + delay
        wait = earliest - now
        if wait > 0:
            await asyncio.sleep(wait)

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
        validate_url(url)
        for attempt in range(self.max_retries):
            try:
                await self._enforce_rate_limit(url, delay)

                if method == FetchMethod.PLAYWRIGHT:
                    async with self._browser_slots:
                        result = await self._fetch_playwright(url)
                else:
                    result = await self._fetch_aiohttp(url)
                if self.archive_dir:
                    await asyncio.to_thread(self._archive_response, url, result, method.value)
                return result
            except Exception as e:
                last_error = e
                status = getattr(e, "status", 0)
                # Only retry on transient errors
                # 428 is dantri's Varnish rate-limit response
                if status in (428, 429, 500, 502, 503, 504) or isinstance(e, (asyncio.TimeoutError, aiohttp.ClientConnectionError)):
                    if attempt + 1 >= self.max_retries:
                        break
                    wait = (2 ** attempt)
                    retry_after = (getattr(e, "headers", None) or {}).get("Retry-After", "")
                    if str(retry_after).isdigit():
                        wait = min(60, max(wait, int(retry_after)))
                    logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {url}: {e}. Waiting {wait}s")
                    await asyncio.sleep(wait)
                else:
                    raise
        raise last_error  # type: ignore

    async def _fetch_aiohttp(self, url: str) -> str:
        original_url = url
        session = await self._get_session()
        for _ in range(6):
            validate_url(url)
            async with session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    url = urljoin(url, resp.headers.get("Location", ""))
                    continue
                resp.raise_for_status()
                data = await self._read_limited(resp)
                self.final_urls[original_url] = str(resp.url)
                return data.decode(resp.charset or "utf-8", errors="replace")
        raise ValueError("Too many redirects")

    @staticmethod
    async def _read_limited(resp, limit=12 * 1024 * 1024):
        data = bytearray()
        async for chunk in resp.content.iter_chunked(65536):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("Response exceeds size limit")
        return bytes(data)

    def _archive_response(self, url, content, method):
        raw = content.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        folder = Path(self.archive_dir)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (digest + ".html.gz")
        if not target.exists():
            self._write_atomic(target, gzip.compress(raw, mtime=0))
        # Separate records avoid concurrent append races.
        record = {"url": url, "final_url": self.final_urls.get(url, url), "method": method, "captured_at": datetime.now(timezone.utc).isoformat(), "sha256": digest, "body": target.name}
        key = hashlib.sha256((url + record["captured_at"]).encode()).hexdigest()
        self._write_atomic(folder / (key + ".json"), json.dumps(record, ensure_ascii=False).encode("utf-8"))

    @staticmethod
    def _write_atomic(path, data):
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _fetch_playwright(self, url: str) -> str:
        browser = await self._get_browser()
        page = await browser.new_page(user_agent=self.user_agent)
        try:
            resolver = PublicResolver()
            checked = set()
            async def route_request(route):
                request = route.request
                try:
                    validate_url(request.url)
                    host = urlparse(request.url).hostname
                    if host not in checked:
                        await resolver.resolve(host, 443)
                        checked.add(host)
                    if request.resource_type in ("image", "media", "font"):
                        await route.abort()
                    else:
                        await route.continue_()
                except (ValueError, OSError):
                    await route.abort()
            await page.route("**/*", route_request)
            # "domcontentloaded" is 5-20x faster than "networkidle" and is
            # sufficient for server-rendered content. "networkidle" rarely
            # fires on ad-heavy pages and causes 30 s timeouts.
            response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if response and response.status >= 400:
                raise ValueError(f"Browser HTTP {response.status}")
            if "/tto-" in url:
                await page.mouse.wheel(0, 500)
                await page.wait_for_selector('#loadingPerHome a[href*=".htm"]', timeout=15000)
            content = await page.content()
            self.final_urls[url] = page.url
            await self._export_cookies(page, url)
            return content
        finally:
            try:
                await asyncio.wait_for(page.close(), timeout=5)
            except Exception as exc:
                logger.debug("Browser page cleanup: %s", exc)
            await resolver.close()

    async def _export_cookies(self, page, url: str) -> None:
        """Copy browser cookies into the aiohttp jar.

        Sites like laodong.vn guard URLs behind a JS cookie challenge that
        only a browser can solve. Once solved during the (Playwright) listing
        fetch, the cookie lets all detail pages go over plain aiohttp --
        ~10x faster than a browser round-trip per article.
        """
        try:
            validate_url(url)
            from http.cookies import SimpleCookie
            from yarl import URL

            cookies = await page.context.cookies()
            if not cookies:
                return
            jar = SimpleCookie()
            for c in cookies:
                name = c["name"]
                jar[name] = c["value"]
                # Without explicit domain/path the morsel doesn't survive
                # aiohttp's filter_cookies() matching.
                jar[name]["path"] = c.get("path") or "/"
                domain = (c.get("domain") or "").lstrip(".")
                if domain:
                    jar[name]["domain"] = domain
            session = await self._get_session()
            session.cookie_jar.update_cookies(jar, URL(url))
        except Exception:
            pass  # cookies are an optimization, never fatal

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
            validate_url(url)
            relative = f"{images_subdir}/{filename}.jpg"
            filepath = output_dir / images_subdir / f"{filename}.jpg"
            if filepath.exists():
                return relative

            session = await self._get_session()
            # Spoof Referer to bypass CDN anti-hotlinking
            referer = urlparse(url)
            headers = {"Referer": f"{referer.scheme}://{referer.netloc}/"}
            async with session.get(url, headers=headers, allow_redirects=False) as resp:
                if resp.status != 200:
                    return None
                content_type = resp.content_type or ""
                if not content_type.startswith("image"):
                    return None
                data = await self._read_limited(resp)

            if len(data) < 1000:  # Skip tiny/broken images
                return None

            # PIL decode/resize/encode is CPU-bound; run it off the event loop
            # so it doesn't stall concurrent fetches.
            await asyncio.to_thread(
                self._process_and_save_image, data, filepath, max_width
            )
            return relative
        except Exception:
            # Silent failure — image placeholder will be used
            return None

    @staticmethod
    def _process_and_save_image(data: bytes, filepath: Path, max_width: int) -> None:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > 25_000_000:
            raise ValueError("Image pixel limit exceeded")
        if img.mode != "RGB":
            img = img.convert("RGB")

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        filepath.parent.mkdir(parents=True, exist_ok=True)
        img.save(filepath, "JPEG", quality=78, optimize=True)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._browser:
            try:
                await asyncio.wait_for(self._browser.close(), timeout=10)
            except Exception as exc:
                logger.warning("Browser close did not finish: %s", type(exc).__name__)
        if self._playwright:
            try:
                await asyncio.wait_for(self._playwright.stop(), timeout=10)
            except Exception as exc:
                logger.warning("Browser driver stop did not finish: %s", type(exc).__name__)

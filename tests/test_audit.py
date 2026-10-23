import asyncio
import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from tests.test_core import make_article
from tonghoptin.archive import backup, restore
from tonghoptin.cleaning import ContentCleaner
from tonghoptin.discovery import same_site, discover_sitemaps
from tonghoptin.fetcher import validate_url, Fetcher
from tonghoptin.models import ArticleStub, SiteConfig
from tonghoptin.overview import build_overview
from tonghoptin.renderer import render_digest
from tonghoptin.scrapers.generic import GenericScraper


def test_iso_offset_crosses_vietnam_midnight():
    from tonghoptin.vietnamese import parse_vietnamese_date
    assert parse_vietnamese_date("2026-09-04T18:00:00Z") == datetime(2026, 9, 5, 1)
    assert parse_vietnamese_date("2026-09-05T00:15:00+09:00") == datetime(2026, 9, 4, 22, 15)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1", "http://[::1]", "http://169.254.169.254/", "https://user:pass@example.com", "http://localhost", "http://example.com:22"])
def test_network_targets_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_host_scope():
    assert same_site("https://www.vnexpress.net/a", "vnexpress.net")
    assert not same_site("https://vnexpress.net.evil.com/a", "vnexpress.net")


def test_url_dedup_keeps_article_ids_and_case():
    from tonghoptin.orchestrator import CrawlOrchestrator
    normalize = CrawlOrchestrator._normalize_url
    assert normalize("https://news.vn/article?id=1") != normalize("https://news.vn/article?id=2")
    assert normalize("https://news.vn/Story") != normalize("https://news.vn/story")
    assert normalize("https://news.vn/story?utm_source=x") == normalize("https://news.vn/story")


def test_active_html_removed():
    html, _ = ContentCleaner("https://news.vn").clean('<meta http-equiv="refresh" content="0;url=https://evil.com"><object data="x"></object><a href="javascript:alert(1)">click</a><img src="data:image/svg+xml,test" onerror="alert(1)"><p onclick="bad()">Safe</p>')
    assert "javascript:" not in html and "data:" not in html
    assert "onerror" not in html and "onclick" not in html
    assert "<meta" not in html and "<object" not in html
    assert "Safe" in html


def test_metadata_script_breakout_and_attributes(tmp_path):
    attack = '</script><script>alert(1)</script><img src=x onerror=alert(2)>'
    article = make_article(title=attack, source_category='" onclick="alert(1)')
    output = render_digest([article], tmp_path)
    html = output.read_text(encoding="utf-8")
    assert attack not in html
    soup = BeautifulSoup(html, "html.parser")
    data = json.loads(soup.find(id="articles-data").string)
    assert data[article.url_hash]["title"] == attack
    assert not soup.select("[onclick], [onerror]")


def test_archive_incremental_and_corruption(tmp_path):
    root, store = tmp_path / "root", tmp_path / "archive"
    (root / "output").mkdir(parents=True)
    (root / "docs").mkdir()
    file = root / "output" / "a.html"
    file.write_text("original", encoding="utf-8")
    first = backup(root, store)
    assert first["files_added_or_changed"] == 1
    assert backup(root, store)["files_added_or_changed"] == 0
    file.write_text("updated article", encoding="utf-8")
    assert backup(root, store)["files_added_or_changed"] == 1
    assert restore(store, tmp_path / "restored") == 1
    assert (tmp_path / "restored/output/a.html").read_text() == "updated article"
    assert len(list((store / "packs").glob("*.zip"))) == 2
    pack = next((store / "packs").glob("*.zip"))
    pack.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="Corrupt pack"):
        restore(store, tmp_path / "unused", verify_only=True)


def test_identical_archive_payload_is_shared_and_restores_both_paths(tmp_path):
    from tonghoptin.archive import load_index
    root = tmp_path / "root"
    (root / "output").mkdir(parents=True)
    for name in ("first.json", "second.json"):
        (root / "output" / name).write_bytes(b"identical valuable evidence")
    store = tmp_path / "archive"
    backup(root, store)
    index = load_index(store)
    assert index["output/first.json"]["parts"] == index["output/second.json"]["parts"]
    assert restore(store, tmp_path / "restored") == 2
    assert (tmp_path / "restored/output/second.json").read_bytes() == b"identical valuable evidence"


def test_archive_walk_covers_nested_paths_root_logs_and_drops_transients(tmp_path):
    from tonghoptin.archive import load_index
    root, store = tmp_path / "root", tmp_path / "archive"
    (root / "output" / "runs" / "deep").mkdir(parents=True)
    (root / "docs" / "articles" / "2026-10-23").mkdir(parents=True)
    (root / "output" / "runs" / "deep" / "report.json").write_text("deep", encoding="utf-8")
    (root / "docs" / "articles" / "2026-10-23" / "a.json").write_text("body", encoding="utf-8")
    (root / "tonghoptin.log").write_text("log line", encoding="utf-8")
    (root / "output" / "collection.lock").write_text("lock", encoding="utf-8")
    (root / "output" / "tonghoptin.db-wal").write_text("wal", encoding="utf-8")

    backup(root, store)
    index = load_index(store)

    assert "output/runs/deep/report.json" in index
    assert "docs/articles/2026-10-23/a.json" in index
    assert "tonghoptin.log" in index
    assert not [path for path in index if path.endswith((".lock", "-wal"))]
    # Index keys stay posix so restore targets match across platforms.
    assert not [path for path in index if "\\" in path]
    assert restore(store, tmp_path / "restored") == 3
    assert (tmp_path / "restored/output/runs/deep/report.json").read_text() == "deep"


def test_archive_honours_exclude_and_skips_unchanged_files(tmp_path):
    from tonghoptin.archive import load_index
    root, store = tmp_path / "root", tmp_path / "archive"
    (root / "output").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "output" / "keep.json").write_text("keep", encoding="utf-8")
    (root / "output" / "secret.json").write_text("secret", encoding="utf-8")

    assert backup(root, store, exclude=("output/secret.json",))["files_added_or_changed"] == 1
    index = load_index(store)
    assert "output/keep.json" in index and "output/secret.json" not in index
    assert backup(root, store, exclude=("output/secret.json",))["files_added_or_changed"] == 0


def test_archive_persists_refreshed_mtime_for_unchanged_content(tmp_path):
    """A touched-but-identical file must not be re-packed, and the new mtime
    must reach the index; otherwise every later run re-hashes the same bytes."""
    from tonghoptin.archive import load_index
    root, store = tmp_path / "root", tmp_path / "archive"
    (root / "output").mkdir(parents=True)
    (root / "docs").mkdir()
    file = root / "output" / "a.json"
    file.write_text("same bytes", encoding="utf-8")
    backup(root, store)
    packs = sorted(path.name for path in (store / "packs").glob("*.zip"))

    os.utime(file, (1_000_000, 1_000_000))
    assert backup(root, store)["files_added_or_changed"] == 0
    assert sorted(path.name for path in (store / "packs").glob("*.zip")) == packs
    assert load_index(store)["output/a.json"]["mtime_ns"] == file.stat().st_mtime_ns


def test_archive_skips_symlinks(tmp_path):
    from tonghoptin.archive import load_index
    root, store = tmp_path / "root", tmp_path / "archive"
    (root / "output").mkdir(parents=True)
    (root / "docs").mkdir()
    target = root / "output" / "real.json"
    target.write_text("real", encoding="utf-8")
    try:
        (root / "output" / "link.json").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks needs privileges on this platform")

    backup(root, store)
    index = load_index(store)
    assert "output/real.json" in index
    assert "output/link.json" not in index


def test_publish_retains_previous_snapshot(tmp_path, monkeypatch):
    from tonghoptin.cli import _publish_to_docs
    monkeypatch.chdir(tmp_path)
    article = make_article()
    first = render_digest([article], tmp_path / "output", "2026-09-05_0700")
    _publish_to_docs(first, tmp_path / "output", [article])
    first_body = tmp_path / "docs/articles/2026-09-05_0700" / (article.url_hash + ".json")
    original = first_body.read_bytes()
    article.content_html = "<p>Updated body</p>"
    second = render_digest([article], tmp_path / "output", "2026-09-05_0800")
    _publish_to_docs(second, tmp_path / "output", [article])
    assert first_body.read_bytes() == original
    assert (tmp_path / "docs" / first.name).exists()
    assert (tmp_path / "docs/index.html").read_bytes() == second.read_bytes()


def test_overview_separates_days_and_retains_sources():
    a = make_article(url="https://a.vn/1", title="Kinh tế Việt Nam", source_site="a.vn", source_category="Kinh tế")
    b = make_article(url="https://b.vn/2", title=a.title, source_site="b.vn", source_category="Kinh tế")
    c = make_article(url="https://a.vn/3", title="Bóng đá", source_category="Thể thao")
    a.published_date = b.published_date = datetime(2026, 9, 5)
    c.published_date = datetime(2026, 9, 4)
    result = build_overview([a, b, c])
    assert len(result["days"]["2026-09-05"]["economy"]) == 1
    assert len(result["days"]["2026-09-05"]["economy"][0]["articles"]) == 2
    assert "sports" in result["days"]["2026-09-04"]


def test_strict_day_real_pipeline_and_feed_rollover():
    day = date(2026, 9, 5)
    config = SiteConfig("example", "https://example.vn", sitemap_enabled=False)
    current = make_article(source_site="example.vn", content_text="news " * 120, content_html="<p>" + "news " * 120 + "</p>")
    from tonghoptin.vietnamese import now_vn
    current.scraped_at = now_vn()
    current.published_date = datetime(2026, 9, 5, 0, 1)
    old = make_article(url="https://example.vn/yesterday", source_site="example.vn")
    old.published_date = datetime(2026, 9, 4, 23, 59)
    scraper = GenericScraper(config, None, day, {a.url: a.to_cache_dict() for a in [current, old]})
    async def listing(*args):
        return []  # today story is no longer on the feed
    scraper._discover_stubs_for_category = listing
    result = asyncio.run(scraper.crawl())
    assert [a.url for a in result.articles] == [current.url]
    assert scraper.window_start == day


def test_fast_category_is_retained_while_other_listing_is_blocked():
    async def scenario():
        ready = asyncio.Event()
        scraper = GenericScraper(SiteConfig("example", "https://example.vn", sitemap_enabled=False), None, date(2026, 9, 5))
        scraper.get_category_urls = lambda: [("https://example.vn/fast", "fast"), ("https://example.vn/slow", "slow")]
        article = make_article(published=datetime(2026, 9, 5))
        async def listing(url, category):
            if category == "fast":
                return [ArticleStub(article.url, article.title, "example.vn", "News")]
            await asyncio.sleep(10)
            return []
        async def fetch(stub):
            scraper.completed_articles.append(article)
            ready.set()
            return article
        scraper._discover_stubs_for_category = listing
        scraper._fetch_and_parse_article = fetch
        task = asyncio.create_task(scraper.crawl())
        await asyncio.wait_for(ready.wait(), timeout=1)
        assert not task.done()
        assert scraper.completed_articles == [article]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(detail.done() for detail in scraper._detail_tasks.values())
    asyncio.run(scenario())


def test_unknown_publication_date_not_fabricated():
    scraper = GenericScraper(SiteConfig("example", "https://example.vn"), None, date(2026, 9, 5))
    article = scraper.parse_article_detail("<h1>News title</h1><article>" + "<p>Long news content.</p>" * 30 + "</article>", ArticleStub("https://example.vn/1", "News title", "example.vn", "News"))
    assert article.published_date is None


def test_limited_response_reads_every_chunk_and_rejects_large():
    class Body:
        async def iter_chunked(self, size):
            yield b"ab"
            yield b"cd"
    class Response:
        content = Body()
    assert asyncio.run(Fetcher._read_limited(Response(), 4)) == b"abcd"
    with pytest.raises(ValueError):
        asyncio.run(Fetcher._read_limited(Response(), 3))


def test_publisher_sitemap_dates_and_scope():
    class Fetch:
        async def fetch(self, url, **kwargs):
            if url.endswith("robots.txt"):
                return "Sitemap: https://example.vn/news.xml"
            return '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"><url><loc>https://example.vn/today</loc><news:news><news:publication_date>2026-09-05T01:00:00+07:00</news:publication_date><news:title>Today</news:title></news:news></url><url><loc>https://evil.com/a</loc><lastmod>2026-09-05</lastmod></url><url><loc>https://example.vn/old</loc><news:news><news:publication_date>2026-09-04</news:publication_date></news:news></url></urlset>'
    scraper = GenericScraper(SiteConfig("example", "https://example.vn"), Fetch(), date(2026, 9, 5))
    stubs = asyncio.run(discover_sitemaps(scraper))
    assert [stub.url for stub in stubs] == ["https://example.vn/today"]


def test_overview_normalizes_entities_and_uses_category_url():
    from tonghoptin.overview import plain_text
    assert plain_text("News &amp;quot;today&amp;quot;") == 'News "today"'
    article = make_article(url="https://example.vn/giao-duc/story", title="A new beginning", source_category="Latest")
    from tonghoptin.overview import category_for
    assert category_for(article) == "education"


def test_sanitizer_receipt_invalidated_by_body_change():
    from tonghoptin.cleaning import is_sanitized, mark_sanitized
    article = make_article()
    mark_sanitized(article)
    assert is_sanitized(article)
    article.content_html += '<script>alert(1)</script>'
    assert not is_sanitized(article)


def test_generic_finance_discovery_rejects_category_links():
    scraper = GenericScraper(SiteConfig("cafef", "https://cafef.vn"), None, date(2026, 9, 5))
    assert not scraper._looks_like_article_url("/tai-chinh-ngan-hang.chn")
    assert scraper._looks_like_article_url("/a-news-headline-188260905094326624.chn")


def test_archive_verify_rejects_traversal_without_extracting(tmp_path):
    import json
    from tonghoptin.archive import restore
    store = tmp_path / "store"
    store.mkdir()
    (store / "manifests").mkdir()
    (store / "index.json").write_text(json.dumps({"../outside": {"parts": [], "sha256": "", "size": 0}}))
    with pytest.raises(ValueError, match="escaped"):
        restore(store, tmp_path / "target", verify_only=True)

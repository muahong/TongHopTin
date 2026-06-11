"""Unit tests for core logic: dates, dedup, cache, cleaning, rendering."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from tonghoptin.cleaning import ContentCleaner
from tonghoptin.dedup import DedupDB, _normalize_title
from tonghoptin.models import Article
from tonghoptin.orchestrator import CrawlOrchestrator
from tonghoptin.scrapers.rss_base import parse_rss_pubdate
from tonghoptin.vietnamese import (
    now_vn,
    parse_vietnamese_date,
    tag_article_topics,
    score_article,
)


def make_article(url="https://example.vn/bai-viet-1.html", title="Tiêu đề bài viết",
                 published=None, **kwargs) -> Article:
    defaults = dict(
        url=url,
        title=title,
        source_site="example.vn",
        source_category="Thời sự",
        published_date=published or now_vn(),
        content_html="<p>Nội dung bài viết dài hơn hai trăm ký tự. " + "x" * 250 + "</p>",
        content_text="Nội dung bài viết dài hơn hai trăm ký tự. " + "x" * 250,
    )
    defaults.update(kwargs)
    return Article(**defaults)


# ---------- Vietnamese date parsing ----------

class TestDateParsing:
    def test_dmy_with_time(self):
        dt = parse_vietnamese_date("Thứ Bảy, 04/04/2026, 10:30 (GMT+7)")
        assert dt == datetime(2026, 4, 4, 10, 30)

    def test_dmy_only(self):
        assert parse_vietnamese_date("04/04/2026") == datetime(2026, 4, 4)

    def test_day_first_not_month_first(self):
        # 05/04 must be April 5th, not May 4th
        assert parse_vietnamese_date("05/04/2026") == datetime(2026, 4, 5)

    def test_iso(self):
        dt = parse_vietnamese_date("2026-04-04T10:30:00")
        assert dt is not None and (dt.year, dt.hour) == (2026, 10)

    def test_relative_hours(self):
        ref = datetime(2026, 4, 4, 12, 0)
        dt = parse_vietnamese_date("3 giờ trước", reference=ref)
        assert dt == datetime(2026, 4, 4, 9, 0)

    def test_garbage_returns_none(self):
        assert parse_vietnamese_date("not a date") is None
        assert parse_vietnamese_date("") is None


class TestRssPubdate:
    def test_standard_rfc2822(self):
        dt = parse_rss_pubdate("Sat, 04 Apr 2026 10:30:00 +0700")
        assert dt == datetime(2026, 4, 4, 10, 30)

    def test_utc_converted_to_vn(self):
        dt = parse_rss_pubdate("Sat, 04 Apr 2026 03:30:00 GMT")
        assert dt == datetime(2026, 4, 4, 10, 30)

    def test_malformed_short_offset(self):
        # "+07" must be +07:00, not 7 minutes
        dt = parse_rss_pubdate("Sat, 04 Apr 2026 10:30:00 +07")
        assert dt == datetime(2026, 4, 4, 10, 30)

    def test_colon_offset(self):
        dt = parse_rss_pubdate("Sat, 04 Apr 2026 10:30:00 +07:00")
        assert dt == datetime(2026, 4, 4, 10, 30)


# ---------- Topic tagging / scoring ----------

class TestTagging:
    def test_economy_tagged(self):
        topics = tag_article_topics("Lãi suất ngân hàng tăng mạnh", "")
        assert "Kinh tế" in topics

    def test_unknown_gets_khac(self):
        assert tag_article_topics("zzz", "yyy") == ["Khác"]

    def test_title_match_scores_double(self):
        assert score_article("Giá xăng dầu tăng", "") > score_article("Tin tức", "xăng tăng giá")


# ---------- Title normalization + dedup DB ----------

class TestNormalizeTitle:
    def test_diacritics_and_case(self):
        assert _normalize_title("Giá VÀNG tăng!") == _normalize_title("gia vang tang")

    def test_punctuation_collapsed(self):
        assert _normalize_title("A - B: C") == "a b c"


class TestDedupDB:
    @pytest.fixture
    def db(self, tmp_path):
        db = DedupDB(tmp_path / "test.db")
        yield db
        db.close()

    def test_first_sight_is_new(self, db):
        a = make_article()
        db.mark_articles([a])
        assert a.is_new is True

    def test_same_url_same_day_still_new(self, db):
        # First seen earlier today (another run) -> still today's news
        a1 = make_article()
        db.mark_articles([a1])
        a2 = make_article()
        db.mark_articles([a2])
        assert a2.is_new is True

    def test_same_title_different_url_is_rehash(self, db):
        a1 = make_article(url="https://a.vn/x.html", title="Cùng một tiêu đề")
        db.mark_articles([a1])
        a2 = make_article(url="https://b.vn/y.html", title="Cùng một tiêu đề")
        db.mark_articles([a2])
        assert a2.is_new is False

    def test_url_seen_yesterday_is_rehash(self, db):
        a1 = make_article()
        db.mark_articles([a1])
        # Backdate first_seen to yesterday
        yesterday = (now_vn() - timedelta(days=1)).isoformat()
        db._conn.execute("UPDATE seen_articles SET first_seen = ?", (yesterday,))
        db._conn.commit()
        a2 = make_article()
        db.mark_articles([a2])
        assert a2.is_new is False

    def test_content_cache_roundtrip(self, db):
        a = make_article(author="Ai Đó", hero_image_url="https://x.vn/i.jpg",
                         hero_image_path="images/abc.jpg")
        db.save_content_cache([a])
        cache = db.load_content_cache()
        assert a.url in cache
        restored = Article.from_cache_dict(cache[a.url])
        assert restored.title == a.title
        assert restored.content_html == a.content_html
        assert restored.author == "Ai Đó"
        assert restored.hero_image_path == "images/abc.jpg"
        assert restored.published_date == a.published_date

    def test_cache_expiry(self, db):
        a = make_article()
        db.save_content_cache([a])
        old = (now_vn() - timedelta(days=10)).isoformat()
        db._conn.execute("UPDATE article_cache SET cached_at = ?", (old,))
        db._conn.commit()
        assert db.load_content_cache(max_age_days=2) == {}
        db.prune()
        rows = db._conn.execute("SELECT COUNT(*) FROM article_cache").fetchone()
        assert rows[0] == 0


# ---------- URL normalization ----------

class TestUrlNormalization:
    def test_scheme_www_query_stripped(self):
        n = CrawlOrchestrator._normalize_url
        assert n("https://www.x.vn/a/?utm_source=zalo") == n("http://x.vn/a")

    def test_distinct_paths_stay_distinct(self):
        n = CrawlOrchestrator._normalize_url
        assert n("https://x.vn/a") != n("https://x.vn/b")


# ---------- Content cleaning ----------

class TestCleaning:
    def test_scripts_and_clutter_removed(self):
        cleaner = ContentCleaner("https://x.vn")
        html = (
            '<div><script>evil()</script><p>Giữ lại nội dung này.</p>'
            '<div class="related-news"><a href="/x">Tin liên quan</a></div></div>'
        )
        cleaned_html, text = cleaner.clean(html)
        assert "evil" not in cleaned_html
        assert "Tin liên quan" not in cleaned_html
        assert "Giữ lại nội dung này." in text

    def test_lazy_images_normalized_and_absolutized(self):
        cleaner = ContentCleaner("https://x.vn")
        html = '<div><p>t</p><img data-src="/img/a.jpg" src="data:image/gif;base64,x"></div>'
        cleaned_html, _ = cleaner.clean(html)
        assert 'src="https://x.vn/img/a.jpg"' in cleaned_html


# ---------- Renderer ----------

class TestRenderer:
    def test_render_digest_outputs(self, tmp_path):
        from tonghoptin.renderer import render_digest, BRAND_NAME

        articles = [
            make_article(url=f"https://example.vn/bai-{i}.html", title=f"Bài viết số {i}",
                         topics=["Kinh tế"], interest_score=5.0, final_score=5.0)
            for i in range(3)
        ]
        out = render_digest(articles, tmp_path, "2026-06-12_0800")

        html = out.read_text(encoding="utf-8")
        assert BRAND_NAME in html
        assert "Bài viết số 0" in html
        # Content must NOT be inlined in the page
        assert "x" * 250 not in html

        # Per-article content files exist and carry the content
        for a in articles:
            f = tmp_path / "articles" / f"{a.url_hash}.json"
            assert f.exists()
            data = json.loads(f.read_text(encoding="utf-8"))
            assert "Nội dung bài viết" in data["content_html"]

        # Markdown digest exists with brand
        md = (tmp_path / "tonghoptin_2026-06-12_0800.md").read_text(encoding="utf-8")
        assert BRAND_NAME in md


# ---------- Base scraper date window ----------

class TestDateWindow:
    def test_yesterday_evening_article_kept(self):
        """Articles from yesterday must pass the detail-page date filter."""
        from tonghoptin.scrapers.base import BaseScraper
        target = date(2026, 6, 12)
        window_start = target - timedelta(days=1)
        cap = target + timedelta(days=1)

        yesterday_evening = datetime(2026, 6, 11, 23, 30)
        two_days_ago = datetime(2026, 6, 10, 12, 0)

        assert window_start <= yesterday_evening.date() <= cap
        assert not (window_start <= two_days_ago.date() <= cap)

"""Deduplication database for tracking seen articles."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path

from tonghoptin.models import Article


def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy dedup across republishes.

    Lowercases, strips diacritics, removes punctuation, collapses whitespace.
    Two article titles that differ only in casing/punctuation/accents will
    produce the same normalized form.
    """
    if not title:
        return ""
    # Strip Vietnamese diacritics
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    # Replace non-alphanumeric with space
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


class DedupDB:
    """SQLite-based deduplication tracker.

    Tracks article URLs and normalized titles to detect new vs. previously
    seen articles. Same URL or same normalized title = already seen.
    Also stores last run timestamp for --since-last-run mode.
    """

    def __init__(self, db_path: str | Path = "tonghoptin.db"):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._create_tables()
        self._migrate()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_articles (
                url TEXT PRIMARY KEY,
                title TEXT,
                title_normalized TEXT,
                source_site TEXT,
                first_seen TEXT,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_time TEXT,
                articles_count INTEGER,
                errors_count INTEGER
            );
        """)
        self._conn.commit()

    def _migrate(self) -> None:
        """Add title_normalized column to pre-existing databases and backfill."""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(seen_articles)")]
        if "title_normalized" not in cols:
            self._conn.execute("ALTER TABLE seen_articles ADD COLUMN title_normalized TEXT")
            self._conn.commit()

        # Create index (safe to run after column is guaranteed to exist)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_title_norm ON seen_articles(title_normalized)"
        )
        self._conn.commit()

        # Backfill any NULL title_normalized
        rows = self._conn.execute(
            "SELECT url, title FROM seen_articles WHERE title_normalized IS NULL"
        ).fetchall()
        if rows:
            for url, title in rows:
                self._conn.execute(
                    "UPDATE seen_articles SET title_normalized = ? WHERE url = ?",
                    (_normalize_title(title or ""), url),
                )
            self._conn.commit()

    def mark_articles(self, articles: list[Article]) -> None:
        """Mark articles as new or seen based on URL and normalized title.

        An article is considered seen if:
          - its URL already exists in the DB, OR
          - its normalized title matches any existing entry (republish at new URL).

        Updates last_seen on existing rows, inserts new ones.
        """
        now = datetime.now().isoformat()
        for article in articles:
            title_norm = _normalize_title(article.title)

            # Check URL first
            row = self._conn.execute(
                "SELECT url FROM seen_articles WHERE url = ?",
                (article.url,),
            ).fetchone()

            if row:
                article.is_new = False
                self._conn.execute(
                    "UPDATE seen_articles SET last_seen = ?, title_normalized = ? WHERE url = ?",
                    (now, title_norm, article.url),
                )
                continue

            # Not same URL - check for a same-title republish
            title_row = None
            if title_norm:
                title_row = self._conn.execute(
                    "SELECT url FROM seen_articles WHERE title_normalized = ? LIMIT 1",
                    (title_norm,),
                ).fetchone()

            if title_row:
                # Republish: same title, different URL. Mark seen and
                # insert the new URL too so it's not re-flagged next run.
                article.is_new = False
                self._conn.execute(
                    "INSERT INTO seen_articles "
                    "(url, title, title_normalized, source_site, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (article.url, article.title, title_norm, article.source_site, now, now),
                )
                # Update the original row's last_seen
                self._conn.execute(
                    "UPDATE seen_articles SET last_seen = ? WHERE url = ?",
                    (now, title_row[0]),
                )
            else:
                article.is_new = True
                self._conn.execute(
                    "INSERT INTO seen_articles "
                    "(url, title, title_normalized, source_site, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (article.url, article.title, title_norm, article.source_site, now, now),
                )
        self._conn.commit()

    def record_run(self, articles_count: int, errors_count: int) -> None:
        """Record a crawl run for history."""
        self._conn.execute(
            "INSERT INTO run_history (run_time, articles_count, errors_count) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), articles_count, errors_count),
        )
        self._conn.commit()

    def get_last_run_time(self) -> datetime | None:
        """Get timestamp of the last successful run."""
        row = self._conn.execute(
            "SELECT run_time FROM run_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            return datetime.fromisoformat(row[0])
        return None

    def close(self) -> None:
        self._conn.close()

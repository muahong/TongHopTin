"""Deduplication database for tracking seen articles."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from tonghoptin.models import Article


class DedupDB:
    """SQLite-based deduplication tracker.

    Tracks article URLs to detect new vs. previously seen articles.
    Also stores last run timestamp for --since-last-run mode.
    """

    def __init__(self, db_path: str | Path = "tonghoptin.db"):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_articles (
                url TEXT PRIMARY KEY,
                title TEXT,
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

    def mark_articles(self, articles: list[Article]) -> None:
        """Mark articles as new or seen, updating is_new flag in-place."""
        now = datetime.now().isoformat()
        for article in articles:
            row = self._conn.execute(
                "SELECT url FROM seen_articles WHERE url = ?",
                (article.url,)
            ).fetchone()

            if row:
                article.is_new = False
                self._conn.execute(
                    "UPDATE seen_articles SET last_seen = ? WHERE url = ?",
                    (now, article.url),
                )
            else:
                article.is_new = True
                self._conn.execute(
                    "INSERT INTO seen_articles (url, title, source_site, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (article.url, article.title, article.source_site, now, now),
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

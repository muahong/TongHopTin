"""Browser history reading and analysis."""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class DomainStats:
    """Visit statistics for a domain."""
    domain: str
    visit_count: int
    unique_urls: int
    last_visit: datetime
    sample_titles: list[str]


def read_browser_history(
    history_path: str,
    days: int = 30,
) -> list[DomainStats]:
    """Read Chrome/Brave history SQLite file and analyze by domain.

    Chrome locks the History file while running, so we copy it first.
    """
    path = Path(history_path)
    if not path.exists():
        logger.warning(f"History file not found: {history_path}")
        return []

    # Copy to temp file (Chrome locks the original)
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        tmp_path = tmp.name
    shutil.copy2(path, tmp_path)

    try:
        return _analyze_history(tmp_path, days)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _analyze_history(db_path: str, days: int) -> list[DomainStats]:
    """Analyze a copied History database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Chrome timestamps are microseconds since 1601-01-01
    # Convert to Unix epoch
    chrome_epoch = datetime(1601, 1, 1)
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_chrome = int((cutoff - chrome_epoch).total_seconds() * 1_000_000)

    try:
        rows = conn.execute("""
            SELECT u.url, u.title, u.visit_count, v.visit_time
            FROM urls u
            JOIN visits v ON u.id = v.url
            WHERE v.visit_time > ?
            ORDER BY v.visit_time DESC
        """, (cutoff_chrome,)).fetchall()
    except sqlite3.OperationalError as e:
        logger.error(f"Failed to query history: {e}")
        conn.close()
        return []

    # Aggregate by domain
    domain_visits: Counter = Counter()
    domain_urls: dict[str, set[str]] = {}
    domain_last_visit: dict[str, datetime] = {}
    domain_titles: dict[str, list[str]] = {}

    for row in rows:
        url = row["url"]
        parsed = urlparse(url)
        domain = parsed.netloc

        # Skip internal/empty domains
        if not domain or domain in ("", "newtab", "extensions"):
            continue
        # Skip common non-news domains
        if any(d in domain for d in ["google.com", "facebook.com", "youtube.com", "github.com", "localhost"]):
            continue

        domain_visits[domain] += 1

        if domain not in domain_urls:
            domain_urls[domain] = set()
        domain_urls[domain].add(url)

        # Convert Chrome timestamp to datetime
        visit_time = chrome_epoch + timedelta(microseconds=row["visit_time"])
        if domain not in domain_last_visit or visit_time > domain_last_visit[domain]:
            domain_last_visit[domain] = visit_time

        title = row["title"]
        if title and domain not in domain_titles:
            domain_titles[domain] = []
        if title and len(domain_titles.get(domain, [])) < 5:
            domain_titles[domain].append(title)

    conn.close()

    # Build domain stats, sorted by visit count
    stats = []
    for domain, count in domain_visits.most_common():
        stats.append(DomainStats(
            domain=domain,
            visit_count=count,
            unique_urls=len(domain_urls.get(domain, set())),
            last_visit=domain_last_visit.get(domain, datetime.min),
            sample_titles=domain_titles.get(domain, []),
        ))

    return stats


def suggest_favourites(
    stats: list[DomainStats],
    threshold: int = 5,
) -> list[DomainStats]:
    """Filter domain stats to suggest favourite sites."""
    return [s for s in stats if s.visit_count >= threshold]


def merge_history_sources(*paths: str, days: int = 30) -> list[DomainStats]:
    """Merge history from multiple browser files."""
    all_stats: dict[str, DomainStats] = {}

    for path in paths:
        if not path:
            continue
        stats = read_browser_history(path, days)
        for s in stats:
            if s.domain in all_stats:
                existing = all_stats[s.domain]
                existing.visit_count += s.visit_count
                existing.unique_urls += s.unique_urls
                if s.last_visit > existing.last_visit:
                    existing.last_visit = s.last_visit
                existing.sample_titles.extend(s.sample_titles)
                existing.sample_titles = existing.sample_titles[:5]
            else:
                all_stats[s.domain] = s

    # Sort by visit count
    return sorted(all_stats.values(), key=lambda x: x.visit_count, reverse=True)

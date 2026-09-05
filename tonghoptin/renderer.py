"""HTML digest renderer using Jinja2."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from tonghoptin.cleaning import ContentCleaner, safe_url, is_sanitized, mark_sanitized
from tonghoptin.overview import build_overview, plain_text
from jinja2 import Environment, FileSystemLoader

from tonghoptin.models import Article
from tonghoptin.vietnamese import now_vn

logger = logging.getLogger(__name__)

BRAND_NAME = "Thông Tin Là Sức Mạnh!"

# Friendly display names for known sources (fallback: capitalized domain part)
SOURCE_NAMES = {
    "vnexpress.net": "VnExpress",
    "vietnamnet.vn": "VietnamNet",
    "thanhnien.vn": "Thanh Niên",
    "tuoitre.vn": "Tuổi Trẻ",
    "dantri.com.vn": "Dân Trí",
    "cafef.vn": "CafeF",
    "cafebiz.vn": "CafeBiz",
    "vietnambusinessinsider.vn": "VN Business Insider",
    "tienphong.vn": "Tiền Phong",
    "nld.com.vn": "Người Lao Động",
    "nhandan.vn": "Nhân Dân",
    "vietnamplus.vn": "VietnamPlus",
    "www.vietnamplus.vn": "VietnamPlus",
    "sggp.org.vn": "SGGP",
    "www.sggp.org.vn": "SGGP",
    "baochinhphu.vn": "Báo Chính Phủ",
    "laodong.vn": "Lao Động",
    "plo.vn": "PLO",
    "thesaigontimes.vn": "Saigon Times",
    "mekongasean.vn": "Mekong ASEAN",
    "tapchikinhtetaichinh.vn": "TC Tài Chính",
    "chinhphu.vn": "Chính Phủ",
}


def source_display_name(domain: str) -> str:
    if domain in SOURCE_NAMES:
        return SOURCE_NAMES[domain]
    parts = [p for p in domain.split(".") if p and p.lower() != "www"]
    return parts[0].capitalize() if parts else domain


def source_hue(domain: str) -> int:
    """Stable per-source hue (0-359) so each source gets its own accent color."""
    h = 0
    for ch in domain:
        h = (h * 31 + ord(ch)) % 360
    return h


@dataclass
class SourceGroup:
    """Articles grouped by source site."""
    domain: str
    name: str
    count: int
    articles: list[Article]


def _time_display(article: Article) -> str:
    """Compact publish time: 'HH:MM' for today, 'HH:MM dd/MM' otherwise."""
    today = now_vn().date()
    if article.published_date.date() == today:
        return article.published_date.strftime("%H:%M")
    return article.published_date.strftime("%H:%M %d/%m")


def render_digest(
    articles: list[Article],
    output_dir: Path,
    timestamp_label: str | None = None,
    coverage: list[dict] | None = None,
) -> Path:
    """Render articles into an HTML digest file.

    The page itself only carries card metadata; each article's full content
    is written to articles/<hash>.json for HTTP(S) and articles/<hash>.js for
    local file viewing. Content is loaded on demand when the reader opens it,
    which keeps the page much smaller than inlining every article.

    timestamp_label: e.g. "2026-04-04_1830". If None, generated from now().
    Returns the path to the generated HTML file.
    """
    articles = [replace(a, title=plain_text(a.title), source_category=plain_text(a.source_category)) for a in articles]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not timestamp_label:
        timestamp_label = now_vn().strftime("%Y-%m-%d_%H%M")
    timestamp_label = _unique_archive_label(output_dir, timestamp_label)

    date_str = timestamp_label.split("_")[0]  # "2026-04-04"
    publication_days = sorted({a.published_date.date().isoformat() for a in articles if a.published_date})
    if publication_days:
        date_str = publication_days[0] if len(publication_days) == 1 else f"{publication_days[0]} – {publication_days[-1]}"

    # Group articles by source
    source_groups = _group_by_source(articles)

    # Count topics
    topic_counter: Counter = Counter()
    for article in articles:
        for topic in article.topics:
            topic_counter[topic] += 1
    topic_counts = topic_counter.most_common()

    # Load templates
    template_dir = Path(__file__).parent / "templates"
    css = (template_dir / "style.css").read_text(encoding="utf-8")
    js = (template_dir / "script.js").read_text(encoding="utf-8")

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    env.globals["source_name"] = source_display_name
    env.globals["time_display"] = _time_display
    env.globals["source_hue"] = source_hue
    template = env.get_template("digest.html")

    # Per-article content files, loaded lazily by the reading modal. Browsers
    # do not allow fetch() from file:// pages, so the JS sidecar provides the
    # same data through a regular <script> element for local archives.
    content_base = Path("articles") / timestamp_label
    articles_dir = output_dir / content_base
    articles_dir.mkdir(parents=True, exist_ok=True)
    for article in articles:
        if not is_sanitized(article):
            article.content_html, article.content_text = ContentCleaner(article.url).clean(article.content_html)
            mark_sanitized(article)
        article.url = safe_url(article.url)
        if article.hero_image_path and not __import__("re").fullmatch(r"images/[a-f0-9]+\.jpg", article.hero_image_path):
            article.hero_image_path = None
        content_file = articles_dir / f"{article.url_hash}.json"
        content_file.write_text(
            json.dumps({"content_html": article.content_html}, ensure_ascii=False),
            encoding="utf-8",
        )
        script_file = articles_dir / f"{article.url_hash}.js"
        article_id_json = json.dumps(article.url_hash)
        content_json = json.dumps(article.content_html, ensure_ascii=False)
        script_file.write_text(
            "window.__ttsmArticleContent = window.__ttsmArticleContent || {};\n"
            f"window.__ttsmArticleContent[{article_id_json}] = {content_json};\n",
            encoding="utf-8",
        )

    # Lightweight metadata for the modal header (content loaded separately)
    articles_meta = {}
    for article in articles:
        articles_meta[article.url_hash] = {
            "title": article.title,
            "url": article.url,
            "source": source_display_name(article.source_site),
            "category": article.source_category,
            "date": article.published_date.strftime("%H:%M %d/%m/%Y"),
            "author": article.author or "",
            "rt": article.estimated_reading_time_minutes,
            "topics": article.topics,
            "img": article.hero_image_path or "",
            "content": (content_base / article.url_hash).as_posix(),
        }
    articles_json = json.dumps(articles_meta, ensure_ascii=False).replace("<", "\\u003c")
    overview_json = json.dumps(build_overview(articles), ensure_ascii=False).replace("<", "\\u003c")

    # Render
    html = template.render(
        brand=BRAND_NAME,
        date_str=date_str,
        total_articles=len(articles),
        new_articles=sum(1 for a in articles if a.is_new),
        total_sources=len(source_groups),
        generated_at=now_vn().strftime("%H:%M %d/%m/%Y"),
        sources=source_groups,
        all_articles=articles,
        topic_counts=topic_counts,
        articles_json=articles_json,
        overview_json=overview_json,
        coverage=coverage or [],
        css=css,
        js=js,
    )

    # Write HTML output
    output_file = output_dir / f"tonghoptin_{timestamp_label}.html"
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    output_file.write_text(html, encoding="utf-8")

    # Write Markdown output
    md_file = output_dir / f"tonghoptin_{timestamp_label}.md"
    md_content = _render_markdown(articles, date_str, timestamp_label)
    md_file.write_text(md_content, encoding="utf-8")

    logger.info(f"Digest written to {output_file} + {md_file.name} ({len(articles)} articles)")
    return output_file


def _unique_archive_label(output_dir: Path, timestamp_label: str) -> str:
    """Return a label that cannot overwrite an existing historical run."""
    candidate = timestamp_label
    suffix = 2
    while (
        (output_dir / f"tonghoptin_{candidate}.html").exists()
        or (output_dir / f"tonghoptin_{candidate}.md").exists()
        or (output_dir / "articles" / candidate).exists()
    ):
        candidate = f"{timestamp_label}_{suffix}"
        suffix += 1
    return candidate


def _render_markdown(articles: list[Article], date_str: str, timestamp_label: str) -> str:
    """Render articles into a Markdown file for LLM consumption."""
    lines = []
    generated_at = now_vn().strftime("%H:%M %d/%m/%Y")
    new_count = sum(1 for a in articles if a.is_new)
    sources = len(set(a.source_site for a in articles))

    lines.append(f"# {BRAND_NAME} - {date_str}")
    lines.append("")
    lines.append(f"Generated: {generated_at} | Articles: {len(articles)} | New: {new_count} | Sources: {sources}")
    lines.append("")

    for article in articles:
        lines.append("---")
        lines.append("")
        lines.append(f"## [{article.title}]({article.url})")
        lines.append("")

        # Metadata line
        source_name = source_display_name(article.source_site)
        date_fmt = article.published_date.strftime("%H:%M %d/%m")
        author_part = f" | **Author**: {article.author}" if article.author else ""
        lines.append(
            f"**Source**: {source_name} · {article.source_category} | "
            f"**Date**: {date_fmt}{author_part}"
        )

        topics_str = ", ".join(article.topics) if article.topics else "N/A"
        lines.append(
            f"**Topics**: {topics_str} | "
            f"**Score**: {article.final_score} (interest: {article.interest_score}, freshness: {article.freshness_adjustment}) | "
            f"**Reading**: {article.estimated_reading_time_minutes} min"
        )
        lines.append("")

        # Content
        if article.content_text:
            lines.append(article.content_text)
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*{BRAND_NAME} — {timestamp_label}*")
    lines.append("")

    return "\n".join(lines)


def _group_by_source(articles: list[Article]) -> list[SourceGroup]:
    """Group articles by source_site domain."""
    groups: dict[str, list[Article]] = {}
    for article in articles:
        domain = article.source_site
        if domain not in groups:
            groups[domain] = []
        groups[domain].append(article)

    # Create SourceGroup objects, sorted by article count descending
    result = []
    for domain, arts in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        result.append(SourceGroup(
            domain=domain,
            name=source_display_name(domain),
            count=len(arts),
            articles=arts,
        ))

    return result

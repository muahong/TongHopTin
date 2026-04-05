"""HTML digest renderer using Jinja2."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from tonghoptin.models import Article

logger = logging.getLogger(__name__)


@dataclass
class SourceGroup:
    """Articles grouped by source site."""
    domain: str
    name: str
    count: int
    articles: list[Article]


def render_digest(
    articles: list[Article],
    output_dir: Path,
    timestamp_label: str | None = None,
) -> Path:
    """Render articles into an HTML digest file.

    timestamp_label: e.g. "2026-04-04_1830". If None, generated from now().
    Returns the path to the generated HTML file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not timestamp_label:
        timestamp_label = datetime.now().strftime("%Y-%m-%d_%H%M")

    date_str = timestamp_label.split("_")[0]  # "2026-04-04"

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
        autoescape=False,  # We trust our own cleaned HTML
    )
    template = env.get_template("digest.html")

    # Build article data JSON for modal
    articles_data = {}
    for article in articles:
        articles_data[article.url_hash] = {
            "title": article.title,
            "url": article.url,
            "source_category": article.source_category,
            "published_date": article.published_date.strftime("%H:%M %d/%m/%Y"),
            "author": article.author or "",
            "reading_time": article.estimated_reading_time_minutes,
            "topics": article.topics,
            "hero_image_path": article.hero_image_path or "",
            "content_html": article.content_html,
            "is_new": article.is_new,
            "interest_score": article.interest_score,
            "freshness_adjustment": article.freshness_adjustment,
            "final_score": article.final_score,
        }
    articles_json = json.dumps(articles_data, ensure_ascii=False)

    # Render
    html = template.render(
        date_str=date_str,
        total_articles=len(articles),
        new_articles=sum(1 for a in articles if a.is_new),
        total_sources=len(source_groups),
        generated_at=datetime.now().strftime("%H:%M %d/%m/%Y"),
        sources=source_groups,
        all_articles=articles,
        topic_counts=topic_counts,
        articles_json=articles_json,
        css=css,
        js=js,
    )

    # Write HTML output
    output_file = output_dir / f"tonghoptin_{timestamp_label}.html"
    output_file.write_text(html, encoding="utf-8")

    # Write Markdown output
    md_file = output_dir / f"tonghoptin_{timestamp_label}.md"
    md_content = _render_markdown(articles, date_str, timestamp_label)
    md_file.write_text(md_content, encoding="utf-8")

    logger.info(f"Digest written to {output_file} + {md_file.name} ({len(articles)} articles)")
    return output_file


def _render_markdown(articles: list[Article], date_str: str, timestamp_label: str) -> str:
    """Render articles into a Markdown file for LLM consumption."""
    lines = []
    generated_at = datetime.now().strftime("%H:%M %d/%m/%Y")
    new_count = sum(1 for a in articles if a.is_new)
    sources = len(set(a.source_site for a in articles))

    lines.append(f"# TongHopTin - {date_str}")
    lines.append("")
    lines.append(f"Generated: {generated_at} | Articles: {len(articles)} | New: {new_count} | Sources: {sources}")
    lines.append("")

    for article in articles:
        lines.append("---")
        lines.append("")
        lines.append(f"## [{article.title}]({article.url})")
        lines.append("")

        # Metadata line
        source_name = article.source_site.split(".")[0].capitalize()
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
    lines.append(f"*Generated by TongHopTin {timestamp_label}*")
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
        # Use domain as display name, capitalize first letter
        name = domain.split(".")[0].capitalize()
        result.append(SourceGroup(
            domain=domain,
            name=name,
            count=len(arts),
            articles=arts,
        ))

    return result

"""Repair retained HTML archives so their article bodies load from file://.

Older runs kept each Markdown digest but removed the lazy-loaded JSON and image
files after seven days. The Markdown copy still contains the full article text,
so this utility rebuilds file-safe JavaScript sidecars from it and refreshes the
inline reader code in every matching HTML digest.
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import re
from pathlib import Path


META_RE = re.compile(
    r'<script type="application/json" id="articles-data">\s*(\{.*?\})\s*</script>',
    re.DOTALL,
)
READER_SCRIPT_RE = re.compile(
    r'<script>// Thông Tin Là Sức Mạnh! — interactive digest.*?</script>'
    r'(?=\s*</body>)',
    re.DOTALL,
)
ARTICLE_HEADING_RE = re.compile(
    r"^## \[(.*?)\]\((https?://[^\r\n]+)\)[ \t]*\r?$",
    re.MULTILINE | re.DOTALL,
)


def parse_markdown_articles(markdown: str) -> dict[str, str]:
    """Return article URL -> readable HTML rebuilt from a Markdown digest."""
    headings = list(ARTICLE_HEADING_RE.finditer(markdown))
    articles: dict[str, str] = {}
    for heading_index, heading in enumerate(headings):
        end = (
            headings[heading_index + 1].start()
            if heading_index + 1 < len(headings)
            else len(markdown)
        )
        section = markdown[heading.end():end].splitlines()
        url = heading.group(2)
        topics_index = next(
            (i for i, line in enumerate(section) if line.startswith("**Topics**:")),
            None,
        )
        if topics_index is None:
            continue

        content_lines = section[topics_index + 1:]
        while content_lines and not content_lines[0].strip():
            content_lines.pop(0)
        while content_lines and (
            not content_lines[-1].strip() or content_lines[-1].strip() == "---"
        ):
            content_lines.pop()

        paragraphs = [
            part.strip()
            for part in re.split(r"\n\s*\n", "\n".join(content_lines).strip())
            if part.strip()
        ]
        if paragraphs:
            articles[url] = "".join(
                f"<p>{html_module.escape(paragraph)}</p>" for paragraph in paragraphs
            )
    return articles


def sidecar_text(article_id: str, content_html: str) -> str:
    """Build the executable data-only sidecar consumed by script.js."""
    return (
        "window.__ttsmArticleContent = window.__ttsmArticleContent || {};\n"
        f"window.__ttsmArticleContent[{json.dumps(article_id)}] = "
        f"{json.dumps(content_html, ensure_ascii=False)};\n"
    )


def repair_archive(
    html_path: Path,
    reader_script: str,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Repair one digest and return (sidecars rebuilt, bodies unavailable)."""
    markdown_path = html_path.with_suffix(".md")
    if not markdown_path.exists():
        return 0, 0

    digest_html = html_path.read_text(encoding="utf-8")
    meta_match = META_RE.search(digest_html)
    if not meta_match:
        raise ValueError(f"Article metadata not found in {html_path}")
    metadata = json.loads(meta_match.group(1))
    markdown_articles = parse_markdown_articles(markdown_path.read_text(encoding="utf-8"))

    archive_label = html_path.stem.removeprefix("tonghoptin_")
    content_base = Path("articles") / archive_label
    articles_dir = html_path.parent / content_base
    if not dry_run:
        articles_dir.mkdir(parents=True, exist_ok=True)

    rebuilt = unavailable = 0
    for article_id, article_meta in metadata.items():
        content_html = ""
        existing_content = article_meta.get("content")
        if existing_content:
            existing_json = html_path.parent / Path(existing_content).with_suffix(".json")
            try:
                content_html = json.loads(existing_json.read_text(encoding="utf-8")).get(
                    "content_html", ""
                )
            except (json.JSONDecodeError, OSError):
                pass
        if not content_html:
            content_html = markdown_articles.get(article_meta.get("url", ""), "")
        if not content_html:
            legacy_json = html_path.parent / "articles" / f"{article_id}.json"
            try:
                content_html = json.loads(legacy_json.read_text(encoding="utf-8")).get(
                    "content_html", ""
                )
            except (json.JSONDecodeError, OSError):
                pass
        if not content_html:
            unavailable += 1
            continue

        rebuilt += 1
        article_meta["content"] = (content_base / article_id).as_posix()
        if not dry_run:
            (articles_dir / f"{article_id}.json").write_text(
                json.dumps({"content_html": content_html}, ensure_ascii=False),
                encoding="utf-8",
            )
            (articles_dir / f"{article_id}.js").write_text(
                sidecar_text(article_id, content_html),
                encoding="utf-8",
            )

    metadata_block = (
        '<script type="application/json" id="articles-data">\n'
        + json.dumps(metadata, ensure_ascii=False)
        + "\n</script>"
    )
    repaired_html = (
        digest_html[:meta_match.start()]
        + metadata_block
        + digest_html[meta_match.end():]
    )
    replacement = f"<script>{reader_script}</script>"
    repaired_html, replacements = READER_SCRIPT_RE.subn(
        lambda _match: replacement,
        repaired_html,
        count=1,
    )
    if replacements != 1:
        raise ValueError(f"Reader script not found in {html_path}")
    if not dry_run and repaired_html != digest_html:
        html_path.write_text(repaired_html, encoding="utf-8")

    return rebuilt, unavailable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    reader_script = (
        Path(__file__).resolve().parents[1] / "tonghoptin" / "templates" / "script.js"
    ).read_text(encoding="utf-8")

    archives = sorted(args.output.glob("tonghoptin_*.html"))
    repaired = rebuilt = unavailable = 0
    for archive in archives:
        count, missing = repair_archive(
            archive,
            reader_script,
            args.dry_run,
        )
        if archive.with_suffix(".md").exists():
            repaired += 1
        rebuilt += count
        unavailable += missing
        print(
            f"[{repaired}/{len(archives)}] {archive.name}: "
            f"{count} bodies available, {missing} unavailable",
            flush=True,
        )

    mode = "Would repair" if args.dry_run else "Repaired"
    print(
        f"{mode} {repaired} archives; {rebuilt} immutable article snapshots; "
        f"{unavailable} bodies unavailable"
    )
    return 0 if unavailable == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

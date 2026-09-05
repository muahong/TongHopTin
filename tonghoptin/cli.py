"""CLI entry point for TongHopTin."""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import click

from tonghoptin.config import load_config, save_config, DEFAULT_SITES
from tonghoptin.dedup import DedupDB
from tonghoptin.history import merge_history_sources, suggest_favourites
from tonghoptin.models import AppConfig, FetchMethod, SiteConfig
from tonghoptin.orchestrator import CrawlOrchestrator
from tonghoptin.renderer import render_digest


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler("tonghoptin.log", encoding="utf-8"),
        ],
    )


@click.group(invoke_without_command=True)
@click.option("--config", "config_path", default="config.yaml", help="Path to config file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def main(ctx, config_path, verbose):
    """TongHopTin - Vietnamese news aggregation tool."""
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["verbose"] = verbose
    if ctx.invoked_subcommand is None:
        click.echo("Use 'tonghoptin --help' for usage info.")
        click.echo("Common commands: init, collect, favourites")


@main.command()
@click.option("--chrome", "chrome_path", default="", help="Path to Chrome History file")
@click.option("--brave", "brave_path", default="", help="Path to Brave History file")
@click.option("--days", default=30, help="Days of history to analyze")
@click.option("--threshold", default=5, help="Minimum visits for favourite detection")
@click.pass_context
def init(ctx, chrome_path, brave_path, days, threshold):
    """Initialize: analyze browser history and generate config with suggested favourites."""
    config_path = ctx.obj["config_path"]

    click.echo("Analyzing browser history...")

    if not chrome_path and not brave_path:
        click.echo("Please provide at least one history file path:")
        click.echo("  tonghoptin init --chrome 'path/to/History' --brave 'path/to/History'")
        return

    stats = merge_history_sources(chrome_path, brave_path, days=days)
    favourites = suggest_favourites(stats, threshold=threshold)

    click.echo(f"\nFound {len(stats)} domains, {len(favourites)} favourites (>= {threshold} visits):\n")

    # Show top favourites
    for i, fav in enumerate(favourites[:30], 1):
        click.echo(f"  {i:2d}. {fav.domain:30s} ({fav.visit_count} visits, {fav.unique_urls} pages)")
        for title in fav.sample_titles[:2]:
            click.echo(f"      - {title[:70]}")

    # Build config
    config = AppConfig(
        chrome_history_path=chrome_path,
        brave_history_path=brave_path,
        analysis_days=days,
        auto_detect_threshold=threshold,
        sites=list(DEFAULT_SITES),  # Start with known sites
    )

    # Add discovered favourite domains that have scrapers
    from tonghoptin.scrapers import SCRAPER_REGISTRY
    for fav in favourites:
        if fav.domain in SCRAPER_REGISTRY:
            # Already in DEFAULT_SITES, ensure it's enabled
            for site in config.sites:
                if site.domain == fav.domain:
                    site.enabled = True
                    break
        elif fav.visit_count >= threshold * 2:
            # High-frequency site without dedicated scraper -> add as generic
            config.sites.append(SiteConfig(
                name=fav.domain.split(".")[0],
                base_url=f"https://{fav.domain}",
                domain=fav.domain,
                fetch_method=FetchMethod.REQUESTS,
                request_delay=1.0,
                max_pages=3,
                max_concurrent=3,
            ))

    save_config(config, config_path)
    click.echo(f"\nConfig saved to {config_path}")
    click.echo("Edit this file to customize sites, then run: tonghoptin collect")


@main.command()
@click.option("--days", default=1, type=click.IntRange(1, 90), help="Number of Vietnam calendar days ending at --date")
@click.option("--date", "day", type=click.DateTime(formats=["%Y-%m-%d"]), default=None, help="Vietnam date YYYY-MM-DD; default today")
@click.option("--output", "output_dir", default=None, help="Output directory override")
@click.option("--since-last-run", is_flag=True, help="Include days since last successful run")
@click.pass_context
def collect(ctx, days, day, output_dir, since_last_run):
    """Collect, preserve crawl evidence, and publish a daily reader."""
    from tonghoptin.archive import collection_lock
    config = load_config(ctx.obj["config_path"])
    if output_dir:
        config.output_directory = output_dir
    out_path = Path(config.output_directory)
    out_path.mkdir(parents=True, exist_ok=True)
    with collection_lock(out_path):
        _collect(config, out_path, days, day, since_last_run)


def _collect(config, out_path, days, day, since_last_run):
    from tonghoptin.vietnamese import now_vn
    from tonghoptin.archive import save_run
    import uuid
    end_date = day.date() if day else now_vn().date()
    start_date = end_date - timedelta(days=days - 1)
    db = DedupDB(out_path / "tonghoptin.db")
    try:
        if since_last_run:
            last_run = db.get_last_run_time()
            if last_run:
                start_date = min(last_run.date(), end_date)
        timestamp_label = now_vn().strftime("%Y-%m-%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        click.echo(f"Collecting {start_date} through {end_date} (Vietnam time)...")
        content_cache = db.load_content_cache(max_age_days=max(days, 2))
        orchestrator = CrawlOrchestrator(config, target_date=end_date, start_date=start_date,
            output_dir=out_path, timestamp_label=timestamp_label, content_cache=content_cache)
        articles, results = asyncio.run(orchestrator.run())
        # Save failures and every successfully parsed article before any cache pruning.
        coverage = save_run(out_path, timestamp_label, start_date, end_date, articles, results)
        all_parsed = [a for r in results for a in r.parsed_articles]
        db.save_content_cache(all_parsed or articles)
        if not articles:
            raise click.ClickException("No dated articles collected. Crawl report saved; previous website retained.")
        db.mark_articles(articles)
        # Keep all sources. Same-title republications are grouped in the overview,
        # not silently discarded by the personal freshness heuristic.
        output_file = render_digest(articles, out_path, timestamp_label, coverage=coverage)
        _publish_to_docs(output_file, out_path, articles)
        db.record_run(len(articles), sum(len(r.errors) for r in results))
        db.prune()
        click.echo(f"Saved {len(articles)} articles: {output_file}")
        for row in coverage:
            click.echo(f"  {row['site_name']}: {row['articles_count']} articles, {row['errors_count']} errors ({row['status']})")
    finally:
        db.close()


@main.command("backup")
@click.option("--destination", default="archive", help="Private archive repository checkout")
def backup_command(destination):
    """Create incremental, immutable archive packs (no network upload)."""
    from tonghoptin.archive import backup, collection_lock
    import json
    with collection_lock(Path("output")):
        click.echo(json.dumps(backup(Path.cwd(), Path(destination))))


@main.command("verify-archive")
@click.option("--destination", default="archive")
def verify_archive(destination):
    """Verify every archived pack and latest file without extracting it."""
    from tonghoptin.archive import restore
    click.echo(f"Verified {restore(destination, Path('archive-restore'), verify_only=True)} files")


def _publish_to_docs(output_file: Path, output_dir: Path, articles: list) -> None:
    """Copy latest digest to docs/ folder for GitHub Pages.

    Only files referenced by the current digest are published: the HTML,
    each article's content JSON/JS sidecars, and each article's hero image.
    """
    project_root = Path.cwd()
    docs_dir = project_root / "docs"

    (docs_dir / "images").mkdir(parents=True, exist_ok=True)
    (docs_dir / "articles").mkdir(parents=True, exist_ok=True)

    # Publish assets first; replace index only after all dependencies exist.


    archive_label = output_file.stem.removeprefix("tonghoptin_")
    docs_content_dir = docs_dir / "articles" / archive_label
    docs_content_dir.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor
    copies = {}
    for article in articles:
        for suffix in (".json", ".js"):
            source = output_dir / "articles" / archive_label / f"{article.url_hash}{suffix}"
            if not source.is_file():
                raise FileNotFoundError(f"Missing article dependency: {source}")
            copies[docs_content_dir / source.name] = source
        if article.hero_image_path:
            source = output_dir / article.hero_image_path
            if source.is_file():
                copies[docs_dir / "images" / source.name] = source
    copies[docs_dir / output_file.name] = output_file
    md_file = output_file.with_suffix(".md")
    if md_file.exists():
        copies[docs_dir / md_file.name] = md_file

    def copy_asset(item):
        import filecmp
        destination, source = item
        if destination.is_file() and filecmp.cmp(source, destination, shallow=False):
            return
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(copy_asset, copies.items()))
    temporary = docs_dir / "index.html.tmp"
    shutil.copyfile(output_file, temporary)
    temporary.replace(docs_dir / "index.html")

    # Custom domain + disable Jekyll processing
    (docs_dir / "CNAME").write_text("chuyenhay.com")
    (docs_dir / ".nojekyll").write_text("")


def _cleanup_output(output_dir: Path) -> None:
    """Preserve all generated archives and their dependencies permanently.

    The function remains as an explicit policy hook so future maintenance does
    not accidentally reintroduce age-based deletion at the collect call site.
    """
    del output_dir


@main.group()
def favourites():
    """Manage favourite sites."""
    pass


@favourites.command("list")
@click.pass_context
def favourites_list(ctx):
    """List configured favourite sites."""
    config = load_config(ctx.obj["config_path"])
    click.echo(f"Configured sites ({len(config.sites)}):\n")
    for site in config.sites:
        status = "enabled" if site.enabled else "disabled"
        click.echo(
            f"  {site.name:15s} {site.domain:25s} "
            f"{site.fetch_method.value:12s} [{status}]"
        )


@favourites.command("add")
@click.argument("domain")
@click.option("--name", default=None, help="Display name")
@click.option("--playwright", is_flag=True, help="Use Playwright for JS rendering")
@click.pass_context
def favourites_add(ctx, domain, name, playwright):
    """Add a site to favourites."""
    config = load_config(ctx.obj["config_path"])

    # Check if already exists
    for site in config.sites:
        if site.domain == domain:
            click.echo(f"Site {domain} already exists. Enable it with config edit.")
            return

    method = FetchMethod.PLAYWRIGHT if playwright else FetchMethod.REQUESTS
    config.sites.append(SiteConfig(
        name=name or domain.split(".")[0],
        base_url=f"https://{domain}",
        domain=domain,
        fetch_method=method,
    ))

    save_config(config, ctx.obj["config_path"])
    click.echo(f"Added {domain} to favourites.")


@favourites.command("remove")
@click.argument("domain")
@click.pass_context
def favourites_remove(ctx, domain):
    """Remove a site from favourites."""
    config = load_config(ctx.obj["config_path"])
    config.sites = [s for s in config.sites if s.domain != domain]
    save_config(config, ctx.obj["config_path"])
    click.echo(f"Removed {domain} from favourites.")


if __name__ == "__main__":
    main()

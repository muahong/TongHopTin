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
@click.option("--days", default=1, help="Collect articles from last N days (default: today)")
@click.option("--output", "output_dir", default=None, help="Output directory override")
@click.option("--since-last-run", is_flag=True, help="Collect since last successful run")
@click.pass_context
def collect(ctx, days, output_dir, since_last_run):
    """Collect articles from all configured sites and generate HTML digest."""
    config = load_config(ctx.obj["config_path"])

    if output_dir:
        config.output_directory = output_dir

    out_path = Path(config.output_directory)
    out_path.mkdir(parents=True, exist_ok=True)

    # Determine target date
    target = date.today()
    if days > 1:
        target = date.today() - timedelta(days=days - 1)

    db = DedupDB(out_path / "tonghoptin.db")

    if since_last_run:
        last_run = db.get_last_run_time()
        if last_run:
            target = last_run.date()
            click.echo(f"Collecting since last run: {target}")

    # Generate timestamp label for this run (used for filenames)
    from tonghoptin.vietnamese import now_vn
    timestamp_label = now_vn().strftime("%Y-%m-%d_%H%M")

    click.echo(f"Collecting articles for {target} from {len(config.sites)} sites...")

    # Run the crawler
    orchestrator = CrawlOrchestrator(
        config, target_date=target, output_dir=out_path, timestamp_label=timestamp_label
    )
    articles, results = asyncio.run(orchestrator.run())

    if not articles:
        click.echo("No articles collected.")
        total_errors = sum(len(r.errors) for r in results)
        if total_errors:
            click.echo(f"Encountered {total_errors} errors. Check tonghoptin.log for details.")
        return

    # Mark with 7-day sliding-window dedup (URL + normalized title in VN time).
    # is_new=False flags same-day-rehashes of content seen in the last 7 days,
    # which we filter out of the digest.
    db.mark_articles(articles)

    total_collected = len(articles)
    fresh_articles = [a for a in articles if a.is_new]
    hidden_count = total_collected - len(fresh_articles)

    if not fresh_articles:
        click.echo(
            f"\nNo fresh articles today. "
            f"({total_collected} collected, all flagged as rehashes.)"
        )
        total_errors = sum(len(r.errors) for r in results)
        db.record_run(total_collected, total_errors)
        db.close()
        return

    output_file = render_digest(fresh_articles, out_path, timestamp_label)

    # Record run
    total_errors = sum(len(r.errors) for r in results)
    db.record_run(total_collected, total_errors)
    db.close()

    # Copy latest output to docs/ for GitHub Pages
    _publish_to_docs(output_file, out_path, timestamp_label)

    # Summary
    click.echo(
        f"\nDone! {len(fresh_articles)} articles published "
        f"({hidden_count} rehashes filtered, {total_collected} total collected)"
    )
    click.echo(f"Output: {output_file}")
    click.echo(f"Latest: docs/index.html")

    # Print per-site summary (based on what was collected, not published)
    for result in results:
        status = result.status.value.upper()
        site_new = sum(1 for a in result.articles if a.is_new)
        click.echo(
            f"  [{result.site_name}] {status}: "
            f"{len(result.articles)} collected / {site_new} new, "
            f"{len(result.errors)} errors"
        )


def _publish_to_docs(output_file: Path, output_dir: Path, timestamp_label: str) -> None:
    """Copy latest output to docs/ folder for GitHub Pages."""
    # Find project root (where .git or pyproject.toml lives)
    project_root = Path.cwd()
    docs_dir = project_root / "docs"

    # Clean and recreate docs/
    if docs_dir.exists():
        # Keep CNAME file if it exists
        cname_content = None
        cname_file = docs_dir / "CNAME"
        if cname_file.exists():
            cname_content = cname_file.read_text()
        shutil.rmtree(docs_dir)

    docs_dir.mkdir(parents=True, exist_ok=True)

    # Copy HTML as index.html, rewriting image paths
    html_content = output_file.read_text(encoding="utf-8")
    images_subdir = f"tonghoptin_{timestamp_label}_images"
    html_content = html_content.replace(f"{images_subdir}/", "images/")
    (docs_dir / "index.html").write_text(html_content, encoding="utf-8")

    # Copy images folder
    src_images = output_dir / images_subdir
    dst_images = docs_dir / "images"
    if src_images.exists():
        shutil.copytree(src_images, dst_images)

    # Write CNAME for custom domain
    (docs_dir / "CNAME").write_text("chuyenhay.com")

    # Write .nojekyll to disable Jekyll processing
    (docs_dir / ".nojekyll").write_text("")


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

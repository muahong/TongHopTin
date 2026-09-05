"""Reparse a captured response directory to recover cache after an interrupted run.

Usage: python scripts/recover_raw_cache.py output/raw/RUN_ID
Does not make network requests or modify original evidence.
"""
import gzip
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tonghoptin.cleaning import ContentCleaner
from tonghoptin.config import load_config
from tonghoptin.dedup import DedupDB
from tonghoptin.models import ArticleStub
from tonghoptin.models import Article
from tonghoptin.publication import publication_date
from tonghoptin.scrapers import get_scraper_class
from tonghoptin.vietnamese import now_vn


def recover(folder):
    config = load_config()
    sites = {site.domain.removeprefix("www."): site for site in config.sites}
    recovered = []
    count = errors = 0
    for path in Path(folder).glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        url = record["url"]
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        site = sites.get(host)
        if not site or url.endswith((".xml", ".rss", ".txt")):
            continue
        count += 1
        if count % 200 == 0:
            print(f"Examined {count} responses; recovered {len(recovered)} dated records", flush=True)
        try:
            html = gzip.decompress((Path(folder) / record["body"]).read_bytes()).decode("utf-8")
            if "<h1" not in html.lower():
                continue
            published = publication_date(html)
            if published and published.date() < now_vn().date():
                recovered.append(Article(url, url, site.domain, "Tin mới", published, "", ""))
                continue
            scraper = get_scraper_class(site.domain)(site, None, now_vn().date())
            article = scraper.parse_article_detail(html, ArticleStub(url, url, site.domain, "Tin mới"))
            article.published_date = published or article.published_date
            article.content_html, article.content_text = ContentCleaner(url).clean(article.content_html)
            if article.published_date and len(article.content_text.strip()) >= scraper.MIN_CONTENT_CHARS:
                from datetime import datetime
                from tonghoptin.vietnamese import to_vn_naive
                article.scraped_at = to_vn_naive(datetime.fromisoformat(record["captured_at"]))
                recovered.append(article)
        except Exception:
            errors += 1
    db = DedupDB(Path(config.output_directory) / "tonghoptin.db")
    try:
        db.save_content_cache(recovered)
    finally:
        db.close()
    result = {"raw_directory": str(folder), "responses_examined": count, "articles_recovered": len(recovered), "parse_errors": errors}
    destination = Path(config.output_directory) / "runs"
    destination.mkdir(exist_ok=True)
    (destination / (Path(folder).name + "-recovery.json")).write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    recover(Path(sys.argv[1]))

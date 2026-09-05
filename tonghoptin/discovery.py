"""Bounded supplementary discovery from publisher sitemaps (no search API)."""
from collections import deque
import re
from urllib.parse import urljoin, urlsplit

from lxml import etree

from tonghoptin.models import ArticleStub
from tonghoptin.vietnamese import parse_vietnamese_date


def same_site(url, domain):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").removeprefix("www.")
        return p.scheme in ("http", "https") and not p.username and host == domain.removeprefix("www.")
    except ValueError:
        return False


async def discover_sitemaps(scraper):
    cfg = scraper.config
    queue = deque()
    try:
        robots = await scraper.fetcher.fetch(urljoin(cfg.base_url, "/robots.txt"), delay=cfg.request_delay)
        queue.extend(re.findall(r"(?im)^Sitemap:\s*(https?://\S+)", robots))
    except Exception as exc:
        scraper.discovery.append({"url": cfg.base_url + "/robots.txt", "stop": "unavailable", "error": str(exc)})
    if not queue:
        queue.append(urljoin(cfg.base_url, "/sitemap.xml"))
    seen, stubs = set(), []
    while queue and len(seen) < cfg.max_sitemaps:
        url = queue.popleft()
        if re.search(r"(?:categories|topics|tags|authors)\b", url, re.I):
            scraper.discovery.append({"url": url, "stop": "non_article_sitemap"})
            continue
        if url in seen or not scraper.in_scope(url):
            continue
        seen.add(url)
        try:
            xml = await scraper.fetcher.fetch(url, delay=cfg.request_delay)
            root = etree.fromstring(xml.encode(), etree.XMLParser(resolve_entities=False, no_network=True))
            kind = etree.QName(root).localname
            if kind == "sitemapindex":
                children = []
                for item in root:
                    loc = item.findtext("{*}loc")
                    modified = parse_vietnamese_date(item.findtext("{*}lastmod") or "")
                    if loc and (not modified or modified.date() >= scraper.window_start):
                        children.append((loc, modified.isoformat() if modified else ""))
                children.sort(key=lambda x: ("news" in x[0].lower(), x[1]), reverse=True)
                queue.extendleft(loc for loc, _ in reversed(children))
            elif kind == "urlset":
                for item in root:
                    loc = item.findtext("{*}loc")
                    if not loc or not scraper.in_scope(loc):
                        continue
                    # lastmod is an update time, never evidence of publication.
                    publication = item.findtext(".//{*}publication_date")
                    pub = parse_vietnamese_date(publication or "")
                    modified = parse_vietnamese_date(item.findtext("{*}lastmod") or "")
                    if pub and not scraper.window_start <= pub.date() <= scraper.target_date:
                        continue
                    if not pub and modified and modified.date() < scraper.window_start:
                        continue
                    if not pub and not modified:
                        continue  # unbounded historical sitemap; report limitation below
                    title = item.findtext(".//{*}title") or loc.rsplit("/", 1)[-1]
                    stubs.append(ArticleStub(loc, title, cfg.domain, "Tin mới", published_date=pub))
            else:
                raise ValueError("Not a sitemap XML document")
            scraper.discovery.append({"url": url, "kind": kind, "stop": "read", "undated_entries": "detail verification required; entries without any dates skipped"})
        except Exception as exc:
            scraper.discovery.append({"url": url, "stop": "failed", "error": str(exc)})
    if queue:
        scraper.discovery.append({"stop": "sitemap_limit", "remaining": len(queue)})
    return stubs

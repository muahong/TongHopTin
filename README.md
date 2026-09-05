# Thông Tin Là Sức Mạnh!

Vietnamese news reader at https://chuyenhay.com, collecting from 19 enabled publisher configurations. A source reader and a **Toàn cảnh Việt Nam** overview show a day's collected news across politics, economics, society, culture, sports, world, technology, health, education and environment.

## Install and run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m tonghoptin.cli collect
run.bat
```

`collect` saves evidence locally and updates `docs/`. `run.bat` also backs up to the private archive repository and pushes the website. It never force-pushes or automatically resolves conflicts. A rejected push leaves the local data intact and exits with an error.

```powershell
python -m tonghoptin.cli collect --date 2026-09-05
python -m tonghoptin.cli collect --days 3
python -m tonghoptin.cli collect --since-last-run
```

Dates are Vietnam calendar dates (UTC+7). `--days N` includes exactly N days ending at `--date`, or today. Missing publication dates are reported; they are never replaced with the crawl time. `--since-last-run` includes calendar days since the last successful run, not an exact timestamp interval.

## Coverage and reader

RSS feeds, category pagination and bounded publisher sitemaps are combined. Earlier successful same-day discoveries remain available after feeds roll over. Cached bodies refresh after two hours; failures can retain the previous copy and are recorded. Category concurrency is bounded and requests remain rate limited per domain.

Coverage is **best effort, not exhaustive**. Paywalls, source outages, invalid markup, date-less entries, expired RSS entries, page limits and sitemap limits can leave gaps. The overview includes every accepted article from all collected sources, groups exact normalized titles and shows attributed extracts; it does not invent an editorial synthesis or assume similar headlines describe the same event. A date selector separates multi-day collections. Mobile uses an accessible category grid.

## Permanent history and GitHub

The website repository remains public to keep Pages online, as requested. The private backup repository is https://github.com/muahong/TongHopTin-archive . Privacy of a GitHub repository does not make a published Pages website private.

Clone the archive beside the code:

```powershell
git clone https://github.com/muahong/TongHopTin-archive.git archive
python -m tonghoptin.cli backup
python -m tonghoptin.cli verify-archive
```

The backup includes `output/`, `docs/` and crawler logs: timestamped HTML/Markdown, immutable article JSON/JS, images, SQLite cache/run history, structured run reports and raw response evidence. Browser history, browser profiles, credentials and cookies are excluded. Raw response evidence starts with the September 2026 revision; source responses that were never retained in the past cannot be recovered.

`archive/packs/` stores immutable ZIP packs below GitHub's file limit; large files are chunked. SHA-256 manifests retain all file versions; `index.json` and its small `index/` shards map each path to its latest archived version. Deleted local files remain in the archive index. Verify and restore using `tonghoptin.archive.restore`, as documented in the private archive README. The archive is never part of public Pages output.

`run.bat` pushes backup packs on every run, even after a collection error. The manual GitHub workflow uses a write deploy key restricted to the archive repository, saved as `ARCHIVE_DEPLOY_KEY`. Scheduled Actions remain disabled to preserve the existing minutes policy. Local startup scheduling remains unchanged. Concurrent archive pushes fail safely and require reconciliation; no automatic history rewrite is allowed.

All historical output and published dependencies are retained. `python scripts/export_html_history.py` exports historical Git-published HTML and its SHA-256 manifest. `python scripts/repair_archives.py` repairs older lazy-body archives. Never delete old sidecars merely to save space; monitor both repository and Pages storage as history grows.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pip-audit
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip_audit -r requirements.lock
node --check tonghoptin/templates/script.js
```

See `reports/2026-09-05-project-review.md` for findings, validation and remaining limits. Historical immutable HTML may contain old unsafe markup; view it only in an isolated browser. Newly generated readers sanitize bodies, escape metadata and restrict URL schemes. Raw HTML is private research evidence and must not be served as trusted application content.

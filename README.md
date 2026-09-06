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

Use the `.venv` interpreter above, or activate it before the shorter `python` examples below.

`collect` saves evidence locally and updates `docs/`. `run.bat` also backs up to the private archive repository and pushes the website. It never force-pushes or automatically resolves conflicts. A rejected push leaves the local data intact and exits with an error.

## Automatic runs on Windows

Two publication slots use Vietnam time (UTC+7): a morning run at the first Windows logon, with 09:00 as a daily fallback, and an evening run at 21:00. The existing `TongHopTin Startup` and `TongHopTin 9PM` tasks share a process lock and success markers; repeated logons and delayed triggers reuse the same slot. After 21:00, a logon joins the evening slot. Manual `run.bat` still forces a new run.

The tasks run hidden, can wake the computer from sleep, catch missed starts, and retry failures three times at 15-minute intervals. Windows must be running or able to wake, the user must remain signed in (screen lock is fine), and the network and ChatGPT/GitHub logins must work. A powered-off computer cannot publish; a long absence cannot recreate exact missed snapshots. These are local tasks, not Codex app automations or cloud cron jobs.

`tonghoptin.automation` freezes the crawl report per slot, reuses completed editorial batches and resumes backup/push/verification without recollecting. The full process has a shared lock; an overlapping invocation fails so Task Scheduler can retry it. Success requires the private archive push, website push, and a byte-for-byte live index plus sampled JSON/JS body and image check. A stale website or failed editorial pass remains a failure. Each stage has a timeout and a retained log. The scheduler allows four hours for the larger editorial pipeline.

Inspect or restore the schedule with:

```powershell
.\scripts\configure_schedule.ps1 -InspectOnly
.\scripts\configure_schedule.ps1
.\.venv\Scripts\python.exe -m tonghoptin.automation --trigger startup --check
```

Schedule changes first export the previous task XML into `output/automation/scheduler-backup-*`. Slot states and step logs are in `output/automation/`; each state includes coverage counts, attempts, failed step, and live verification evidence. Run `run.bat --trigger startup` to retry the current slot. For a crawl that failed before this runner was introduced, add `--resume-report output/runs/<report>.json`; this reuses the selected evidence. No historical files are deleted.

```powershell
python -m tonghoptin.cli collect --date 2026-09-05
python -m tonghoptin.cli collect --days 3
python -m tonghoptin.cli collect --since-last-run
```

Dates are Vietnam calendar dates (UTC+7). `--days N` includes exactly N days ending at `--date`, or today. Missing publication dates are reported; they are never replaced with the crawl time. `--since-last-run` includes calendar days since the last successful run, not an exact timestamp interval.

## Coverage and reader

RSS feeds, category pagination and bounded publisher sitemaps are combined. Earlier successful same-day discoveries remain available after feeds roll over. Cached bodies refresh after two hours; failures can retain the previous copy and are recorded. Category concurrency is bounded and requests remain rate limited per domain.

Coverage is **best effort, not exhaustive**. Paywalls, source outages, invalid markup, date-less entries, expired RSS entries, page limits and sitemap limits can leave gaps. The default **Toàn cảnh Việt Nam** view groups overlapping coverage into source-traceable editorial stories, arranged in a continuous category tree with an 11-category directory, search and an optional headlines-only mode. Each story opens its rewritten text with paragraph-level source buttons and links to all original articles; closing the reader preserves the page position. `#news` opens the original source reader. Dates without a matching editorial edition display clearly labeled source extracts.

The editorial job uses **Codex CLI authenticated with ChatGPT**, never a separately billed LLM API or API key. GPT-5.5 groups related events; GPT-5.4-mini rewrites from the full collected bodies. This uses the account's Codex allowance. The tone is warm and lightly witty where appropriate; sensitive news stays sober. Run `.venv\Scripts\python.exe scripts/build_editorial.py <run-report.json> --publish` to generate and locally publish a day, or omit the report to use the latest crawl. `run.bat` performs this step before backup and GitHub publication. GitHub Actions can collect source news but does not receive the desktop's ChatGPT credentials or run this editorial step.

Each source ID must occur exactly once across the edition and be cited by its story's paragraphs. Source-content fingerprints prevent applying stale copy to changed articles. Validated editions live in `editorial/<day>/<fingerprint>.json`; prompts, CLI logs and intermediate results stay in `output/editorial/` and are included in the private archive. Completed batches are reused on retry. Structural validation checks completeness and provenance references; it is not a guarantee of factual editorial correctness.

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

`run.bat` pushes backup packs on every new run, even after a collection error. The manual GitHub workflow uses a write deploy key restricted to the archive repository, saved as `ARCHIVE_DEPLOY_KEY`. Scheduled Actions remain disabled to preserve the existing minutes policy. Local scheduling is described above. Concurrent archive pushes fail safely and require reconciliation; no automatic history rewrite is allowed.

All historical output and published dependencies are retained. `python scripts/export_html_history.py` exports historical Git-published HTML and its SHA-256 manifest. `python scripts/repair_archives.py` repairs older lazy-body archives. Never delete old sidecars merely to save space; monitor both repository and Pages storage as history grows.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pip-audit
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip_audit -r requirements.lock
node --check tonghoptin/templates/script.js
```

See `reports/2026-09-05-project-review.md` for findings, validation and remaining limits. Historical immutable HTML may contain old unsafe markup; view it only in an isolated browser. Newly generated readers sanitize bodies, escape metadata and restrict URL schemes. Raw HTML is private research evidence and must not be served as trusted application content.

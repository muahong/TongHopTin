# TongHopTin review — 5 September 2026

## Scope and decisions

Reviewed the crawler, all scraper adapters, date parsing, cache/deduplication, HTML reader, archive retention, publication scripts, dependencies and GitHub configuration. Existing uncommitted archive-repair work was retained and incorporated. No historical content was intentionally deleted and no remote Git history was rewritten.

The user prioritized keeping chuyenhay.com online. GitHub admin access is available, but the account plan could not be determined. The Pages repository therefore remains public. A separate private repository, `muahong/TongHopTin-archive`, holds the full crawl backup; a restricted deploy key permits the existing manual Actions workflow to update it. HTTPS enforcement was enabled for chuyenhay.com.

## Findings and changes

| Finding | Change |
| --- | --- |
| Unescaped scraped metadata in HTML/attributes and JSON script elements | Enable template autoescaping, escape script-closing characters and attribute values; regression test malicious titles/categories |
| Active URL schemes and unexpected HTML elements could survive body cleaning | HTTP(S) URL validation and allowed-element/attribute sanitization, including cached content and rendering |
| Network fetches could reach local services through URLs or DNS | Public-address resolver, scheme/port/credential validation, redirect validation and browser request checks |
| Unbounded response downloads and expensive images/browser pages | Streamed 12 MiB response cap, image pixel cap, four browser slots and off-loop image processing |
| Missing browser installation and repeated failed launches | Install the locked Chromium runtime and close Playwright after failed launches |
| ISO date parser discarded timezone offsets | Parse full ISO timestamps and normalize to Vietnam time, including midnight boundary tests |
| Today collection included yesterday and tomorrow; multi-day semantics were wrong | Exact inclusive Vietnam dates, `--date`, `--days`, and documented calendar-based `--since-last-run` |
| Missing publication dates became today's timestamp | Preserve unknown dates as failures; use publisher metadata/JSON-LD where available |
| RSS rollover lost stories found earlier that day | Merge same-day cached discoveries into each source's candidate set |
| Indefinitely reused cached bodies hid updates | Two-hour freshness, with reported use of a previous copy on refresh failure |
| RSS/homepage-only discovery missed sections | Supplement feeds/listings with homepage discovery and bounded dated publisher sitemaps |
| Navigation pages and broad extraction produced missing or unrelated bodies | Tighter URL checks; prioritized RSS body selectors; observed containers for finance, Mekong ASEAN and generic sites |
| Slow categories blocked a whole site and some sources ran indefinitely | Stream detail work as listings arrive, use three listing workers and eight off-loop parser slots, enforce per-domain rate limits and ten-minute per-source budgets retaining completed work |
| Query-string removal merged different article IDs | Remove tracking parameters only, preserving identity parameters and case-sensitive paths |
| Freshness dedup silently hid source versions | Retain all accepted URLs; group matching titles only in overview |
| Full text could be lost when a crawl failed or a cache entry expired | Save raw response bodies and metadata, structured run reports, discovery outcomes, errors and parsed article records |
| Publisher redirect could be mislabeled as original source | Record final URLs and reject cross-publisher article redirects. PLO, NLD and Saigon Times now redirect to a personalized Tuoi Tre page; that page cannot establish original-publisher coverage |
| Publishing removed old dependencies before writing the new index | Retain historical assets and publish dependencies before atomic index replacement |
| Force-push conflict handling could erase valuable remote history | Stop safely on conflicts; never force-push or automatically pick a winner |
| Local history ignored by Git and cache TTL mistaken for backup | Private immutable ZIP packs, SHA-256 manifests, sharded indexes, restore and verification commands |
| Floating old dependencies included known-risk versions | Isolated environment, locked runtime dependencies; 25 packages audited with zero known vulnerabilities reported |
| No regression gate in CI | Add read-only validation workflow and archive preservation to manual collection workflow |

## Reader

Added **Toàn cảnh Việt Nam**, linked directly by `#overview`. Desktop shows a circular map of eleven categories; mobile uses a two-column category grid. Each day is kept separate. Selecting a category shows short source-derived extracts, every grouped source version, search, incremental loading and full-article reading. Modal keyboard focus, Escape, focus return and reduced-motion support are included.

The overview is a deterministic overview of collected reporting, not an invented editorial narrative. Exact normalized-title grouping does not establish that differently titled articles are the same event. Rule-based category assignment can be imperfect.

## Historical preservation

- Recovered 964 deleted published dependencies from the existing Git index.
- Materialized and checked the existing exporter output for 313 historical published HTML versions, from April through August 2026.
- Pre-backup inventory: 271,472 output files / 6,329,757,963 bytes, plus 1,912 published files / 56,668,958 bytes. Counts change as new evidence is saved.
- Existing Git object storage is approximately 9.78 GiB. That history remains in the website repository; it is not repacked or discarded in this change.
- Private backup includes all available local output and published assets, logs and SQLite, with all subsequent versions retained. Indexes and manifests are sharded to avoid oversized GitHub files.
- The first exploratory crawl was interrupted after identifying runtime and extraction issues. Its raw responses were retained and reparsed with `scripts/recover_raw_cache.py` before final validation.

## Validation

- 62 regression tests passed in the isolated locked environment.
- JavaScript syntax check passed.
- Initial desktop/mobile browser checks passed: no JavaScript errors, eleven category buttons, no mobile horizontal overflow.
- Dependency audit: `reports/dependency-audit-2026-09-05.json` (25 runtime packages, zero known vulnerabilities).
- Local historical reader audit: 82 HTML archives, 86,449 article references, zero missing bodies and zero metadata parse errors (`reports/local-history-validation-2026-09-05.json`).
- Initial browser validation on 665 collected articles: eleven categories, article modal loads, no JavaScript errors and no mobile horizontal overflow.
- Final crawl and archival results are recorded in the accompanying JSON reports.

## Limits and operation

Coverage remains best effort. Feeds can expire, sitemap indexes can be incomplete or undated, source sites may be unavailable or redirect, and paywalled or image-only articles may not yield readable text. Missing, thin, out-of-window and failed articles are recorded; source failures do not imply that no news was published. A ten-minute source budget may leave additional candidates unprocessed and is visible in the report.

Raw evidence starts with this revision. Past responses never saved cannot be reconstructed. Older immutable HTML is retained exactly and may lack current sanitization; inspect it only in an isolated browser. Browser-route DNS checks reduce local-target risk but are not a general browser sandbox; the crawler should run without privileged network access.

The private archive does not make the public reader or its existing Git history private. Making the source repository private is deferred until private Pages support is confirmed or hosting is migrated without downtime. GitHub Pages availability and visibility implications: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility .

Scheduled GitHub crawls remain disabled under the existing minutes policy; the manual workflow and local run script perform backups. Rejected concurrent pushes require reconciliation and preserve local data. Disk, GitHub storage and Pages capacity need monitoring as history grows; this implementation never solves capacity pressure by deleting history.

## Release crawl

The final validation crawl collected 829 retained articles from 15 of 19 configured sources for 2026-09-05. Four returned no usable articles: VN Business Insider, NLD, PLO and Saigon Times. Partial-source outcomes include timeouts, missing bodies and navigation links; the last finance-link filter eliminates the observed non-article `.chn` requests on subsequent runs. Original publisher URLs are retained for the three redirecting sources to avoid assigning personalized Tuoi Tre recommendations to them.

All 829 published article JSON and JavaScript dependencies exist. The released overview passed desktop/mobile interaction checks with no JavaScript errors, eleven category controls, readable Vietnamese headline accents and no horizontal overflow. See `live-crawl-2026-09-05.json` and `reader-validation-2026-09-05.json`.

## Live verification

Release `cb315c31e2effc9cbd9ffc3d8b4cfb90e45477fd` passed GitHub CI and Pages deployment. HTTPS returned 200; the live HTML matches the local release after Git line-ending normalization, and a live article body matches its local sidecar. The public browser checks passed again. See `live-deployment-2026-09-05.json`.

Browser captures: [desktop](overview-desktop-2026-09-05.png), [mobile](overview-mobile-2026-09-05.png).

Archive verification now checks path traversal without resolving every nonexistent destination path. Extraction still resolves paths to prevent symlink escapes; the added traversal regression passes.

## Completed private archive

Verified 289,419 latest retained file paths across 194 immutable packs (3,225,072,385 bytes). Every recorded pack SHA-256 passed; an independently restored historical article matches its local original. SQLite quick_check returned ok. All packs and version manifests are uploaded to the private archive repository at commit `044a93912a3c320b99f44e01e6dba4aa1c2c01b0`, with the remote commit verified. See `archive-validation-2026-09-05.json` and `archive-upload-2026-09-05.json`.

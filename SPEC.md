# TongHopTin - Normative Specification

**Version**: 1.0.0
**Language**: Python 3.11+
**Type**: Async CLI application

---

## 1. Purpose

TongHopTin ("tong hop tin" = aggregate information) is a Vietnamese news aggregation tool that:

1. Reads browser history from Chrome/Brave SQLite database files to identify favourite sites
2. Scrapes those sites using site-specific scraper classes
3. Follows pagination to collect ALL articles published on a target date
4. Extracts full article content, metadata, and images
5. Tags articles with Vietnamese topic categories
6. Tracks seen articles via a local SQLite database
7. Generates a self-contained HTML digest with interactive filtering

---

## 2. Architecture Overview

```
CLI (click)
  │
  ├── init ──────► history.py ──► Analyze Chrome/Brave SQLite ──► Generate config.yaml
  │
  ├── collect ──► CrawlOrchestrator ──► asyncio.gather(scrapers) ──► DedupDB ──► Renderer ──► HTML
  │                     │
  │                     ├── VnExpressScraper
  │                     ├── TuoiTreScraper
  │                     ├── ThanhNienScraper
  │                     ├── DanTriScraper
  │                     ├── VietnamNetScraper
  │                     └── GenericScraper
  │
  └── favourites ──► config.py ──► Read/write config.yaml
```

All site scrapers inherit from `BaseScraper` and are registered in `SCRAPER_REGISTRY` by domain.
The `Fetcher` provides async HTTP (aiohttp) and headless browser (Playwright) capabilities.

---

## 3. Data Models (`models.py`)

### 3.1 Enumerations

| Enum | Values |
|------|--------|
| `FetchMethod` | `REQUESTS`, `PLAYWRIGHT` |
| `CrawlStatus` | `SUCCESS`, `PARTIAL`, `FAILED` |

### 3.2 ArticleStub

Lightweight reference discovered from listing pages. Used in Phase 1 (discovery).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Article URL |
| `title` | `str` | required | Article title |
| `source_site` | `str` | required | Domain name (e.g., "vnexpress.net") |
| `source_category` | `str` | required | Category label from source site |
| `thumbnail_url` | `Optional[str]` | `None` | Thumbnail image URL |
| `published_date` | `Optional[datetime]` | `None` | Publication date if parseable from listing |

### 3.3 Article

Full article with extracted content. Produced in Phase 2 (detail extraction).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | required | Article URL |
| `title` | `str` | required | Article title |
| `source_site` | `str` | required | Domain name |
| `source_category` | `str` | required | Category from source site |
| `published_date` | `datetime` | required | Publication datetime |
| `content_html` | `str` | required | Cleaned HTML body |
| `content_text` | `str` | required | Plain text (for reading time and search) |
| `author` | `Optional[str]` | `None` | Author name |
| `hero_image_url` | `Optional[str]` | `None` | Original image URL |
| `hero_image_path` | `Optional[str]` | `None` | Local path relative to output dir |
| `estimated_reading_time_minutes` | `int` | `0` | Calculated as `len(content_text) // 1000`, min 1 |
| `topics` | `list[str]` | `[]` | Vietnamese keyword topic tags |
| `is_new` | `bool` | `True` | False if previously seen in dedup DB |
| `scraped_at` | `datetime` | `now()` | Scrape timestamp |

**Computed properties:**
- `preview_text`: First 2-3 sentences (splits on ". ", "! ", "? ") or first 300 chars
- `url_hash`: 12-char MD5 hex digest of URL (used for image filenames and dedup)

### 3.4 SiteCrawlResult

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `site_name` | `str` | required | Site identifier |
| `status` | `CrawlStatus` | required | SUCCESS, PARTIAL, or FAILED |
| `articles` | `list[Article]` | `[]` | Collected articles |
| `errors` | `list[dict]` | `[]` | Error records `{url, error, phase, timestamp}` |
| `stubs_discovered` | `int` | `0` | Total unique stubs found |
| `stubs_filtered` | `int` | `0` | Stubs excluded (wrong date, paywall) |
| `duration_seconds` | `float` | `0.0` | Total crawl duration |

### 3.5 SiteConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Display name |
| `base_url` | `str` | required | Site base URL |
| `domain` | `str` | auto from `base_url` | Domain extracted via `urlparse` |
| `enabled` | `bool` | `True` | Whether to crawl this site |
| `fetch_method` | `FetchMethod` | `REQUESTS` | HTTP method to use |
| `request_delay` | `float` | `1.0` | Seconds between requests per domain |
| `max_pages` | `int` | `10` | Max pagination depth per category |
| `max_concurrent` | `int` | `5` | Max concurrent article detail fetches |
| `categories` | `list[str]` | `[]` | Category URL paths (unused; hardcoded per scraper) |

### 3.6 AppConfig

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `chrome_history_path` | `str` | `""` | Path to Chrome History SQLite file |
| `brave_history_path` | `str` | `""` | Path to Brave History SQLite file |
| `analysis_days` | `int` | `30` | Days of history to analyze |
| `auto_detect_threshold` | `int` | `5` | Min visits to suggest as favourite |
| `sites` | `list[SiteConfig]` | `[]` | Configured sites |
| `output_directory` | `str` | `"./output"` | Output directory path |
| `embed_images` | `bool` | `False` | If True, base64-embed (unused; always separate folder) |
| `image_max_width` | `int` | `800` | Max image width in pixels |
| `theme` | `str` | `"auto"` | Theme: "light", "dark", or "auto" |
| `target_days` | `int` | `1` | Days to collect (1 = today) |
| `user_agent` | `str` | `"TongHopTin/1.0 (...)"` | HTTP User-Agent header |

---

## 4. Crawling Engine

### 4.1 Scraper Registry (`scrapers/__init__.py`)

A global `SCRAPER_REGISTRY: dict[str, type[BaseScraper]]` maps domain strings to scraper classes.

- `@register_scraper(*domains)` decorator registers a class for one or more domains
- `get_scraper_class(domain)` returns the registered class or `GenericScraper` as fallback
- All scraper modules are imported at package init to trigger registration

### 4.2 BaseScraper (`scrapers/base.py`)

Abstract base class providing the two-phase crawl orchestration loop.

**Constructor**: `(config: SiteConfig, fetcher: Fetcher, target_date: date)`

**Abstract methods** (subclasses MUST implement):

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_category_urls` | `() -> list[tuple[str, str]]` | Return `(url, category_name)` pairs |
| `parse_article_listing` | `(html, category) -> list[ArticleStub]` | Parse listing page into stubs |
| `get_next_page_url` | `(html, current_url) -> Optional[str]` | Return next page URL or None |
| `parse_article_detail` | `(html, stub) -> Article` | Parse detail page into Article |
| `extract_hero_image_url` | `(html) -> Optional[str]` | Extract main image URL |

**Optional override**: `is_paywall(html) -> bool` (default: `False`)

**Crawl pipeline** (`crawl() -> SiteCrawlResult`):

```
Phase 1 - Stub Discovery:
  For each category URL:
    page = 0
    While page < max_pages:
      Fetch listing page
      Parse into ArticleStubs
      Classify stubs: today / older / unknown-date
      Keep today + unknown stubs
      If ALL stubs are older than target_date: stop
      Get next page URL; if None: stop
      page++

  Deduplicate stubs by URL

Phase 2 - Detail Extraction:
  For each unique stub (concurrent, semaphore-bounded):
    Fetch article detail page
    Check paywall -> skip if True
    Parse into Article
    Clean content HTML via ContentCleaner
    Recalculate reading time from cleaned content_text
    Extract hero image URL

  Filter articles: keep only those with published_date == target_date
  Return SiteCrawlResult
```

**Error handling**: Per-article try/except. Errors recorded as `{url, error, phase, timestamp}`.

### 4.3 Concrete Scrapers

#### VnExpress (`vnexpress.net`)

| Property | Value |
|----------|-------|
| Fetch method | `requests` (aiohttp) |
| Categories | 11: Thoi su, The gioi, Kinh doanh, Giai tri, The thao, Phap luat, Giao duc, Suc khoe, Doi song, Khoa hoc, So hoa |
| Listing selector | `article.item-news` -> `h3.title-news a` or `h2.title-news a` |
| Date selector (listing) | `span.time-public, span.date, span.time` |
| Pagination pattern | `/{category}-p{N}` (e.g., `/thoi-su-p2`) |
| Detail title | `h1.title-detail` |
| Detail date | `span.date` (format: "Thu Bay, 04/04/2026, 10:30 (GMT+7)") |
| Detail author | `p.author_mail strong, span.author` |
| Detail body | `article.fck_detail` |
| Hero image | `meta[property="og:image"]` or first `img` in body |

#### Tuoi Tre (`tuoitre.vn`)

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 14: Thoi su, The gioi, Phap luat, Kinh doanh, Cong nghe, Xe, Nhip song tre, Van hoa, Giai tri, The thao, Giao duc, Khoa hoc, Suc khoe, Du lich |
| Listing selector | `li.news-item, div.box-category-item, article` -> `a.box-category-link-title, h3 a, h2 a` |
| Pagination pattern | `/{category}/trang-{N}.htm` |
| Detail title | `h1.article-title, h1.detail-title` |
| Detail body | `div#main-detail-body, div.detail-content` |

#### Thanh Nien (`thanhnien.vn`)

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 13: Thoi su, The gioi, Kinh te, Doi song, Suc khoe, Gioi tre, Giao duc, Du lich, Van hoa, Giai tri, The thao, Cong nghe, Xe |
| Listing selector | `div.box-category-item, article.story` -> `a.box-category-link-title, h3 a` |
| Pagination pattern | `?page={N}` query parameter |
| Detail title | `h1.detail__title` |
| Detail body | `div.detail__content` |

#### Dan Tri (`dantri.com.vn`)

| Property | Value |
|----------|-------|
| Fetch method | **`playwright`** (JS-heavy site) |
| Categories | 17: Xa hoi, The gioi, Kinh doanh, Bat dong san, The thao, Lao dong, Tam long nhan ai, Suc khoe, Giao duc, An sinh, Phap luat, Doi song, Van hoa, Giai tri, Suc manh so, O to xe may, Du lich |
| Listing selector | `article, div.article-item, h3.article-title` -> `h3 a, h2 a` |
| Pagination pattern | `/{category}/trang-{N}.htm` |
| Detail title | `h1.title-page` |
| Detail body | `div.singular-content, div.detail-content` |

#### VietnamNet (`vietnamnet.vn`)

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 14: Thoi su, Chinh tri, The gioi, Kinh doanh, Giao duc, Doi song, Suc khoe, Giai tri, The thao, Cong nghe, Oto xe may, Bat dong san, Du lich, Phap luat |
| Discovery | **Dual method**: (1) JSON regex from `Countly.q.push()` script blocks; (2) DOM parsing as fallback |
| Listing selector (DOM) | `div.horizontalPost, div.verticalPost, article` -> `a.vnn-title, h3 a` |
| Pagination pattern | `?page={N}` query parameter |
| Detail title | `h1.content-detail-title` |
| Detail body | `div.maincontent, div.content-detail-body` |

#### CafeF (`cafef.vn`) — Finance/Stock News

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 6: Thi truong chung khoan, Bat dong san, Tai chinh ngan hang, Vi mo dau tu, Doanh nghiep, Tai chinh quoc te |
| URL pattern | `/{slug}.chn` |
| Listing selector | `.tlitem h3 a` for title+link, `.tlitem .time_cate` for date |
| Pagination | AJAX-based; scraper uses category page with `?page=N` fallback |
| Detail extraction | JSON-LD `NewsArticle` schema (primary), `h1` title, `[data-role="content"]` body (fallback) |
| Hero image | `meta[property="og:image"]` |

#### CafeBiz (`cafebiz.vn`) — Business News

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 5: Cau chuyen kinh doanh, Cong nghe, Vi mo, Bizmoney, CEO Circle |
| URL pattern | `/{slug}.chn` |
| Listing selector | `.listtimeline ul li h3 a`, `.cfbiznews_box .cfbiznews_title a` |
| Pagination | Traditional `.page ul li.next a` links |
| Detail extraction | JSON-LD `NewsArticle` (primary), `.detail-content` body (fallback) |
| Hero image | `meta[property="og:image"]` |

#### VietnamBusinessInsider (`vietnambusinessinsider.vn`) — Business Analysis

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | 1: Featured (noi-bat) |
| URL pattern | `/{slug}-a{id}.html` |
| Listing selector | `.item-news .title a`, `.box-news .title a` |
| Pagination | `?page={N}` query parameter |
| Detail extraction | JSON-LD `NewsArticle` (primary), `.the-article-body` body (fallback) |
| Hero image | JSON-LD `image` or `meta[property="og:image"]` |

### 4.3.1 Interest-Based Scoring (`vietnamese.py`)

Articles are scored based on the user's reading interest keywords:

**`score_article(title, content_text) -> float`**

Keyword weight tiers:
- **High (3.0)**: Trump, dau, xang, dien, kinh te, AI, USD, ngan hang, lai suat, Trung Quoc
- **Medium (2.0)**: vang, thue, xuat khau, nhap khau, VinFast, EV, chung khoan, bat dong san, GDP
- **Low (1.0)**: cong nghe, startup, robot, blockchain, ung thu, giao thong

Score = sum of matched keyword weights. Searches `title + content_text[:500]`, case-insensitive.

### 4.3.2 Freshness Detection and Prioritization

Some sites republish old articles with a fresh date to game traffic. The scoring system detects and penalizes these "recycled" articles while boosting genuinely new content.

**`compute_freshness_penalty(article) -> float`**

Detection signals (any match triggers penalty):
- **URL date mismatch**: Article URL contains a date pattern (e.g., `/2026/03/15/`) that is older than the claimed `published_date` → penalty -10.0
- **Previously seen**: Article URL exists in the dedup database from a prior run (same article re-scraped) → penalty -5.0
- **Very short content**: `content_text` < 200 characters (stub/teaser, likely recycled headline) → penalty -3.0

**Freshness bonus** for genuinely new articles:
- Published within the last 3 hours → bonus +4.0
- Published within the last 6 hours → bonus +2.0

**Final score** = `interest_score + freshness_adjustment`

Default sort: **Final score descending, then published_date descending**.
Sort toggle in filter bar: "Phu hop nhat" (Best match) vs "Moi nhat" (Newest first).

#### Generic Scraper (fallback for unknown sites)

| Property | Value |
|----------|-------|
| Fetch method | `requests` |
| Categories | Homepage only ("Trang chu") |
| Pagination | **None** (single page) |
| Discovery | Homepage link analysis with heuristics: URL contains date patterns (`/2026/04/`), long hyphenated slugs (>20 chars, 3+ hyphens), or `.html/.htm` extensions |
| Extraction | `readability-lxml` library (`Document(html).summary()`) |
| Date extraction | `meta[property="article:published_time"]` -> `time[datetime]` -> `<time>` text |
| Hero image | `meta[property="og:image"]` |

### 4.4 Fetcher (`fetcher.py`)

Async HTTP client with rate limiting, retries, and Playwright fallback.

**Constructor**: `(user_agent, max_retries=3, timeout_seconds=30)`

**Default HTTP headers**:
```
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7
Accept-Encoding: gzip, deflate
Connection: keep-alive
```

**fetch(url, method, delay) -> str**:
- Per-domain lock + rate limiting (configurable delay between requests)
- aiohttp for `REQUESTS` method; Playwright headless Chromium for `PLAYWRIGHT`
- Retries on transient errors: HTTP 429, 500, 502, 503, 504; `TimeoutError`; `ClientConnectionError`
- Exponential backoff: `2^attempt` seconds, up to `max_retries` attempts
- Non-transient errors (403, 404) fail immediately

**download_image(url, output_dir, filename, max_width) -> Optional[str]**:
- Downloads image via aiohttp
- Converts RGBA/P mode to RGB
- Resizes to max_width maintaining aspect ratio (Lanczos resampling)
- Saves as JPEG (quality=80, optimized) to `output_dir/images/{filename}.jpg`
- Returns relative path `images/{filename}.jpg` or None on failure

**Lazy initialization**:
- aiohttp session created on first `fetch()` call
- Playwright browser created on first `PLAYWRIGHT` fetch

### 4.5 Content Cleaning (`cleaning.py`)

HTML sanitization pipeline via `ContentCleaner(base_url)`.

**`clean(html) -> (cleaned_html, plain_text)`**

Pipeline stages (in order):
1. **Remove unwanted tags**: `script, style, iframe, form, nav, aside, footer, header, noscript, svg, button, input, select, textarea`
2. **Remove clutter**: CSS selectors for `.related`, `.social-share`, `.ads`, `.comments`, `.author-info`, `.breadcrumb`, `.banner`, `.popup`, `.newsletter`, `.tags-container`, and `[class*='quangcao']`
3. **Normalize images**: Convert `data-src`, `data-original`, `data-lazy-src` to `src`; remove 1x1 tracking pixels
4. **Strip attributes**: Keep only `src`, `href`, `alt`, `title`
5. **Remove empty containers**: `div, span, p, section` with no text and no `img/video/picture` children
6. **Absolutize URLs**: Convert relative `href`/`src` to absolute using `base_url`

Plain text extracted via `soup.get_text(separator=" ", strip=True)` with whitespace normalized.

---

## 5. Vietnamese Language Support (`vietnamese.py`)

### 5.1 Date Parsing

`parse_vietnamese_date(text, reference=None) -> Optional[datetime]`

Vietnamese dates use **DD/MM/YYYY** (day-first). Parsing order:
1. ISO 8601 in `<time datetime="...">` format
2. Relative expressions:
   - `{N} phut truoc` (N minutes ago)
   - `{N} gio truoc` (N hours ago)
   - `{N} ngay truoc` (N days ago)
   - `Hom nay` (today)
   - `Hom qua` (yesterday)
3. Absolute patterns (most specific first):
   - `"Thu Bay, 04/04/2026, 10:30 (GMT+7)"` — weekday + DD/MM/YYYY + HH:MM
   - `"04/04/2026"` — DD/MM/YYYY date only
   - `"3 thang 4, 2026"` / `"3 thang 4 nam 2026"` — written Vietnamese
   - `"2026-04-04T10:30:00"` — ISO with time
   - `"2026-04-04"` — ISO date only

Weekday prefix pattern: `Thu Hai, Thu Ba, Thu Tu, Thu Nam, Thu Sau, Thu Bay, Chu Nhat`

### 5.2 Topic Tagging

`tag_article_topics(title, content_text) -> list[str]`

Searches `title + content_text[:500]` (lowercased) against keyword dictionaries. Articles can have multiple topics.

| Topic | Sample Keywords |
|-------|----------------|
| Chinh tri | quoc hoi, chinh phu, dang, bo truong, thu tuong, tong bi thu, dai bieu, nghi quyet |
| Kinh te | GDP, lam phat, chung khoan, ngan hang, xuat khau, doanh nghiep, bat dong san, lai suat, ty gia, thue |
| Xa hoi | dan sinh, giao thong, tai nan, moi truong, dan cu, an sinh, do thi |
| Cong nghe | AI, tri tue nhan tao, smartphone, ung dung, bao mat, internet, phan mem, chip, robot, blockchain, 5G |
| Giao duc | hoc sinh, sinh vien, dai hoc, thi, diem chuan, giao vien, truong, tuyen sinh, hoc phi |
| Y te | benh vien, bac si, dich benh, vaccine, suc khoe, thuoc, phau thuat, ung thu, COVID |
| The thao | bong da, SEA Games, Olympic, V-League, doi tuyen, World Cup, cau thu, HLV, giai dau, tennis |
| Giai tri | phim, ca si, nghe si, gameshow, am nhac, dien vien, MV, showbiz, dien anh |
| Quoc te | My, Trung Quoc, Nga, Ukraine, ASEAN, Lien Hop Quoc, NATO, EU, Nhat Ban, Han Quoc, ngoai giao |
| Phap luat | toi pham, bat giu, xet xu, toa an, cong an, khoi to, truy to, vi pham, hinh su |

Default tag if no keywords match: `"Khac"` (Other).

---

## 6. Crawl Orchestration (`orchestrator.py`)

`CrawlOrchestrator(config: AppConfig, target_date, output_dir)`

**`run() -> (list[Article], list[SiteCrawlResult])`**:

1. Filter enabled sites from config
2. For each site, resolve scraper class via `get_scraper_class(domain)`
3. Run all scrapers concurrently via `asyncio.gather()`
4. Per-site error isolation: exceptions produce `FAILED` SiteCrawlResult
5. Deduplicate articles across sites by normalized URL (lowercase, trailing slash stripped)
6. Apply Vietnamese topic tags to all articles
7. Download hero images concurrently
8. Sort articles by `published_date` descending
9. Close fetcher
10. Return `(articles, results)`

---

## 7. Deduplication (`dedup.py`)

`DedupDB(db_path="tonghoptin.db")`

**SQLite schema**:

```sql
CREATE TABLE seen_articles (
    url TEXT PRIMARY KEY,
    title TEXT,
    source_site TEXT,
    first_seen TEXT,  -- ISO datetime
    last_seen TEXT    -- ISO datetime
);

CREATE TABLE run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_time TEXT,        -- ISO datetime
    articles_count INTEGER,
    errors_count INTEGER
);
```

**Methods**:
- `mark_articles(articles)`: Sets `article.is_new = False` for previously seen URLs; inserts new URLs; updates `last_seen` for existing
- `record_run(articles_count, errors_count)`: Records crawl run
- `get_last_run_time() -> Optional[datetime]`: Returns last run timestamp (for `--since-last-run`)

---

## 8. Browser History Analysis (`history.py`)

**`read_browser_history(history_path, days=30) -> list[DomainStats]`**:
- Copies History SQLite file to temp (Chrome locks the original)
- Queries `urls` JOIN `visits` tables
- Chrome timestamps: microseconds since 1601-01-01 (converted to Unix epoch)
- Filters out: empty domains, google.com, facebook.com, youtube.com, github.com, localhost
- Aggregates by domain: visit count, unique URLs, last visit, sample titles (up to 5)
- Returns sorted by visit count descending

**`DomainStats`**: `domain, visit_count, unique_urls, last_visit, sample_titles`

**`suggest_favourites(stats, threshold=5)`**: Filters domains with `visit_count >= threshold`

**`merge_history_sources(*paths, days=30)`**: Merges multiple browser history files, aggregating stats per domain

---

## 9. HTML Output (`renderer.py` + `templates/`)

### 9.1 Renderer

`render_digest(articles, output_dir, date_str) -> Path`

- Groups articles by `source_site` into `SourceGroup` objects (sorted by count descending)
- Counts topic occurrences
- Loads `style.css` and `script.js` as inline strings
- Renders `digest.html` Jinja2 template
- Writes `tonghoptin_{date_str}.html` to output_dir
- `SourceGroup.name`: first segment of domain, capitalized

### 9.2 HTML Template (`digest.html`)

Structure:
1. **Header**: Title "TongHopTin", date, stats bar (total articles, new articles, sources, generation time)
2. **Filter bar**: Search input, source filter pills (one per site + "Tat ca"), topic filter pills (one per topic), dark mode toggle. Source and topic pills are toggleable — clicking one filters the view, clicking again (or "Tat ca") shows all.
3. **Single flat card grid**: ALL articles from ALL sources in one unified grid, sorted by `published_date` descending. No per-source section grouping. Each card shows its source domain in the meta line so the reader knows which site it came from.
4. **Article cards**: Image (clickable), meta (source name + category + time), title (clickable, opens reading modal) with small external link icon, "MOI" badge, topic tags, preview text (clickable), footer (author + reading time). Clicking the thumbnail, title, or preview text all open the reading modal.
5. **Reading modal**: Full-page scrollable overlay for reading articles locally
6. **Article data block**: `<script type="application/json" id="articles-data">` containing full article content keyed by `url_hash`
7. **Load more button**: Shows remaining count
8. **Back-to-top button**: Fixed bottom-right button, appears when scrolled down >300px, smooth-scrolls to page top
9. **Footer**: Generation timestamp + totals

**Default view**: All articles from all sources, newest first. No grouping by source.

**Filter bar behavior**:
- **Source pills**: "Tat ca" (All) is active by default. Clicking a source name shows only that source's articles. Clicking it again or "Tat ca" returns to all sources. Only one source active at a time.
- **Topic pills**: "Tat ca" (All) is active by default. Clicking a topic shows only articles tagged with that topic. Clicking it again or "Tat ca" returns to all topics. Only one topic active at a time.
- **Source + Topic**: Both filters can be active simultaneously (intersection). E.g., "VnExpress" + "Kinh te" shows only VnExpress economics articles.
- **Search**: Combines with source and topic filters (intersection of all three).

CSS and JS are inlined in the HTML (self-contained except for images).

**Article card click behavior**:
- Clicking the **article title text**, **thumbnail image**, or **preview text** opens the reading modal
- All three clickable areas share the same `data-article-id` attribute referencing the article's `url_hash`
- A small external link icon (🔗) next to the title opens the original source URL in a new tab (`target="_blank"`)
- The card no longer contains inline expand/collapse — all full content reading happens in the modal

**Reading modal structure**:
```
Backdrop (semi-transparent overlay)
└── Modal panel (centered, max-width 800px, scrollable)
    ├── Close button [X] (top-right, fixed within panel)
    ├── Hero image (full-width, if available)
    ├── Meta line: source category · publish time · reading time
    ├── Title + external link icon
    ├── Topic tags
    ├── Separator
    ├── Article content (full HTML, scrollable)
    ├── Separator
    └── Author attribution
```

**Article data JSON block**:
- Rendered at the end of `<body>` as `<script type="application/json" id="articles-data">`
- Contains a JSON object keyed by `article.url_hash`
- Each entry stores: `title`, `url`, `source_category`, `published_date` (formatted), `author`, `reading_time`, `topics`, `hero_image_path`, `content_html`, `is_new`
- JavaScript reads this JSON to populate the modal on title click

### 9.3 Stylesheet (`style.css`)

- **CSS custom properties** for light/dark theming via `[data-theme="dark"]`
- **Light theme**: `--bg: #f5f5f5`, `--card-bg: #ffffff`, `--accent: #1a73e8`
- **Dark theme**: `--bg: #1a1a2e`, `--card-bg: #16213e`, `--accent: #4dabf7`
- **Card grid**: `grid-template-columns: repeat(auto-fill, minmax(350px, 1fr))`
- **Card hover**: `box-shadow` + `translateY(-2px)` transition
- **Responsive**: Single column at `max-width: 768px`
- **Seen articles**: `opacity: 0.7`
- **New badge**: Green background (`#34a853`)
- **Card title**: Cursor pointer, hover underline (indicates clickable for modal)
- **External link icon**: Small, inline, muted color, hover accent color

**Controls styles**:
- **Search box**: Compact width `max-width: 280px` (not flex-grow), fits alongside filter buttons without dominating the row

**Reading modal styles**:
- **Backdrop**: `position: fixed`, full viewport, `background: rgba(0,0,0,0.6)`, `z-index: 1000`, `backdrop-filter: blur(4px)`, `overflow-y: auto` (full-page scroll)
- **Panel**: `max-width: 800px`, `margin: 40px auto`, no max-height constraint (content flows naturally, backdrop scrolls), `border-radius: 16px`, card background color
- **Close button**: `position: sticky`, top of panel, circular, `z-index: 1001` (stays visible while scrolling)
- **Hero image**: Full-width within panel, `max-height: 400px`, `object-fit: cover`
- **Content area**: `padding: 32px`, `line-height: 1.8`, `font-size: 1.05em` for comfortable reading
- **Content images**: `max-width: 100%`, `border-radius: 8px`, centered
- **Transitions**: Backdrop fade-in 0.2s, panel scale-in 0.2s
- **Responsive**: On `max-width: 768px`, panel becomes full-screen (100vw, no border-radius, no margin)

**Back-to-top button**:
- Fixed `bottom: 30px`, `right: 30px`, circular, accent color
- Hidden by default, appears when `window.scrollY > 300`
- Smooth-scrolls to top on click

### 9.4 JavaScript (`script.js`)

Self-executing IIFE. Features:
- **Pagination**: `CARDS_PER_PAGE = 50`; cards beyond limit hidden; "Load more" button increments
- **Theme toggle**: Detects `prefers-color-scheme`, saves to `localStorage('tht-theme')`, toggles `data-theme` attribute
- **Search**: Debounced (300ms) input handler; case-insensitive match against `data-searchtext` attribute
- **Source filter**: Pill buttons in filter bar. "Tat ca" default. Click toggles filter. Uses `data-source` attribute on cards.
- **Topic filter**: Pill buttons in filter bar. "Tat ca" default. Click toggles filter. Uses `data-topics` attribute on cards.
- Both filters combine as intersection with search.

**Reading modal behavior**:
- **Open**: Click on any element with `[data-article-id]` (title text, thumbnail, preview) reads article data from the JSON block, populates the modal DOM, shows overlay with fade-in transition, locks body scroll (`overflow: hidden`)
- **Close**: Three methods — click close [X] button, click backdrop outside panel, press Escape key. Restores body scroll.
- **Scrolling**: The backdrop itself is scrollable (`overflow-y: auto`). The panel has no max-height — long articles scroll the full page within the backdrop.
- **Data loading**: `JSON.parse(document.getElementById('articles-data').textContent)` parsed once on page load, cached in a variable
- **Content injection**: Modal hero image src, meta text, title, tags, content HTML, and author are set via `innerHTML`/`textContent` on open

### 9.5 Output File Naming and Image Structure

Each generation produces a **timestamped** set of files so multiple runs per day do not overwrite each other:

- **HTML file**: `tonghoptin_YYYY-MM-DD_HHMM.html` (e.g., `tonghoptin_2026-04-04_1830.html`)
- **Image folder**: `tonghoptin_YYYY-MM-DD_HHMM_images/` (e.g., `tonghoptin_2026-04-04_1830_images/`)
- **Image files**: `{url_hash}.jpg` inside the per-generation image folder
- **HTML references**: relative path `tonghoptin_YYYY-MM-DD_HHMM_images/{url_hash}.jpg`

This ensures:
- Multiple runs in a day produce separate, self-contained outputs
- Each HTML file references only its own image folder
- Previous generations remain intact and can be re-opened at any time

Image specs: JPEG format, quality 80, optimized, max width 800px (configurable), aspect ratio preserved, `loading="lazy"` on `<img>` tags

### 9.6 Latest Output for GitHub Pages (`docs/`)

After each `tonghoptin collect` run, the latest output is copied to the `docs/` folder at the project root:
- `docs/index.html` — the latest digest (copied and renamed from the timestamped HTML)
- `docs/images/` — hero images for the latest digest (copied from the timestamped images folder)
- `docs/CNAME` — custom domain file for GitHub Pages (contains `chuyenhay.com`)

The `docs/` folder is committed to git and pushed to GitHub. GitHub Pages is configured to serve from the `docs/` folder on the `main` branch. This makes the latest digest accessible at `https://chuyenhay.com`.

Image paths in `docs/index.html` are rewritten from `tonghoptin_YYYY-MM-DD_HHMM_images/` to `images/` so they resolve correctly when served from the `docs/` root.

The `output/` folder (timestamped archives) remains gitignored — only `docs/` is tracked.

---

## 10. Configuration (`config.yaml`)

```yaml
history:
  chrome_path: ""                  # Path to Chrome History SQLite file
  brave_path: ""                   # Path to Brave History SQLite file
  analysis_days: 30                # Days of history to analyze

favourites:
  auto_detect_threshold: 5         # Min visits to suggest as favourite

sites:                             # List of site configurations
  - name: vnexpress                # Display name
    base_url: https://vnexpress.net
    domain: vnexpress.net
    enabled: true
    fetch_method: requests         # "requests" or "playwright"
    request_delay: 0.5             # Seconds between requests
    max_pages: 10                  # Max pagination depth per category
    max_concurrent: 5              # Max concurrent detail fetches
  # ... (5 default sites)

output:
  directory: ./output              # Output directory
  image_max_width: 800             # Max image width in pixels
  theme: auto                      # "light", "dark", or "auto"
```

### Default Sites

| Site | Domain | Fetch Method | Delay | Pages | Concurrent |
|------|--------|-------------|-------|-------|------------|
| VnExpress | vnexpress.net | requests | 0.5s | 10 | 5 |
| Tuoi Tre | tuoitre.vn | requests | 1.0s | 5 | 3 |
| Thanh Nien | thanhnien.vn | requests | 1.0s | 5 | 3 |
| Dan Tri | dantri.com.vn | playwright | 1.5s | 5 | 3 |
| VietnamNet | vietnamnet.vn | requests | 1.0s | 5 | 3 |

---

## 11. CLI Interface (`cli.py`)

Entry point: `tonghoptin` (via `pyproject.toml` console script)

### Global Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | `config.yaml` | Path to config file |
| `--verbose / -v` | `False` | Enable DEBUG logging |

### Commands

**`tonghoptin init`**
```
tonghoptin init --chrome <path> --brave <path> [--days 30] [--threshold 5]
```
Analyzes browser history, suggests favourites, generates `config.yaml`. Adds known sites as enabled; adds high-frequency unknown sites (>= 2x threshold) with GenericScraper.

**`tonghoptin collect`**
```
tonghoptin collect [--days 1] [--output <dir>] [--since-last-run]
```
Crawls all enabled sites, generates HTML digest. Process: CrawlOrchestrator -> DedupDB.mark_articles -> render_digest -> DedupDB.record_run. Prints per-site summary.

**`tonghoptin favourites list`** — Lists configured sites with status and fetch method

**`tonghoptin favourites add <domain> [--name <name>] [--playwright]`** — Adds site to config

**`tonghoptin favourites remove <domain>`** — Removes site from config

### Logging

- Handlers: stderr + `tonghoptin.log` file (UTF-8)
- Format: `HH:MM:SS [logger_name] LEVEL: message`
- Level: DEBUG if `--verbose`, else INFO

---

## 12. Error Handling

**4-level isolation** (each level catches exceptions independently):
1. **Per-site**: `CrawlOrchestrator._run_site()` wraps each scraper in try/except. Returns `FAILED` SiteCrawlResult on unhandled exception.
2. **Per-category**: Each category URL crawled in separate try/except within `BaseScraper.crawl()`.
3. **Per-page**: Pagination failure stops that category but preserves already-discovered stubs.
4. **Per-article**: `_fetch_and_parse_article()` wraps each detail fetch. Failed articles recorded in `errors` list.

**Error record format**: `{url: str, error: str, phase: str, timestamp: str}`
- Phases: `fetch_listing`, `parse_listing`, `fetch_detail`, `parse_detail`, `image_download`, `site_crawl`

**Fetcher retries**: Exponential backoff (1s, 2s, 4s) on transient HTTP errors (429, 5xx) and connection errors. Non-transient errors (403, 404) fail immediately.

---

## 13. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| aiohttp | >=3.9 | Async HTTP fetching |
| beautifulsoup4 | >=4.12 | HTML parsing |
| playwright | >=1.40 | Headless browser for JS-heavy sites |
| readability-lxml | >=0.8 | Generic article extraction (GenericScraper) |
| Pillow | >=10.0 | Image resizing |
| pyyaml | >=6.0 | YAML config parsing |
| click | >=8.1 | CLI framework |
| jinja2 | >=3.1 | HTML template rendering |
| lxml | >=5.0 | Fast HTML/XML parser |
| sqlite3 | stdlib | History DB + dedup DB |

---

## 14. Project Structure

```
TongHopTin/
├── pyproject.toml                 # Build config, dependencies, entry point
├── requirements.txt               # Pinned dependencies
├── config.yaml                    # User configuration
├── run.bat                        # Windows batch runner (collect + open browser)
├── tonghoptin/
│   ├── __init__.py                # Package init (version: 1.0.0)
│   ├── cli.py                     # CLI entry point (click)
│   ├── config.py                  # Config loading/saving + DEFAULT_SITES
│   ├── models.py                  # All dataclasses and enums
│   ├── fetcher.py                 # Async HTTP + Playwright fetcher
│   ├── orchestrator.py            # CrawlOrchestrator
│   ├── cleaning.py                # HTML content cleaning pipeline
│   ├── vietnamese.py              # Date parsing + topic tagging
│   ├── history.py                 # Browser history analysis
│   ├── dedup.py                   # SQLite deduplication DB
│   ├── renderer.py                # HTML digest generation
│   ├── scrapers/
│   │   ├── __init__.py            # Scraper registry + auto-registration
│   │   ├── base.py                # BaseScraper abstract class
│   │   ├── vnexpress.py           # VnExpress (11 categories)
│   │   ├── tuoitre.py             # Tuoi Tre (14 categories)
│   │   ├── thanhnien.py           # Thanh Nien (13 categories)
│   │   ├── dantri.py              # Dan Tri (17 categories, Playwright)
│   │   ├── vietnamnet.py          # VietnamNet (14 categories, JSON+DOM)
│   │   └── generic.py             # Generic fallback (readability-lxml)
│   └── templates/
│       ├── digest.html            # Jinja2 HTML template
│       ├── style.css              # Inline stylesheet (light+dark themes)
│       └── script.js              # Inline JS (search, filter, dark mode)
├── output/                        # Generated digests + images
│   ├── tonghoptin_YYYY-MM-DD.html
│   ├── images/                    # Downloaded hero images
│   └── tonghoptin.db              # Dedup database
└── tests/
    ├── __init__.py
    └── test_scrapers/
        └── __init__.py
```

---

## 15. Output File Structure

Each `tonghoptin collect` run produces:

```
output/
├── tonghoptin_2026-04-04.html     # Self-contained HTML (CSS/JS inline, ~600KB)
├── images/
│   ├── a1b2c3d4e5f6.jpg           # Hero images named by URL hash
│   ├── ...
│   └── (one per article with hero image)
└── tonghoptin.db                   # Dedup + run history database
```

Previous outputs are preserved (not overwritten).

---

## 16. Verified Behavior

Tested end-to-end against VnExpress (2026-04-04):

| Metric | Value |
|--------|-------|
| Categories scraped | 11 (1 page each) |
| Stubs discovered | 410 |
| Articles collected | 80 (today only) |
| Errors | 0 |
| Images downloaded | 80 |
| HTML file size | 662 KB |
| Duration | ~214 seconds |

Interactive features verified: search filtering (80 -> 3 cards for "kinh te"), dark mode toggle, article expand/collapse, topic tag filtering. No JavaScript errors.

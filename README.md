# Thông Tin Là Sức Mạnh!

Vietnamese news aggregator (codebase: TongHopTin). Crawls 20+ Vietnamese news
sites, deduplicates, scores by personal interest, and publishes a static
reading digest to [chuyenhay.com](https://chuyenhay.com) via GitHub Pages.

## Usage

```
python -m tonghoptin.cli collect   # crawl + render + publish to docs/
run.bat                            # collect, commit and push (deploy)
```

Configuration lives in `config.yaml`. The dedup/content cache is
`output/tonghoptin.db` (7-day sliding window; repeat runs within a day reuse
cached article content and are much faster).

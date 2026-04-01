# Design Scraper Agents Guide

This repository packages the `design-scraper` Codex plugin and its reusable scraping skill.

## Purpose

Use this repo when the task is to collect design inspiration assets from supported URLs, prefer original media over screenshots, organize outputs locally, and run the scraper/post-processing pipeline consistently.

## Primary Entry Point

Run the scraper from the plugin root:

```bash
python3 skills/design-scraper/scripts/scrape_design.py <url> [<url> ...]
```

Common flags:

```bash
--output-dir <dir>
--project <name>
--tag <tag>
--fetch-variant playwright|crawl4ai|http
--playwright-user-data-dir <dir>
--headed
--skip-post-process
```

Local defaults can be stored in plugin-root `.env`. Supported keys:

```bash
DEFAULT_OUTPUT_DIR=~/design_scrapped/initial
FETCH_VARIANT=playwright
PLAYWRIGHT_USER_DATA_DIR=~/.design-scraper/profile
PLAYWRIGHT_HEADED=false
DEDUPE_THRESHOLD=25
SKIP_POST_PROCESS=false
```

Default fetch behavior:

- `playwright` is the default backend
- `crawl4ai` is the alternate backend
- `http` is the explicit fallback/debug backend

For auth-gated sites:

- use `--playwright-user-data-dir` to reuse a persistent browser profile
- use `--headed` for the first manual login
- keep the profile outside the repo and restrict it to your user

## Supported Sources

- Dribbble
- Mobbin
- App Store
- Behance
- Pinterest
- Awwwards

Source-specific adapters live under `skills/design-scraper/scripts/design_scraper/adapters/`.

## Expected Workflow

1. Normalize input URLs and detect the source.
2. Use the dedicated source adapter when one matches.
3. Prefer original assets over screenshots and lower-resolution derivatives.
4. Save downloads under the generated output tree.
5. Persist run metadata in `metadata/index.json` and `metadata/run_<id>.json`.
6. Run post-processing unless the caller explicitly skips it.

## Output Layout

The scraper writes:

- `raw/`
- `normalized/`
- `metadata/index.json`
- `metadata/run_<id>.json`
- `preview.html` when post-processing runs

## Editing Rules

- Keep fetcher logic isolated in `skills/design-scraper/scripts/design_scraper/fetchers.py`.
- Keep source-specific logic inside dedicated adapters, not in the CLI entrypoint.
- Reuse shared helpers from `adapters/common.py` when adding new adapters.
- Do not fake success. Return explicit failure states such as `fetch_failed`, `auth_required`, `no_media_found`, or `download_failed`.
- Preserve the plugin manifest at `.codex-plugin/plugin.json`.

## Validation

Before finishing changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile $(find skills/design-scraper/scripts/design_scraper -type f -name '*.py') skills/design-scraper/scripts/scrape_design.py
```

For a live smoke test, use a public design URL and inspect `metadata/index.json` for:

- effective fetch backend
- extracted assets
- duplicate or low-quality variant issues

---
name: design-scraper
description: Scrape and organize design inspiration assets from links such as Dribbble, Mobbin, App Store, Behance, Pinterest, and Awwwards. Use when the user shares design inspiration URLs, asks to download reference assets, build a moodboard source folder, extract color palettes, detect duplicate screenshots, or generate a local preview grid.
---

# Design Scraper

Use this skill when the user wants design inspiration links turned into a local asset set.

## Primary Entry Point

Run the orchestrator instead of manually redoing the workflow:

```bash
python3 .codex/skills/design-scraper/scripts/scrape_design.py \
  <url> [<url> ...] \
  --output-dir <dir> \
  [--fetch-variant playwright|crawl4ai|http] \
  [--project <name>] \
  [--tag <tag>]
```

The orchestrator creates:

- `raw/` for source downloads
- `normalized/` for later normalized assets
- `metadata/index.json` for persistent manifest/state
- `metadata/run_<id>.json` for the current run report
- `preview.html` after post-processing

## Workflow

1. Collect the URLs, output directory, optional project name, and tags.
2. Invoke `scrape_design.py` with those inputs.
3. Prefer original assets over screenshots. Screenshot fallback should be explicit in metadata.
4. Let the orchestrator run the internal post-processing scripts unless the user asks to skip them.
5. Report the output directory, notable warnings, duplicate groups if present, and the preview entrypoint.

## Source Notes

- Mobbin usually needs a logged-in browser session before scraping. If access is blocked, stop and tell the user to authenticate first.
- Pinterest and Behance often return many derived image sizes; keep the largest clean URL rather than small thumbnails.
- If a format conversion fails, keep the original file and note that in the summary.

## Execution Notes

- Codex does not support the Claude hook from the source plugin. Trigger this skill from user intent or by noticing supported design URLs in the prompt.
- The original Claude plugin depended on a Playwright browser plugin. In Codex, use the available browser or shell tooling in the current environment; if browser automation is unavailable, state that constraint explicitly before attempting a partial fallback.
- Use Playwright MCP for dynamic extraction and login-gated pages, then use direct HTTP downloads for canonical assets when available.
- Process downloads in parallel when practical, but keep browser navigation serialized unless the environment clearly supports multiple sessions.
- The current implementation uses a registry with three tiers:
  - dedicated site adapters for Dribbble, Mobbin, App Store, Behance, Pinterest, and Awwwards
  - a generic direct-media fallback for pages that expose image or video URLs plainly
  - an Open Graph fallback for pages that only expose a representative preview image
- HTML acquisition is also split into variants:
  - `playwright`: default requested backend
  - `crawl4ai`: alternate backend
  - `http`: explicit fallback/debug backend
- In the current runtime, the Playwright fetcher degrades to `http` when Python Playwright is unavailable and records that fallback in metadata.
- Source-specific adapters are heuristic and may still need richer rendered HTML or authenticated sessions on some pages. They should report clear failure states instead of faking success.

## Outputs

The post-processing scripts create:

- `palette.json` files beside analyzed images
- `color_summary.json` at the output root
- `duplicates.json` at the output root
- `preview.html` at the output root

If duplicates are found, ask whether to keep all files, remove extras, or move duplicates into a `_duplicates/` folder.

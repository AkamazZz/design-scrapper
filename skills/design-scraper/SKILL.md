---
name: design-scraper
description: Scrape and organize design inspiration assets from links such as Dribbble, Mobbin, App Store, Behance, Pinterest, and Awwwards, then turn them into a reusable mobile-first design contract and implementation guidance. Use when the user shares design inspiration URLs, asks to download reference assets, build a moodboard source folder, extract color palettes, detect duplicate screenshots, generate a local preview grid, or synthesize a mobile design system from the collected references.
---

# Design Scraper

Use this skill when the user wants design inspiration links turned into a local asset set or a reusable mobile-first design handoff.

This is now one skill with two layers:

- scraping and post-processing
- mobile design orchestration on top of the scraped results

## Primary Entry Points

Collect and normalize reference assets:

```bash
python3 skills/design-scraper/scripts/scrape_design.py \
  <url> [<url> ...] \
  --output-dir <dir> \
  [--fetch-variant playwright|crawl4ai|http] \
  [--project <name>] \
  [--tag <tag>]
```

Initialize or refresh the mobile-first design workspace from an existing scrape:

```bash
python3 skills/design-scraper/scripts/orchestrate_mobile_design.py run \
  --scrape-root design_scrapped/initial \
  --output-dir orchestrated/headspace \
  --project "Headspace Mobile"
```

Add an idea card while reviewing inspiration:

```bash
python3 skills/design-scraper/scripts/add_idea.py \
  --output-dir orchestrated/headspace \
  --title "Quiet onboarding with one primary action" \
  --summary "Use calm pacing and a single dominant CTA per step." \
  --pattern-category onboarding \
  --source-url "https://mobbin.com/apps/headspace-ios-28986bf8-81b2-4af0-84df-b5654a8c98f9/f2c7edab-00b5-460c-9663-1cf64517f7db/screens"
```

Validate the canonical design handoff before implementation:

```bash
python3 skills/design-scraper/scripts/validate_design_contract.py \
  --output-dir orchestrated/headspace
```

## Scraper Outputs

The scraping layer creates:

- `raw/` for source downloads
- `normalized/` for later normalized assets
- `metadata/index.json` for persistent manifest/state
- `metadata/run_<id>.json` for the current run report
- `preview.html` after post-processing

## Orchestrator Outputs

The orchestration layer creates:

- `inspirations/index.json`
- `ideas/index.json`
- `proposal/design_direction.md`
- `proposal/design_signals.json`
- `proposal/direction_options.json`
- `proposal/proposal_candidates.json`
- `proposal/review_packet.md`
- `proposal/visual_language.json`
- `proposal/typography_voice.json`
- `proposal/component_motifs.json`
- `proposal/flow_narrative.md`
- `proposal/anti_patterns.md`
- `proposal/source_rationale.json`
- `contract/brief.json`
- `contract/tokens.json`
- `contract/typography.json`
- `contract/semantics.json`
- `screens/index.json`
- `platforms/flutter.json`
- `platforms/swiftui.json`
- `platforms/compose.json`
- `realization/plan.json`
- `validation/report.json`

## Workflow

1. Collect the URLs, output directory, optional project name, and tags.
2. Invoke `scrape_design.py` with those inputs.
3. Prefer original assets over screenshots. Screenshot fallback should be explicit in metadata.
4. Let the scraper run the internal post-processing scripts unless the user asks to skip them.
5. If the user wants a design system or handoff, run `orchestrate_mobile_design.py`.
6. Capture idea cards as inspirations are reviewed.
7. Extract deterministic design signals from inspirations and ideas, including repo-aware clustered signal output.
8. Score directions from the clustered signal layer, then build deterministic `proposal/direction_options.json` and select the top-ranked direction.
9. Generate `proposal/proposal_candidates.json` and `proposal/review_packet.md` so the user can inspect 2-3 serious candidates before the contract is emitted.
10. Synthesize an opinionated proposal before generating tokens or semantics.
11. Build the canonical contract from the proposal, not directly from raw inspiration.
12. Let the selected proposal drive spacing rhythm, corner posture, motion posture, and reusable component variants in the canonical contract.
13. Generate structurally proposal-aware mobile-first screens from the proposal plus contract, then emit platform guidance.
14. Run `validate_design_contract.py` before claiming the workspace is ready.
15. Report the output directory, notable warnings, validation status, and the preview or handoff entrypoints.

## Canonical Contract Rules

- The canonical contract is the source of truth.
- `proposal/design_signals.json` is the evidence layer that keeps proposal generation grounded in the current reference set and now includes clustered signal evidence before archetype scoring.
- `proposal/direction_options.json` is the deterministic ranking layer that makes proposal selection auditable.
- `proposal/proposal_candidates.json` and `proposal/review_packet.md` are the richer human-review surfaces that explain the selected and rejected directions before contract generation.
- Proposal artifacts define the visual stance that the contract must preserve.
- The contract should carry proposal-derived spacing, shape, motion, and component posture, not just colors and fonts.
- Validation should catch stale generic screens even when direction ids still align.
- Tokens hold raw values only. Meaning belongs in semantics.
- Typography must stay semantic and reusable across screens.
- Screen definitions consume semantic roles instead of raw values.
- Platform outputs are guidance artifacts, not code emitters.
- Web references are examples of hierarchy, tone, and rhythm. Translate them into mobile patterns instead of copying desktop layouts.
- Preserve rationale from inspiration through idea cards and into the realization plan.

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
- Keep the canonical contract platform-neutral. Do not put `ThemeData`, `UIFont`, `TextStyle`, `VStack`, `Column`, or `LazyColumn` constructs into the source contract.
- If a platform-specific compromise is required, record it as a gap in the platform guidance instead of silently guessing.

## Post-Processing Outputs

The post-processing scripts create:

- `palette.json` files beside analyzed images
- `color_summary.json` at the output root
- `duplicates.json` at the output root
- `preview.html` at the output root

If duplicates are found, ask whether to keep all files, remove extras, or move duplicates into a `_duplicates/` folder.

## References

- Read `references/mobile-design-orchestrator/contract-schema.md` when editing or extending canonical contract files.
- Read `references/mobile-design-orchestrator/platform-mapping.md` when tightening platform guidance.
- Read `references/mobile-design-orchestrator/realization-plan.md` when the user wants a delivery roadmap.

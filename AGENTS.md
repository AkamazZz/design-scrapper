# Design Scraper Agents Guide

This repository packages the `design-scraper` Codex plugin as a single skill surface with both scraping and mobile design orchestration.

## Purpose

Use this repo when the task is to:

- collect design inspiration assets from supported URLs
- prefer original media over screenshots
- organize outputs locally with metadata and preview artifacts
- turn scraped inspiration into a mobile-first canonical design contract
- produce reusable design handoff guidance for Flutter, SwiftUI, and Compose without generating platform UI code

## Choose The Entry Point

Use the scraper when the user needs assets collected from source URLs:

```bash
python3 skills/design-scraper/scripts/scrape_design.py <url> [<url> ...]
```

Use the orchestrator when the user wants design synthesis and structured handoff from an existing scrape:

```bash
python3 skills/design-scraper/scripts/orchestrate_mobile_design.py run \
  --scrape-root design_scrapped/initial \
  --output-dir orchestrated/headspace \
  --project "Headspace Mobile"
```

Validate an orchestration workspace before handoff:

```bash
python3 skills/design-scraper/scripts/validate_design_contract.py \
  --output-dir orchestrated/headspace
```

## Scraper Defaults

Local scraper defaults can be stored in plugin-root `.env`. Supported keys:

```bash
DEFAULT_OUTPUT_DIR=./design_scrapped/initial
FETCH_VARIANT=playwright
PLAYWRIGHT_USER_DATA_DIR=~/.design-scraper/profile
PLAYWRIGHT_HEADED=false
DEDUPE_THRESHOLD=25
SKIP_POST_PROCESS=false
```

Default fetch behavior:

- `playwright` is the default backend
- `crawl4ai` is the alternate backend
- `http` is the explicit fallback or debug backend

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
5. Persist scraper metadata in `metadata/index.json` and `metadata/run_<id>.json`.
6. Run post-processing unless the caller explicitly skips it.
7. If the user wants design synthesis, initialize an orchestration workspace from the scrape output.
8. Capture reusable idea cards while reviewing inspirations.
9. Extract `proposal/design_signals.json` from inspirations and ideas, including deterministic clustered signals.
10. Score directions from the clustered signal layer, then build deterministic `proposal/direction_options.json` and select the top-ranked direction.
11. Generate `proposal/proposal_candidates.json` and `proposal/review_packet.md` so 2-3 serious candidates can be reviewed before contract generation.
12. Create the proposal direction artifacts from the selected option.
13. Load orchestration policy from the versioned config layer instead of embedding archetypes or layout policy in runtime code.
14. Build the canonical contract from the proposal before touching platform-specific work.
15. Carry proposal posture into the contract, including spacing rhythm, corner posture, motion posture, and reusable component variants.
16. Generate structurally proposal-aware mobile-first screens, platform guidance, a realization plan, and a validation report.

## Orchestrator Phases

The current orchestrator flow is:

1. `ingest`
2. `ideas`
3. `proposal`
4. `contract`
5. `screens`
6. `platforms`
7. `plan`
8. `validate`

The current proposal stack inside `proposal/` is:

1. `design_signals.json`
2. `direction_options.json`
3. `proposal_candidates.json`
4. `review_packet.md`
5. `design_direction.md`
6. `visual_language.json`
7. `typography_voice.json`
8. `component_motifs.json`
9. `flow_narrative.md`
10. `anti_patterns.md`
11. `source_rationale.json`

Platform outputs are guidance artifacts. They explain typography, visuals, components, layout, interaction, assets, implementation notes, and gaps. They are not code emitters.

For the current implemented phases, proposal sublayers, and next roadmap phases, read [phases.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/phases.md).

## Policy Config

The orchestrator now externalizes static policy into versioned data files:

- `skills/design-scraper/scripts/mobile_design_orchestrator/config/orchestrator_policies.v1.json`
- `skills/design-scraper/scripts/mobile_design_orchestrator/config_loader.py`

That config currently owns:

- proposal archetypes
- signal cluster definitions
- screen structure profiles
- screen effect profiles
- validation posture maps such as CTA posture and chrome density expectations

## Output Layout

The scraper writes:

- `raw/`
- `normalized/`
- `metadata/index.json`
- `metadata/run_<id>.json`
- `preview.html` when post-processing runs

The orchestrator writes:

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
- `metadata/index.json`
- `metadata/orchestrator_run_<id>.json`

## Editing Rules

- Keep scraper fetcher logic isolated in `skills/design-scraper/scripts/design_scraper/fetchers.py`.
- Keep source-specific scraping logic inside dedicated adapters, not in the scraper CLI entrypoint.
- Reuse shared scraper helpers from `adapters/common.py` when adding new adapters.
- Reuse `design-scraper` for supported inspiration URLs. Do not duplicate scraping logic in the orchestration layer.
- Keep static orchestration policy in `skills/design-scraper/scripts/mobile_design_orchestrator/config/orchestrator_policies.v1.json` instead of re-embedding large tables in `pipeline.py` or `project.py`.
- Keep `skills/design-scraper/scripts/mobile_design_orchestrator/config_loader.py` thin. It should validate and expose config, not become a second orchestration layer.
- Keep the canonical contract platform-neutral.
- Do not put Flutter, SwiftUI, or Compose implementation constructs into the source contract.
- Keep proposal-driven spacing, radius, motion, and component posture in the canonical contract instead of hardcoding generic defaults.
- Preserve rationale between inspirations, idea cards, semantics, and screens.
- Do not fake success. Return explicit failure states such as `fetch_failed`, `auth_required`, `no_media_found`, `download_failed`, `scrape_input_missing`, `inspiration_manifest_invalid`, `insufficient_inputs`, `canonical_contract_invalid`, or `platform_mapping_incomplete`.
- Preserve the plugin manifest at `.codex-plugin/plugin.json`.

## Validation

Before finishing scraper changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile $(find skills/design-scraper/scripts/design_scraper -type f -name '*.py') skills/design-scraper/scripts/scrape_design.py
```

Before finishing orchestrator changes:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile $(find skills/design-scraper/scripts -type f -name '*.py')
```

Run the current orchestrator test suite with:

```bash
python3 -m unittest tests.test_mobile_design_orchestrator
```

The current suite also proves that runtime policy tables are sourced from the externalized config layer.

For a live scraper smoke test, use a public design URL and inspect `metadata/index.json` for:

- effective fetch backend
- extracted assets
- duplicate or low-quality variant issues

For an orchestrator smoke test, run against an existing scrape and inspect `validation/report.json` for:

- pass or warning status
- missing or invalid clustered signal evidence in `proposal/design_signals.json`
- missing canonical files
- proposal signal or proposal coverage mismatches
- invalid typography or semantic references
- screen structure drift such as `screen_structure_stale`, `screen_contract_drift`, or `screen_motif_drift`
- screen or platform guidance drift

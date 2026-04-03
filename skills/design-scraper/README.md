# Design Scraper V2 Reuse Guide

## Scope

This directory contains the active `v2` implementation work for the `design-scraper` skill.

Use this subtree as the engineering base for:

- deterministic analysis artifacts
- automated ideas
- screen briefs
- screen variants
- critic and review artifacts
- hybrid publication into `screens/index.json`

## Current Rollout State

Current phase status:

- `analysis`: `v2`
- `ideas`: `v2`
- `proposal`: `v1` fallback
- `screen_briefs`: `v2`
- `screen_variants`: `v2`
- `critic`: `v2`
- `screens`: hybrid `v1` baseline plus `v2` lineage overlay

Important constraint:

- `screens/index.json` is still validator-bound to the existing canonical shape.
- The publisher therefore synthesizes the proven baseline structure first, then adds `v2` winner metadata and lineage.

## Key Files

- [SKILL.md](./SKILL.md)
- [scripts/orchestrate_mobile_design.py](./scripts/orchestrate_mobile_design.py)
- [scripts/mobile_design_orchestrator/pipeline.py](./scripts/mobile_design_orchestrator/pipeline.py)
- [scripts/mobile_design_orchestrator/analysis.py](./scripts/mobile_design_orchestrator/analysis.py)
- [scripts/mobile_design_orchestrator/idea_generation.py](./scripts/mobile_design_orchestrator/idea_generation.py)
- [scripts/mobile_design_orchestrator/screen_briefs.py](./scripts/mobile_design_orchestrator/screen_briefs.py)
- [scripts/mobile_design_orchestrator/scene_graph.py](./scripts/mobile_design_orchestrator/scene_graph.py)
- [scripts/mobile_design_orchestrator/screen_variants.py](./scripts/mobile_design_orchestrator/screen_variants.py)
- [scripts/mobile_design_orchestrator/selected_screens.py](./scripts/mobile_design_orchestrator/selected_screens.py)
- [scripts/mobile_design_orchestrator/critic.py](./scripts/mobile_design_orchestrator/critic.py)
- [scripts/mobile_design_orchestrator/review.py](./scripts/mobile_design_orchestrator/review.py)
- [scripts/mobile_design_orchestrator/v2_runtime.py](./scripts/mobile_design_orchestrator/v2_runtime.py)

## Full Run

Run the whole pipeline from an existing scrape:

```bash
python3 skills/design-scraper/scripts/orchestrate_mobile_design.py run \
  --output-dir /absolute/path/to/workspace \
  --project "Project Name" \
  --scrape-root /absolute/path/to/scrape-root \
  --json
```

Default phase order:

1. `ingest`
2. `analysis`
3. `ideas`
4. `proposal`
5. `contract`
6. `screen_briefs`
7. `screen_variants`
8. `critic`
9. `screens`
10. `platforms`
11. `plan`
12. `validate`

## Partial Re-Runs

Run selected phases only:

```bash
python3 skills/design-scraper/scripts/orchestrate_mobile_design.py run \
  --output-dir /absolute/path/to/workspace \
  --project "Project Name" \
  --phase analysis \
  --phase ideas \
  --phase validate \
  --json
```

Useful direct entrypoints:

- analysis

```bash
python3 skills/design-scraper/scripts/analyze_inspiration.py \
  --output-dir /absolute/path/to/workspace \
  --json
```

- ideas

```bash
python3 skills/design-scraper/scripts/generate_ideas.py \
  --output-dir /absolute/path/to/workspace \
  --json
```

- screen briefs

```bash
python3 skills/design-scraper/scripts/generate_screen_briefs.py \
  --output-dir /absolute/path/to/workspace \
  --json
```

- screen variants

```bash
python3 skills/design-scraper/scripts/generate_screen_variants.py \
  --output-dir /absolute/path/to/workspace \
  --screen-id home \
  --max-variants-per-screen 3 \
  --json
```

- critic / review

```bash
python3 skills/design-scraper/scripts/render_screen_variants.py \
  /absolute/path/to/workspace \
  --print-summary
```

- selected screen publication

```bash
python3 skills/design-scraper/scripts/publish_selected_screens.py \
  --output-dir /absolute/path/to/workspace \
  --json
```

- validation

```bash
python3 skills/design-scraper/scripts/validate_design_contract.py \
  --output-dir /absolute/path/to/workspace \
  --json
```

## Artifact Families

`v2` adds these artifact groups:

- `analysis/`
  - `screen_manifest.json`
  - `ocr.json`
  - `layout_regions.json`
  - `component_tags.json`
  - `screen_embeddings.json`
- `ideas/`
  - `auto_generated.json`
  - `review_queue.json`
  - merged `index.json`
- `screen_briefs/`
  - `index.json`
  - one file per screen
- `screen_variants/`
  - `index.json`
  - `variant_*.json` per screen
- `review/`
  - `scores.json`
  - `summary.md`
  - `critic_report.md`

Existing stable contract outputs remain:

- `proposal/*`
- `contract/*`
- `screens/index.json`
- `platforms/*.json`
- `realization/plan.json`
- `validation/report.json`

## Run Metadata

Every full run emits `v2` metadata. The fields that matter are:

- `workspace_version`
- `v2.enabled_flags`
- `v2.enabled_phases`
- `v2.phase_records`

Read `phase_records` to see the actual winner for each stage:

- `winning_path`
- `fallbacks`
- `artifacts`
- `details`

This is the rollout inspection surface. Use it instead of guessing from file presence alone.

## Engineering Rules

1. Preserve the canonical output contract.
2. Add deterministic inspection artifacts before replacing stable outputs.
3. Keep `screens/index.json` validator-compatible until validation policy is intentionally upgraded.
4. Record any dual-path behavior in `v2.phase_records`.
5. Prefer adding lineage over replacing shape.
6. Re-run validation after changes to `proposal`, `contract`, `screens`, `platforms`, or `review`.

## Main Integration Seam

`M3` is the main seam.

`screen_briefs/*` freezes:

- `screen_id`
- navigation edges
- required states
- data bindings
- evidence lineage

`screen_variants` and `critic` should not invent a different screen identity layer. If they need more information, extend the brief contract first.

## Extension Boundaries

- Extend [scripts/mobile_design_orchestrator/analysis.py](./scripts/mobile_design_orchestrator/analysis.py) for richer OCR, layout, and component evidence.
- Extend [scripts/mobile_design_orchestrator/idea_generation.py](./scripts/mobile_design_orchestrator/idea_generation.py) for better clustering and scoring.
- Extend [scripts/mobile_design_orchestrator/screen_briefs.py](./scripts/mobile_design_orchestrator/screen_briefs.py) for stronger planning contracts.
- Extend [scripts/mobile_design_orchestrator/scene_graph.py](./scripts/mobile_design_orchestrator/scene_graph.py) and [scripts/mobile_design_orchestrator/screen_variants.py](./scripts/mobile_design_orchestrator/screen_variants.py) for richer variant generation.
- Extend [scripts/mobile_design_orchestrator/critic.py](./scripts/mobile_design_orchestrator/critic.py) and [scripts/mobile_design_orchestrator/review.py](./scripts/mobile_design_orchestrator/review.py) for stronger review gates.
- Extend [scripts/mobile_design_orchestrator/pipeline.py](./scripts/mobile_design_orchestrator/pipeline.py) only for phase wiring, fallback policy, and artifact persistence.

## Known Caveats

- `proposal` still uses the old heuristic path.
- `critic` is heuristic, not a render-based VLM loop yet.
- selected screens still depend on a `v1` structural baseline.

## Minimal Verification

After non-trivial changes:

1. Compile touched Python modules.
2. Run a fresh workspace.
3. confirm `validation/report.json` is `passed`
4. inspect `v2.phase_records` to confirm the intended winner path was actually used

Example:

```bash
PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile \
  skills/design-scraper/scripts/mobile_design_orchestrator/pipeline.py
```

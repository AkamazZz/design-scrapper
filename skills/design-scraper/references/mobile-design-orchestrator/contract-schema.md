# Contract Schema

This skill treats the canonical contract as the source of truth and platform guidance as structured handoff output.

## Current Scaffold

The bundled scripts create and validate these files:

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

## File Roles

`inspirations/index.json`
- Normalized view of the scraper output.
- Group assets by `source_url` and preserve counts, titles, duplicates, and color summaries.

`ideas/index.json`
- Persistent idea cards created during review.
- Each idea should keep `title`, `summary`, `rationale`, `pattern_category`, source references, and target screens.

`proposal/design_direction.md`
- Opinionated written stance for the direction.
- This is where the workflow rejects generic output before any contract values are emitted.

`proposal/design_signals.json`
- Deterministic evidence extracted from inspirations and idea cards before final proposal assembly.
- Records source patterns, idea patterns, screen pressure, color observations, tone observations, explicit `signal_clusters`, motif candidates, confidence, and scored direction evidence.
- `signal_clusters` should expose deterministic cluster ranking and active cluster metadata before archetype scoring.

`proposal/direction_options.json`
- Deterministic ranked direction candidates derived from `proposal/design_signals.json`.
- Keeps direction selection auditable before final proposal artifacts are emitted.
- Required top-level keys:
  - `contract_version`
  - `project`
  - `selected_direction_id`
  - `options`

`proposal/proposal_candidates.json`
- Rich proposal review surface derived from `proposal/direction_options.json`.
- Keeps 2-3 serious candidates visible before contract generation.
- Required top-level keys:
  - `contract_version`
  - `project`
  - `selected_direction_id`
  - `candidate_count`
  - `candidates`
  - `non_negotiables`
  - `open_questions`

`proposal/review_packet.md`
- Human-readable review packet for the selected direction and rejected candidates.
- Should make selection rationale, rejection rationale, non-negotiables, and open questions explicit.

`proposal/visual_language.json`
- Structured visual direction for palette, atmosphere, composition, surfaces, and motion.

`proposal/typography_voice.json`
- Structured voice and typographic posture that downstream contract files must preserve.

`proposal/component_motifs.json`
- Reusable component patterns and their intent.

`proposal/flow_narrative.md`
- Narrative explanation of how major flows should feel and progress.

`proposal/anti_patterns.md`
- Explicit list of what the design should avoid.

`proposal/source_rationale.json`
- Coverage proof that the proposal actually reflects the reviewed inspirations and ideas.

`contract/brief.json`
- Product intent and implementation constraints.
- Required top-level keys:
  - `contract_version`
  - `project`
  - `platform_targets`
  - `design_principles`
  - `brand`
  - `localization`
  - `accessibility`
  - `content_strategy`
  - `technical_constraints`
  - `deliverables`

`contract/tokens.json`
- Primitive values only.
- Proposal-derived posture belongs here for raw spacing rhythm, corner scale, elevation, opacity, and motion timing.
- Required top-level keys:
  - `contract_version`
  - `color`
  - `spacing`
  - `radius`
  - `size`
  - `elevation`
  - `opacity`
  - `motion`
  - `border`
  - `z_index`

`contract/typography.json`
- Cross-platform type system.
- May carry proposal context such as voice, density posture, and paragraph spacing defaults.
- Required top-level keys:
  - `contract_version`
  - `font_families`
  - `font_weights`
  - `type_scales`
  - `text_styles`
  - `defaults`

`contract/semantics.json`
- Semantic meaning layered on top of tokens and typography.
- This is where proposal-driven spacing roles, shape roles, state posture, and component variants become reusable semantic roles.
- Required top-level keys:
  - `contract_version`
  - `themes`
  - `text_roles`
  - `spacing_roles`
  - `shape_roles`
  - `state_roles`
  - `component_roles`

`screens/index.json`
- Mobile-first composition using semantic roles.
- Each screen should carry structural metadata such as `layout_strategy`, `cta_posture`, `chrome_density`, `card_usage`, and `motif_application`.
- Required top-level keys:
  - `contract_version`
  - `allowed_component_kinds`
  - `screen_rules`
  - `screens`

`platforms/<platform>.json`
- Guidance layer for Flutter, SwiftUI, and Compose.
- Required top-level keys:
  - `platform`
  - `contract_version`
  - `guidance_scope`
  - `design_intent`
  - `typography_guidance`
  - `visual_guidance`
  - `component_guidance`
  - `layout_guidance`
  - `interaction_guidance`
  - `asset_guidance`
  - `implementation_notes`
  - `gaps`

## Reuse Rules

- Proposal artifacts are the design stance layer between inspiration and contract.
- `proposal/design_signals.json` is the extracted evidence layer for the proposal, including clustered signals that direction scoring must consume.
- `proposal/direction_options.json` turns extracted evidence into ranked deterministic direction choices.
- `proposal/proposal_candidates.json` and `proposal/review_packet.md` are the main human-review surfaces for proposal selection.
- `contract/` must depend on `proposal/`, not on raw inspiration alone.
- `contract/tokens.json` should absorb proposal posture beyond palette alone.
- `contract/semantics.json` should preserve proposal-driven component variants and state posture instead of falling back to generic defaults.
- Tokens contain raw values. Never put semantic meaning into token names.
- Typography stays reusable across screens.
- Screen definitions consume semantic roles instead of raw colors, spacing, or font values.
- Platform guidance may explain semantics but must not invent missing semantics.
- References flow in one direction:
  - `inspirations -> ideas -> proposal -> contract -> screens -> platforms`

## Minimum Validation

The validator should reject or warn on:

- missing required files
- missing required top-level keys
- proposal artifacts that do not cover the current inspirations or ideas
- missing or invalid clustered signal evidence in `proposal/design_signals.json`
- proposal direction options that do not align with the selected visual direction
- proposal candidate review artifacts that do not align with the ranked options or selected direction
- contract posture that drifts from the selected proposal surface, motion, spacing, or shape profile
- stale or generic screen outputs that no longer match the selected proposal effect
- motif application that exists formally but is not materially tied to the selected proposal motifs
- typography references to unknown font families, weights, or scales
- semantic roles that point to missing typography styles or token refs
- screen components that use unsupported kinds
- platform guidance that omits used semantics or components

Keep the contract strict. Drift is cheaper to prevent here than to fix in three platform implementations later.

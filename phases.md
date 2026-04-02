# Phases

## Core Flow

The current orchestration flow is:

1. `ingest`
   Normalize scraper output into `inspirations/index.json`.
2. `ideas`
   Capture reusable idea cards in `ideas/index.json`.
3. `proposal`
   Build a non-generic design direction before generating the contract.
4. `contract`
   Generate the canonical cross-platform design contract.
5. `screens`
   Generate mobile-first screen definitions from proposal plus contract.
6. `platforms`
   Generate implementation guidance for Flutter, SwiftUI, and Compose.
7. `plan`
   Refresh realization status and next actions.
8. `validate`
   Check file presence, proposal alignment, and contract consistency.

## Proposal Stack

The `proposal` phase is currently layered like this:

1. `proposal/design_signals.json`
   Deterministic evidence extracted from inspirations and ideas.
   Includes source patterns, idea patterns, screen pressure, color observations, tone observations, explicit clustered signals, motif candidates, confidence, and archetype scores.
2. `proposal/direction_options.json`
   Deterministic ranked direction options.
   Includes `selected_direction_id` plus scored, ranked, and explained candidates.
3. `proposal/proposal_candidates.json`
   Rich proposal candidate set for human review.
   Includes 2-3 serious candidates, the deterministic selected direction, non-negotiables, and open questions.
4. `proposal/review_packet.md`
   Human-readable review surface for proposal candidates and the final selection.
5. `proposal/design_direction.md`
   Written design stance.
6. `proposal/visual_language.json`
   Atmosphere, composition, color signal, surface treatment, and motion posture.
7. `proposal/typography_voice.json`
   Font direction, tone, usage principles, and scale adjustments.
8. `proposal/component_motifs.json`
   Reusable motif definitions.
9. `proposal/flow_narrative.md`
   How key app flows should feel.
10. `proposal/anti_patterns.md`
   What to avoid so the result does not feel generic.
11. `proposal/source_rationale.json`
   Coverage and rationale from sources and ideas into the selected direction.

## Implemented Improvement Phases

These proposal-quality improvement phases are already implemented:

1. `phase_1_signals`
   Added `proposal/design_signals.json` as the extracted evidence layer before final direction selection.
2. `phase_2_direction_options`
   Added `proposal/direction_options.json` so the selected direction is ranked, deterministic, and auditable.
3. `phase_3_contract_posture`
   Made the contract derive more materially from proposal posture.
   Current proposal-derived contract behaviors include:
   - spacing rhythm
   - radius and shape posture
   - elevation posture
   - touch target sizing
   - motion timing and pressed scale
   - button and card variants
   - surface style and density profile
4. `phase_4_screen_structure`
   Made screen synthesis structurally proposal-aware instead of mostly template-driven.
   Current proposal-derived screen behaviors include:
   - direction-specific layout strategies
   - direction-specific CTA posture
   - direction-specific chrome density and card usage
   - screen-level motif application with explicit placement metadata
5. `phase_5_validation_effect`
   Extended validation so it checks downstream effect, not just alignment.
   Current effect-style validation behaviors include:
   - direction-specific screen structure fields must match the selected proposal effect
   - screen component patterns must materially reflect CTA posture and chrome density expectations
   - contract posture must remain consistent with screen CTA and chrome behavior
   - motif application must reference real selected proposal motifs and materially surface them in screen components
6. `phase_6_test_expansion`
   Expanded test coverage so richer proposal logic is protected by deterministic, fast gate checks.
   Current test-hardening coverage includes:
   - an additional contrasting-input direction case beyond calm versus utility
   - a prerequisite gate for `proposal_missing`
   - a deterministic ranking gate for `proposal/direction_options.json`
   - stale downstream screen checks that fail on the specific effect-drift error class
7. `phase_7_signal_clustering`
   Added a deterministic clustering layer before archetype scoring so proposal selection is based on grouped repo-aware signals instead of raw combined terms alone.
   Current clustering behaviors include:
   - explicit `signal_clusters` in `proposal/design_signals.json`
   - deterministic cluster ranking with active and dominant cluster metadata
   - cluster-backed archetype scorecards with score breakdown and cluster matches
   - validation that clustered signals exist and align with ranked direction evidence
8. `phase_8_multi_proposal_review`
   Added a richer review layer on top of deterministic ranking.
   Current review-layer behaviors include:
   - `proposal/proposal_candidates.json` with 2-3 serious candidates
   - `proposal/review_packet.md` as the main human review surface
   - explicit selected direction, rejected candidates, non-negotiables, and open questions
   - validation that candidate review artifacts align with ranked options and the selected visual direction
9. `phase_9_config_externalization`
   Moved static orchestration policy out of runtime code into a versioned config layer.
   Current config-externalization behaviors include:
   - versioned policy data in `skills/design-scraper/scripts/mobile_design_orchestrator/config/orchestrator_policies.v1.json`
   - runtime loading through `skills/design-scraper/scripts/mobile_design_orchestrator/config_loader.py`
   - externalized proposal archetypes, signal clusters, screen profiles, and validation posture maps
   - automated proof that runtime policy is sourced from the externalized config layer

## Current State

What is working now:

- proposal generation is no longer a single hidden jump from inspiration to direction
- proposal evidence and ranked options are explicit artifacts
- proposal evidence now includes explicit clustered signals before direction scoring
- proposal review now exposes 2-3 rich candidates before contract generation
- static orchestration policy is now externalized and versioned
- contract posture now reflects the selected proposal direction
- screen structure now reflects the selected proposal direction
- validation now checks proposal alignment and downstream screen/contract effect
- tests now cover additional direction contrast, prerequisite gates, stale screen drift, deterministic option ordering, clustered signal evidence, proposal review coherence, and config loading

What is still limited:

- direction scoring still depends on the current archetype set
- screen structure is still bounded by the current deterministic direction profiles

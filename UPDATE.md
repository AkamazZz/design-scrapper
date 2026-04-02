# Mobile Design Orchestrator Update

## Purpose

The repository now folds mobile design orchestration into the `design-scraper` repo and skill surface.

The scraper collects assets. The orchestration layer interprets them.

## Current Architectural Decision

- The source of truth is a canonical design contract, not platform code.
- Flutter, SwiftUI, and Compose outputs are guidance artifacts, not code emitters.
- Typography, semantics, tokens, and screen composition must stay platform-neutral.
- The canonical contract should carry proposal-derived spacing rhythm, corner posture, motion posture, and component variants.
- Static orchestration policy is now externalized into a versioned config layer instead of being embedded entirely in runtime Python modules.
- Web references are used as inspiration for hierarchy, pacing, and tone, not as layouts to copy directly.

## Current Phase Flow

1. `ingest`
   Convert scraper output into normalized inspiration data.
2. `ideas`
   Capture reusable idea cards linked back to sources.
3. `proposal`
   Create an opinionated design direction that rejects generic AI-looking output before tokens and semantics are generated.
4. `contract`
   Build the canonical design contract from the proposal artifacts.
5. `screens`
   Synthesize mobile-first starter screen definitions from proposal plus contract.
6. `platforms`
   Generate platform-specific guidance for Flutter, SwiftUI, and Compose.
7. `plan`
   Refresh realization status and next steps.
8. `validate`
   Verify that artifacts are coherent, proposal coverage exists, and the workspace is ready for implementation handoff.

## Canonical Contract

The current contract is composed of:

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

These files are the durable design system layer. Platform work should consume them instead of inventing separate interpretations.

## Platform Handoff Model

Platform artifacts now explain how to realize the design instead of generating UI code.

Each platform file is intended to describe:

- design intent
- typography guidance
- visual guidance
- component guidance
- layout guidance
- interaction guidance
- asset guidance
- implementation notes
- known gaps

This keeps the design system reusable across Flutter, SwiftUI, and Compose without locking the repo into framework-specific emitters.

## Current Outputs

The current implementation lives under:

- `skills/design-scraper/`
- `orchestrated/headspace-extended/`
- `skills/design-scraper/scripts/mobile_design_orchestrator/config/orchestrator_policies.v1.json`
- `skills/design-scraper/scripts/mobile_design_orchestrator/config_loader.py`

The sample workspace demonstrates:

- normalized inspiration intake from the Mobbin scrape
- reusable design contract artifacts
- starter mobile screens
- platform guidance outputs
- realization planning
- validation reports

## Verification

Current verification covers:

- Python compilation for orchestrator scripts
- end-to-end orchestration runs from sample scrape input
- validator pass on the generated workspace
- a growing unittest suite for proposal, validation, review, and config-loading behavior

Test file:

- `tests/test_mobile_design_orchestrator.py`

The test exercises:

- `ingest -> ideas -> proposal -> contract -> screens -> platforms -> plan -> validate`
- deterministic clustered scoring
- review artifact coherence
- stale-screen drift gates
- config externalization proof

## Current Status

- The orchestrator scaffold is working end to end.
- The new proposal layer now sits between ideas and contract.
- The proposal layer now includes an explicit extracted-evidence artifact in `proposal/design_signals.json`.
- The extracted-evidence artifact now includes deterministic clustered signals that feed direction scoring.
- The proposal layer now includes deterministic ranked candidates in `proposal/direction_options.json`.
- The proposal layer now includes richer review artifacts in `proposal/proposal_candidates.json` and `proposal/review_packet.md`.
- Static orchestration policy now lives in `skills/design-scraper/scripts/mobile_design_orchestrator/config/orchestrator_policies.v1.json` and is loaded through `skills/design-scraper/scripts/mobile_design_orchestrator/config_loader.py`.
- The contract now derives spacing, radius, motion, and component posture from the selected proposal direction instead of keeping those layers generic.
- Screen synthesis now changes layout strategy, CTA posture, chrome density, card usage, and motif placement by selected proposal direction.
- Validation now fails stale or generic downstream screens even when proposal ids still line up.
- The platform layer is guidance-first, not emitter-based.
- Validation currently passes on the sample workspace.
- The automated suite now covers nine integration and gate scenarios for the current realization.
- Clustered proposal evidence is now covered by automated tests and validation gates.
- Multi-proposal review coherence is now covered by automated tests and validation gates.
- Externalized policy loading is now covered by automated tests and validation gates.

## Recommended Next Work

- separate schema/version governance across proposal, contract, screens, and validation artifacts
- add fixture-based regression coverage beyond the current sample scrape root
- add a compatibility policy or migration path for older generated workspaces
- improve asset guidance for icons, illustrations, and imagery reuse
- refine references so all docs match the current guidance-first architecture

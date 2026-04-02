# Realization Plan

Use this plan when the user wants a practical path from inspiration to implementation.

## Phase 1: Inspiration Intake

- Gather design references with `design-scraper`.
- Normalize source metadata into `inspirations/index.json`.
- Remove noisy or duplicate references from the decision surface.

Exit criteria:
- relevant references are grouped by source and flow
- duplicates and obvious low-signal assets are identified

## Phase 2: Idea Capture

- Review inspirations and capture idea cards.
- Link each idea to source URLs or source assets.
- Separate reusable patterns from one-off visual details.

Exit criteria:
- idea cards exist for major flows, hierarchy patterns, and interaction directions
- ideas describe both intent and rationale

## Phase 3: Proposal Direction

- Create an opinionated design direction before generating tokens or semantics.
- Write down visual language, typography voice, component motifs, flow narrative, anti-patterns, and source rationale.
- Make the design stance explicit enough that downstream files cannot collapse into generic output.

Exit criteria:
- `proposal/` artifacts exist
- proposal coverage points back to inspirations and reviewed ideas
- the direction is specific enough to constrain contract generation

## Phase 4: Canonical Contract

- Define product brief, tokens, typography, and semantics from the proposal.
- Preserve mobile-first constraints before screen detail.
- Keep the contract platform-neutral.

Exit criteria:
- tokens are primitive-only
- typography is reusable
- semantics describe meaning rather than implementation

## Phase 5: Screen Composition

- Define screen structure in `screens/index.json` from proposal plus contract.
- Use semantic roles and canonical component kinds only.
- Keep primary actions obvious and reachable.

Exit criteria:
- screen inventory exists
- each screen uses semantic roles rather than raw values

## Phase 6: Platform Mapping

- Map the canonical contract into Flutter, SwiftUI, and Compose targets.
- Keep platform gaps explicit.
- Do not fork semantics per platform.

Exit criteria:
- mappings exist for all required platforms
- custom implementation gaps are tracked

## Phase 7: Validation

- Run `validate_design_contract.py`.
- Resolve missing proposal coverage, missing references, unmapped roles, or invalid typography.

Exit criteria:
- validator passes or warnings are explicitly accepted

## Phase 8: Implementation Handoff

- Treat the validated contract as the source of truth for code generation or manual implementation.
- Update the contract first when design changes, then regenerate or refine platform code.

Exit criteria:
- engineering handoff references the canonical contract rather than separate platform-only design notes

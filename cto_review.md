# CTO Review: Design Scraper

## Executive Summary

This repository is no longer just a scraper plugin. It is now a two-part product:

1. A design-inspiration ingestion layer that scrapes and organizes reference assets.
2. A mobile design orchestration layer that converts those references into a structured proposal, contract, screens, and platform guidance.

That direction is strategically promising. The strongest part of the repo today is that it has a clear artifact pipeline, deterministic proposal selection, validation that checks for downstream drift, and an increasingly disciplined proposal stack. The strongest engineering weakness is that too much system behavior now lives inside two large Python files: [pipeline.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/pipeline.py) and [project.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/project.py).

The main quality blockers now are:

- Product identity is still somewhat ambiguous between “scraper plugin” and “design system generation product.”
- Policy, orchestration, validation, and content logic are too concentrated in code.
- Artifact evolution has outgrown the current versioning model.
- Operational and legal posture around scraping, browser profiles, and downloaded design assets is not formalized.

The main non-blocking but important next optimizations are:

- Replacing or widening the fixed archetype model that still shapes proposal generation.
- Moving static policy tables and archetype definitions out of code.
- Expanding from synthetic tests to a fixture-based evaluation matrix.

## Product Identity And Scope

The repo currently presents one plugin surface, but it actually contains two products:

- the scraper described in [.codex-plugin/plugin.json](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/.codex-plugin/plugin.json) and [scrape_design.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/scrape_design.py)
- the orchestration system described in [skills/design-scraper/SKILL.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/SKILL.md), [AGENTS.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/AGENTS.md), and [phases.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/phases.md)

That can be a strength if the product thesis is explicit: “reference intake to reusable mobile design handoff.” If that is the thesis, the current repo direction is coherent.

What is still unclear is whether scraping remains the primary value or whether design orchestration is now the primary value and scraping is only the intake layer. That is not a documentation nit. It affects:

- public positioning
- roadmap priority
- legal risk ownership
- test strategy
- plugin ergonomics

Recommendation:

- Decide the north-star product explicitly.
- If the answer is “design orchestration with built-in inspiration intake,” update the public language to match that instead of presenting orchestration as an extension of scraping.

## Architecture Review

Strengths:

- The system has a clear phase pipeline documented in [phases.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/phases.md).
- The proposal-to-contract-to-screen flow is defensible.
- The contract remains platform-neutral, which is the correct architectural decision.
- Validation has become meaningfully downstream-aware instead of checking only file presence.

Risks:

- [pipeline.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/pipeline.py) is now 2,728 lines.
- [project.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/project.py) is now 2,196 lines.
- Those files contain orchestration flow, proposal policy, scoring logic, screen policy, artifact construction, validation rules, and user-facing review behavior.

This is now architectural debt, not just code style.

The specific risk is policy entanglement:

- archetypes live in code
- signal clustering rules live in code
- screen structure profiles live in code
- validation policy lives in code
- artifact schema assumptions live in code

That makes the system harder to evolve safely. A change that should be “policy/config only” currently requires Python changes in the main execution path.

Recommendation:

- Split engine from policy.
- Keep orchestration mechanics in code.
- Move archetypes, cluster definitions, and screen structure profiles into versioned data files.

## Artifact And Schema Review

This is one of the strongest parts of the repo. The artifact model is explicit and increasingly disciplined:

- proposal artifacts
- contract artifacts
- screen artifacts
- platform guidance artifacts
- validation output
- realization metadata

That said, the schema model is behind the maturity of the artifact set.

Current issues:

- Many artifact families still share the same `contract_version` posture.
- Proposal files have grown substantially, but there is no explicit proposal-schema versioning strategy.
- There is no migration or compatibility layer for older generated workspaces.
- Required artifact shape is enforced in [project.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/project.py), but not represented as a separately managed schema contract.

This is now blocking maintainable growth.

Recommendation:

- Introduce separate version tracks for proposal, contract, screens, and validation rule sets.
- Add a compatibility gate for stale workspaces.
- Decide whether schema definitions should remain implied in Python or be externalized into explicit JSON/YAML contracts.

## Reliability And Operational Risks

The repo is operationally useful, but runtime assumptions are still fragile.

Key issues:

- The scraper depends on runtime browser behavior and external site structure.
- Auth-gated scraping depends on persistent browser profiles and operator setup.
- The plugin has environment-sensitive behavior around output paths and Playwright user data.
- There is no CI pipeline in this repo. `.github/` is absent.

There is also a notable documentation-to-code mismatch:

- [skills/design-scraper/SKILL.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/SKILL.md) says Playwright degrades to `http` when unavailable.
- [fetchers.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/design_scraper/fetchers.py) does not enable that fallback in `build_fetcher()` for the default Playwright path.

That kind of mismatch is a real operational risk because users will trust the docs and the system may fail harder than advertised.

Recommendation:

- Align runtime behavior with docs or correct the docs immediately.
- Add a small CI job for compile + unit tests.
- Add a minimal smoke-test matrix for scraper fetch variants and orchestrator validation.

## Testing And Validation Review

Strengths:

- The repo now has meaningful end-to-end tests in [tests/test_mobile_design_orchestrator.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/tests/test_mobile_design_orchestrator.py).
- Validation is not superficial. It checks proposal coherence, contract alignment, screen drift, clustered evidence, and review-layer consistency.

Weaknesses:

- The suite is still a single Python test module.
- The tests are still driven from one local scrape root and synthetic mutations.
- There is no fixture corpus representing multiple real-world scrape profiles.
- There is no CI enforcement.

This is not blocking local development today, but it will become a blocker once artifact schemas start changing faster.

Recommendation:

- Add fixture-based workspaces for calm, utility, playful, and failure cases.
- Add CI enforcement for compile + unit tests.
- Add artifact snapshot expectations where appropriate for review-layer outputs.

## Security / Legal / Data Handling Risks

This is the most under-specified area in the repo.

Risks:

- The system scrapes third-party design sources, some of which are auth-gated.
- It may store downloaded assets, metadata, previews, palette outputs, and user-influenced review artifacts locally.
- Persistent browser profiles are encouraged in docs, but there is no formal data-handling guidance beyond path/mode suggestions.
- The repo currently does not define a position on retention, redistribution, or copyright-sensitive reuse of scraped assets.

This is a real CTO-level issue, not a future polish item.

Recommendation:

- Write a short policy note covering:
  - what is stored
  - what should stay local only
  - how auth profiles should be handled
  - what users should assume about copyright and redistribution
- Make that policy visible in the skill docs and repo-level docs.

## Maintainability Review

Strengths:

- Documentation is much better than typical prototype repos.
- The proposal stack and phase model are explicit.
- The repo has a real architectural center of gravity instead of ad hoc scripts.

Current debt:

- Policy duplication exists across [AGENTS.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/AGENTS.md), [skills/design-scraper/SKILL.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/SKILL.md), [UPDATE.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/UPDATE.md), and [phases.md](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/phases.md).
- The proposal system is now mature enough that data-driven config should replace some code-defined policy.
- Runtime, policy, and documentation are at risk of drifting apart unless there is a clearer governance model.

Recommendation:

- Reduce documentation duplication by making one file canonical for roadmap and one canonical for operator instructions.
- Externalize policy tables.
- Add schema/version governance before expanding artifact families further.

## Recommendations

Blocking quality now:

- Clarify product identity and operating scope.
- Externalize policy tables from orchestration code.
- Introduce artifact family versioning and workspace compatibility checks.
- Resolve the Playwright fallback documentation/runtime mismatch.
- Add a minimal CI gate.
- Add a repo-visible legal/data-handling note.

Important next, but not blocking this week:

- Move from archetype-backed candidate composition toward broader proposal composition.
- Add a fixture matrix for more realistic regression coverage.
- Add a formal approval or operator-review state between proposal review and contract generation.

Later optimization:

- richer proposal evaluation heuristics
- more granular platform guidance specialization
- migration tooling for historical workspaces

## Prioritized Next Steps

1. Define the product boundary in writing.
   Decide whether this is primarily a scraper plugin or a design orchestration product with built-in intake.

2. Implement config externalization.
   Move archetypes, cluster definitions, and screen policy tables out of [pipeline.py](/Users/tamerlanaltynbek/habit_to_do/habit_to_do/plugins/design-scraper/skills/design-scraper/scripts/mobile_design_orchestrator/pipeline.py).

3. Add schema/version separation.
   Proposal, contract, screens, and validation should not all evolve under one implicit version posture.

4. Add CI and fixture-based validation.
   Start with compile + unittest, then add a small fixture corpus.

5. Publish a data/legal handling note.
   This is required if the project is going to be used beyond private experimentation.

6. Only after the above, invest in broader proposal composition.
   The next design-quality leap should come from candidate composition that is less tied to fixed archetypes.


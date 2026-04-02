# Platform Guidance

Platform files are structured handoff notes from the canonical contract to implementation targets.

## Principle

The canonical contract owns:

- proposal direction and rationale
- tokens
- typography
- semantics
- screens

Platform files own:

- implementation guidance for typography, layout, components, and interaction tone
- unavoidable platform-specific gaps
- notes that help engineers preserve the design intent without reinterpreting it

## Mapping Rules

- Do not add new semantics in platform files.
- Do not sand away the proposal direction into generic platform defaults.
- Keep guidance stable enough that an engineer can implement the screen without inventing a second design language.
- Record unsupported elements in `gaps` instead of guessing.
- Preserve accessibility requirements from the brief and semantic contract.

## Flutter

- Explain how typography roles should live in the theme layer.
- Explain how semantic colors should appear and where they belong in the visual hierarchy.
- Explain how semantic components should behave and what not to compromise.
- Keep custom implementation needs explicit in `gaps`.

## SwiftUI

- Prefer environment-driven `Font`, `Color`, and style wrappers over hardcoded per-screen values.
- Describe how navigation and container semantics should feel in SwiftUI without leaking platform structure into the canonical contract.
- Keep gaps explicit when a custom `ViewModifier`, `Shape`, or environment model is required.

## Compose

- Prefer theme-level `Typography`, `ColorScheme`, and shape layers.
- Describe semantics in terms of reusable composables or wrappers instead of one-off screen code.
- Call out custom composables when Material primitives are insufficient.

## Review Checklist

- Every used text role has implementation guidance.
- Every used component role has implementation guidance.
- Every used semantic color or state role is explained or intentionally deferred.
- Accessibility survives the handoff.
- Platform deltas are explicit and minimal.

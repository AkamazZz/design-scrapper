from __future__ import annotations

from typing import Any, Iterable, Mapping

from mobile_design_orchestrator.project import now_iso
from mobile_design_orchestrator.review import REVIEW_SCHEMA_VERSION, review_artifact_envelope, tokenize_text
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

CRITIC_VERSION = "heuristic_v1"
_DIRECTION_FIELDS = ("direction_name", "motion_posture", "surface_treatment", "composition_principles", "primary_motifs")
_DENSITY_BANDS = {
    "minimal": {"components": (2, 7), "words": (0, 26)},
    "low": {"components": (2, 7), "words": (0, 26)},
    "compact": {"components": (5, 11), "words": (10, 50)},
    "balanced": {"components": (5, 12), "words": (12, 60)},
    "moderate": {"components": (5, 12), "words": (12, 60)},
    "comfortable": {"components": (5, 12), "words": (12, 60)},
    "relaxed": {"components": (4, 10), "words": (10, 52)},
    "high": {"components": (8, 18), "words": (18, 90)},
    "dense": {"components": (8, 18), "words": (18, 90)},
    "busy": {"components": (8, 18), "words": (18, 90)},
}
_TASK_HINTS = {
    "app_shell": {
        "kinds": {"tab_bar", "nav_bar", "badge"},
        "tokens": {"navigation", "tab", "route", "global", "browse"},
        "primary_action_expected": False,
    },
    "home": {
        "kinds": {"card", "progress", "list", "button"},
        "tokens": {"dashboard", "summary", "progress", "today", "metric", "next", "action"},
        "primary_action_expected": True,
    },
    "onboarding": {
        "kinds": {"text_field", "secure_field", "toggle", "checkbox", "radio", "button", "progress"},
        "tokens": {"goal", "setup", "welcome", "plan", "permission", "start"},
        "primary_action_expected": True,
    },
    "detail": {
        "kinds": {"card", "list", "button", "image", "progress"},
        "tokens": {"detail", "history", "metric", "next", "session", "entity"},
        "primary_action_expected": True,
    },
    "profile": {
        "kinds": {"avatar", "list", "toggle", "button", "card"},
        "tokens": {"profile", "account", "plan", "settings", "preference", "membership"},
        "primary_action_expected": True,
    },
    "progress": {
        "kinds": {"progress", "badge", "card", "list"},
        "tokens": {"progress", "streak", "milestone", "trend", "history", "goal"},
        "primary_action_expected": False,
    },
    "paywall": {
        "kinds": {"card", "chip", "list", "button"},
        "tokens": {"plan", "upgrade", "trial", "premium", "subscription", "price", "value"},
        "primary_action_expected": True,
    },
}


def score_direction_fit(variant: Mapping[str, Any]) -> dict[str, Any]:
    direction_context = variant.get("direction_context", {})
    proposal_alignment = variant.get("proposal_alignment", {})
    signals: list[str] = []
    issues: list[str] = []
    measurements: dict[str, Any] = {}

    direction_tokens = set()
    for field in _DIRECTION_FIELDS:
        direction_tokens.update(tokenize_text((direction_context or {}).get(field)))
        direction_tokens.update(tokenize_text((proposal_alignment or {}).get(field)))

    observed_tokens = _observed_tokens(variant)
    overlap = sorted(direction_tokens & observed_tokens)
    measurements["direction_token_overlap"] = overlap[:10]
    score = 0.15

    structure_fields = ("layout_strategy", "cta_posture", "chrome_density", "card_usage")
    present_fields = sum(1 for field in structure_fields if variant.get(field) and variant.get(field) != "unspecified")
    score += 0.25 * (present_fields / len(structure_fields))
    if present_fields == len(structure_fields):
        signals.append("The variant defines the key structure fields the validator already expects.")
    else:
        issues.append("Some screen structure fields are still missing, which weakens direction fit.")

    primary_motif = ((variant.get("motif_application") or {}).get("primary_motif") or "").strip()
    aligned_motifs = set(_string_sequence((proposal_alignment or {}).get("primary_motifs"))) | set(
        _string_sequence((direction_context or {}).get("primary_motifs"))
    )
    if primary_motif:
        score += 0.15
        signals.append(f"Primary motif `{primary_motif}` is explicitly attached to the variant.")
    else:
        issues.append("No primary motif is attached yet, so stylistic carry-through is mostly inferred.")
    if primary_motif and primary_motif in aligned_motifs:
        score += 0.15
        signals.append("Primary motif matches the proposal guidance.")
    elif aligned_motifs:
        issues.append("Motif application does not clearly line up with the proposal guidance.")

    if direction_tokens:
        overlap_ratio = min(1.0, len(overlap) / max(4, min(len(direction_tokens), 8)))
        score += 0.30 * overlap_ratio
        if overlap:
            signals.append(f"Direction vocabulary carries into the variant metadata: {', '.join(overlap[:4])}.")
        else:
            issues.append("Direction context exists, but almost none of its vocabulary appears in the variant metadata.")
    else:
        issues.append("Direction context is thin, so fit is being judged mostly from structural metadata.")

    if not variant.get("components"):
        score -= 0.15
        issues.append("No components are present, so this fit score is only a placeholder.")

    return _dimension_result(score, signals, issues, measurements)


def score_hierarchy_clarity(variant: Mapping[str, Any]) -> dict[str, Any]:
    measurements = dict(variant.get("measurements", {}))
    component_count = int(measurements.get("component_count", 0))
    primary_button_count = int(measurements.get("primary_button_count", 0))
    primary_button_index = measurements.get("primary_button_index")
    headline_count = int(measurements.get("headline_count", 0))
    text_role_count = int(measurements.get("text_role_count", 0))
    unique_kind_count = int(measurements.get("unique_kind_count", 0))
    cta_posture = str(variant.get("cta_posture") or "unspecified")
    signals: list[str] = []
    issues: list[str] = []
    score = 0.15

    if headline_count:
        score += 0.18
        signals.append("A headline-like text element gives the screen an obvious entry point.")
    else:
        issues.append("No headline-like text element was found, so the first focal point is ambiguous.")

    if cta_posture == "none":
        if primary_button_count == 0:
            score += 0.20
            signals.append("CTA posture is `none` and no primary button is present, which is internally consistent.")
        else:
            issues.append("CTA posture is `none`, but a primary button is still present.")
    else:
        if primary_button_count:
            score += 0.18
            signals.append("A primary action is present for a screen that appears to need one.")
        else:
            issues.append(f"CTA posture is `{cta_posture}`, but no `button.primary` was found.")

    if primary_button_count and primary_button_index is not None:
        if cta_posture in {"footer_single", "delayed_footer"} and primary_button_index == component_count - 1:
            score += 0.12
            signals.append("Primary action sits at the end of the component stack, matching footer CTA posture.")
        elif cta_posture == "inline_action_strip":
            first_list_index = _first_component_index(variant, {"list", "divider"})
            if first_list_index is None or int(primary_button_index) < first_list_index:
                score += 0.12
                signals.append("Primary action stays ahead of list chrome for inline action posture.")
            else:
                issues.append("Primary action appears after list chrome, which weakens scan order.")
        elif int(primary_button_index) <= max(2, component_count // 3):
            score += 0.08
            signals.append("Primary action appears early enough to stay visible during the first scan.")
        else:
            issues.append("Primary action is present but lands fairly late in the component order.")

    if 4 <= component_count <= 12:
        score += 0.14
        signals.append("Component count is in a readable range for a first-pass mobile hierarchy.")
    elif component_count > 16:
        issues.append("Component count is high enough that the hierarchy will likely feel crowded.")
    elif component_count and component_count < 3:
        issues.append("Very few components are present, so the hierarchy may be underdeveloped.")

    if 2 <= text_role_count <= 5:
        score += 0.10
        signals.append("Text roles show more than one level of emphasis.")
    elif text_role_count <= 1:
        issues.append("Text roles look flat, which limits hierarchy clarity.")

    if unique_kind_count <= 6:
        score += 0.08
        signals.append("The component mix stays focused instead of branching across too many kinds.")
    else:
        issues.append("Too many component kinds are competing for attention in one screen.")

    if _top_of_stack_has_signal(variant):
        score += 0.08
        signals.append("The first three components contain obvious entry-point content.")
    else:
        issues.append("The top of the stack does not expose a strong entry signal yet.")

    return _dimension_result(score, signals, issues, measurements)


def score_density(variant: Mapping[str, Any]) -> dict[str, Any]:
    measurements = dict(variant.get("measurements", {}))
    component_count = int(measurements.get("component_count", 0))
    text_word_count = int(measurements.get("text_word_count", 0))
    card_count = int(measurements.get("card_count", 0))
    chrome_density = str(variant.get("chrome_density") or "balanced").lower()
    card_usage = str(variant.get("card_usage") or "unspecified").lower()
    targets = _density_targets(chrome_density)
    signals: list[str] = []
    issues: list[str] = []

    component_score = _range_score(component_count, *targets["components"])
    word_score = _range_score(text_word_count, *targets["words"])
    score = 0.10 + (0.45 * component_score) + (0.30 * word_score)

    if component_score >= 0.9:
        signals.append(f"Component count fits the `{chrome_density}` density target well.")
    elif component_count > targets["components"][1]:
        issues.append(f"Component count is above the `{chrome_density}` density target.")
    elif component_count < targets["components"][0] and component_count:
        issues.append(f"Component count is below the `{chrome_density}` density target.")
    else:
        issues.append("Density posture is still approximate because the structure is underspecified.")

    if word_score >= 0.9:
        signals.append("Text volume sits in the expected range for the chosen density.")
    elif text_word_count > targets["words"][1]:
        issues.append("Copy volume looks high for the chosen density posture.")
    elif component_count and text_word_count < targets["words"][0]:
        issues.append("Copy volume looks low for the chosen density posture.")

    if "none" in card_usage:
        if card_count == 0:
            score += 0.10
            signals.append("Card usage is intentionally off and the component mix respects that.")
        else:
            issues.append("Card usage says `none`, but card components are still present.")
    elif "card" in card_usage or "stack" in card_usage:
        if card_count >= 1:
            score += min(0.12, 0.04 * card_count)
            signals.append("Card usage is reflected in the component inventory.")
        else:
            issues.append("Card usage suggests grouped surfaces, but no cards were found.")
    else:
        score += 0.05

    return _dimension_result(score, signals, issues, measurements)


def score_task_fit(variant: Mapping[str, Any]) -> dict[str, Any]:
    screen_id = str(variant.get("screen_id") or "screen")
    hints = dict(_TASK_HINTS.get(screen_id, {}))
    expected_kinds = set(hints.get("kinds", set()))
    expected_tokens = set(hints.get("tokens", set()))
    job_tokens = tokenize_text(variant.get("jobs_to_be_done")) | tokenize_text(variant.get("primary_data")) | tokenize_text(variant.get("purpose"))
    observed_kinds = {str(component.get("kind")) for component in variant.get("components", []) if component.get("kind")}
    observed_tokens = _observed_tokens(variant)
    signals: list[str] = []
    issues: list[str] = []
    measurements: dict[str, Any] = {
        "expected_kinds": sorted(expected_kinds),
        "matched_kinds": sorted(expected_kinds & observed_kinds),
        "job_token_overlap": sorted(job_tokens & observed_tokens)[:10],
    }
    score = 0.12

    if expected_kinds:
        kind_overlap = expected_kinds & observed_kinds
        score += 0.28 * min(1.0, len(kind_overlap) / max(2, len(expected_kinds)))
        if kind_overlap:
            signals.append(f"Component kinds support the core `{screen_id}` task: {', '.join(sorted(kind_overlap))}.")
        else:
            issues.append(f"Component kinds do not yet reflect the expected `{screen_id}` task shape.")

    token_overlap = (expected_tokens | job_tokens) & observed_tokens
    if expected_tokens or job_tokens:
        score += 0.28 * min(1.0, len(token_overlap) / max(4, len(expected_tokens | job_tokens)))
        if token_overlap:
            signals.append(f"Task vocabulary shows up in the variant metadata: {', '.join(sorted(token_overlap)[:4])}.")
        else:
            issues.append("Jobs, purpose, and primary data are not well represented in the current metadata.")

    primary_action_expected = bool(hints.get("primary_action_expected", False))
    primary_button_count = int((variant.get("measurements") or {}).get("primary_button_count", 0))
    if primary_action_expected:
        if primary_button_count:
            score += 0.14
            signals.append("A primary action is present for a task-oriented screen.")
        else:
            issues.append("This screen type usually needs a clear primary action, but none is present.")
    else:
        score += 0.08

    if screen_id == "app_shell":
        navigation_count = int((variant.get("measurements") or {}).get("navigation_count", 0))
        if navigation_count:
            score += 0.12
            signals.append("Navigation chrome is present for the shell screen.")
        else:
            issues.append("App shell variants should expose navigation chrome explicitly.")
    elif variant.get("navigation_edges"):
        score += 0.08
        signals.append("Navigation edges are documented, which helps downstream review.")

    if variant.get("required_states"):
        score += 0.08
        signals.append("Required states are already attached, which improves task coverage.")

    return _dimension_result(score, signals, issues, measurements)


def score_variant(variant: Mapping[str, Any]) -> dict[str, Any]:
    dimensions = {
        "direction_fit": score_direction_fit(variant),
        "hierarchy_clarity": score_hierarchy_clarity(variant),
        "density": score_density(variant),
        "task_fit": score_task_fit(variant),
    }
    overall_score = int(round(sum(detail["score"] for detail in dimensions.values()) / len(dimensions)))
    return {
        "screen_id": variant.get("screen_id"),
        "variant_id": variant.get("variant_id"),
        "variant_key": variant.get("variant_key"),
        "source_path": variant.get("source_path"),
        "overall": {
            "score": overall_score,
            "band": _score_band(overall_score),
        },
        "dimensions": dimensions,
    }


def score_variants(variants: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scored = [score_variant(variant) for variant in variants]
    scored.sort(key=lambda item: (-int(item["overall"]["score"]), str(item.get("screen_id") or ""), str(item.get("variant_id") or "")))
    return scored


def build_scores_artifact(
    scores: Iterable[Mapping[str, Any]],
    *,
    project: str,
    source_dir: str,
    generated_at: str | None = None,
    run_id: str = "manual",
    workspace_version: str = "v2",
) -> dict[str, Any]:
    generated_at = generated_at or now_iso()
    records = [dict(score) for score in scores]
    metadata = build_artifact_version_metadata(
        phase="critic",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=REVIEW_SCHEMA_VERSION,
    )
    metadata.update(
        {
            "critic_version": CRITIC_VERSION,
            "source_dir": source_dir,
        }
    )
    summary = {
        "variant_count": len(records),
        "average_overall_score": _average((record.get("overall") or {}).get("score", 0) for record in records),
        "average_dimension_scores": {
            name: _average(((record.get("dimensions") or {}).get(name) or {}).get("score", 0) for record in records)
            for name in ("direction_fit", "hierarchy_clarity", "density", "task_fit")
        },
    }
    return review_artifact_envelope(
        project=project,
        artifact_type="critic_scores",
        generated_at=generated_at,
        records=records,
        metadata=metadata,
        summary=summary,
    )


def _dimension_result(score: float, signals: list[str], issues: list[str], measurements: Mapping[str, Any]) -> dict[str, Any]:
    bounded = max(0, min(100, int(round(score * 100))))
    return {
        "score": bounded,
        "signals": signals,
        "issues": issues,
        "measurements": dict(measurements),
    }


def _observed_tokens(variant: Mapping[str, Any]) -> set[str]:
    tokens = set()
    tokens.update(tokenize_text(variant.get("screen_id")))
    tokens.update(tokenize_text(variant.get("screen_title")))
    tokens.update(tokenize_text(variant.get("variant_name")))
    tokens.update(tokenize_text(variant.get("layout_strategy")))
    tokens.update(tokenize_text(variant.get("cta_posture")))
    tokens.update(tokenize_text(variant.get("chrome_density")))
    tokens.update(tokenize_text(variant.get("card_usage")))
    tokens.update(tokenize_text(variant.get("motif_application")))
    for component in variant.get("components", []):
        tokens.update(tokenize_text(component.get("kind")))
        tokens.update(tokenize_text(component.get("semantic_role")))
        tokens.update(tokenize_text(component))
    return tokens


def _first_component_index(variant: Mapping[str, Any], kinds: set[str]) -> int | None:
    for index, component in enumerate(variant.get("components", [])):
        if component.get("kind") in kinds:
            return index
    return None


def _top_of_stack_has_signal(variant: Mapping[str, Any]) -> bool:
    components = variant.get("components", [])[:3]
    for component in components:
        role = str(component.get("semantic_role") or "").lower()
        kind = str(component.get("kind") or "").lower()
        if component.get("semantic_role") == "button.primary":
            return True
        if any(token in role for token in ("headline", "title", "hero")):
            return True
        if kind in {"card", "progress", "image"}:
            return True
    return False


def _density_targets(chrome_density: str) -> dict[str, tuple[int, int]]:
    normalized = chrome_density.strip().lower()
    if normalized in _DENSITY_BANDS:
        return _DENSITY_BANDS[normalized]
    if normalized in {"airy", "spacious", "quiet"}:
        return {"components": (3, 9), "words": (8, 48)}
    return _DENSITY_BANDS["balanced"]


def _range_score(value: int, low: int, high: int) -> float:
    if value == 0 and low == 0:
        return 1.0
    if low <= value <= high:
        return 1.0
    if value < low:
        distance = low - value
        span = max(low, 1)
        return max(0.0, 1.0 - (distance / span))
    distance = value - high
    span = max(high, 1)
    return max(0.0, 1.0 - (distance / span))


def _score_band(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "promising"
    if score >= 55:
        return "workable"
    return "weak"


def _average(values: Iterable[object]) -> int:
    numbers = [int(value) for value in values]
    if not numbers:
        return 0
    return int(round(sum(numbers) / len(numbers)))


def _string_sequence(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.config_loader import load_orchestrator_config

DEFAULT_PLATFORMS = ("flutter", "swiftui", "compose")
CANONICAL_COMPONENT_KINDS = (
    "text",
    "image",
    "icon",
    "button",
    "text_field",
    "secure_field",
    "toggle",
    "checkbox",
    "radio",
    "card",
    "list",
    "list_item",
    "tab_bar",
    "nav_bar",
    "bottom_sheet",
    "dialog",
    "divider",
    "chip",
    "badge",
    "avatar",
    "progress",
    "placeholder_block",
    "stack",
    "spacer",
    "container",
)

REQUIRED_FILES = {
    "proposal/design_signals.json": (
        "contract_version",
        "project",
        "source_patterns",
        "idea_patterns",
        "screen_pressure",
        "color_observations",
        "tone_observations",
        "signal_clusters",
        "motif_candidates",
        "confidence",
        "archetype_scores",
    ),
    "proposal/direction_options.json": (
        "contract_version",
        "project",
        "selected_direction_id",
        "options",
    ),
    "proposal/proposal_candidates.json": (
        "contract_version",
        "project",
        "selected_direction_id",
        "candidate_count",
        "candidates",
        "non_negotiables",
        "open_questions",
    ),
    "proposal/visual_language.json": (
        "contract_version",
        "direction_id",
        "direction_name",
        "atmosphere",
        "composition_principles",
        "color_signal",
        "surface_treatment",
        "motion_posture",
    ),
    "proposal/typography_voice.json": (
        "contract_version",
        "direction_id",
        "voice_name",
        "font_family",
        "fallbacks",
        "headline_tone",
        "body_tone",
        "usage_principles",
    ),
    "proposal/component_motifs.json": (
        "contract_version",
        "direction_id",
        "direction_name",
        "motifs",
    ),
    "proposal/source_rationale.json": (
        "contract_version",
        "direction_id",
        "direction_name",
        "source_coverage",
        "idea_coverage",
        "decision_summary",
    ),
    "contract/brief.json": (
        "contract_version",
        "project",
        "platform_targets",
        "design_principles",
        "brand",
        "localization",
        "accessibility",
        "content_strategy",
        "technical_constraints",
        "deliverables",
    ),
    "contract/tokens.json": (
        "contract_version",
        "color",
        "spacing",
        "radius",
        "size",
        "elevation",
        "opacity",
        "motion",
        "border",
        "z_index",
    ),
    "contract/typography.json": (
        "contract_version",
        "font_families",
        "font_weights",
        "type_scales",
        "text_styles",
        "defaults",
    ),
    "contract/semantics.json": (
        "contract_version",
        "themes",
        "text_roles",
        "spacing_roles",
        "shape_roles",
        "state_roles",
        "component_roles",
    ),
    "screens/index.json": (
        "contract_version",
        "allowed_component_kinds",
        "screen_rules",
        "screens",
    ),
}

PROPOSAL_MARKDOWN_FILES = (
    "proposal/design_direction.md",
    "proposal/review_packet.md",
    "proposal/flow_narrative.md",
    "proposal/anti_patterns.md",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "mobile-project"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_markdown(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n")


def scaffold_json(path: Path, data: Any, actions: list[dict[str, str]], force: bool = False) -> None:
    if path.exists() and not force:
        actions.append({"path": str(path), "action": "skipped"})
        return
    action = "updated" if path.exists() else "created"
    write_json(path, data)
    actions.append({"path": str(path), "action": action})


def scaffold_markdown(path: Path, text: str, actions: list[dict[str, str]], force: bool = False) -> None:
    if path.exists() and not force:
        actions.append({"path": str(path), "action": "skipped"})
        return
    action = "updated" if path.exists() else "created"
    write_markdown(path, text)
    actions.append({"path": str(path), "action": action})


def load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def latest_run_report(metadata_dir: Path) -> Path | None:
    reports = sorted(metadata_dir.glob("run_*.json"), key=lambda item: item.stat().st_mtime)
    return reports[-1] if reports else None


def summarize_scrape_root(scrape_root: Path) -> dict[str, Any]:
    manifest_path = scrape_root / "metadata" / "index.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing scrape manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    color_summary = load_optional_json(scrape_root / "color_summary.json") or {}
    duplicates = load_optional_json(scrape_root / "duplicates.json") or {}
    run_report_path = latest_run_report(scrape_root / "metadata")
    run_report = read_json(run_report_path) if run_report_path else {}

    source_lookup: dict[str, dict[str, Any]] = {}
    for adapter_result in run_report.get("adapter_results", []):
        for key in (adapter_result.get("url"), adapter_result.get("normalized_url")):
            if key:
                source_lookup[key] = {
                    "source": adapter_result.get("source"),
                    "title": adapter_result.get("title"),
                    "status": adapter_result.get("status"),
                    "metadata": adapter_result.get("metadata", {}),
                }

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_url": None,
            "source": None,
            "title": None,
            "status": None,
            "asset_count": 0,
            "fallback_screenshot_count": 0,
            "assets": [],
        }
    )

    for local_path, asset in manifest.get("assets", {}).items():
        source_url = asset.get("source_url") or "unknown"
        info = grouped[source_url]
        info["source_url"] = source_url
        adapter_info = source_lookup.get(source_url, {})
        info["source"] = info["source"] or adapter_info.get("source")
        info["title"] = info["title"] or adapter_info.get("title")
        info["status"] = info["status"] or adapter_info.get("status")
        info["asset_count"] += 1
        if asset.get("fallback_screenshot"):
            info["fallback_screenshot_count"] += 1
        info["assets"].append(
            {
                "local_path": asset.get("local_path", local_path),
                "canonical_url": asset.get("canonical_url"),
                "kind": asset.get("kind"),
                "mime_type": asset.get("mime_type"),
                "file_size": asset.get("file_size"),
                "fallback_screenshot": asset.get("fallback_screenshot", False),
                "warnings": asset.get("warnings", []),
            }
        )

    sources = sorted(grouped.values(), key=lambda item: (item["source"] or "", item["source_url"] or ""))
    asset_count = sum(item["asset_count"] for item in sources)

    return {
        "imported_at": now_iso(),
        "scrape_root": str(scrape_root),
        "files": {
            "manifest": str(manifest_path),
            "run_report": str(run_report_path) if run_report_path else None,
            "color_summary": str(scrape_root / "color_summary.json") if color_summary else None,
            "duplicates": str(scrape_root / "duplicates.json") if duplicates else None,
        },
        "source_count": len(sources),
        "asset_count": asset_count,
        "duplicate_group_count": len(duplicates.get("duplicate_groups", [])),
        "most_common_colors": color_summary.get("most_common_colors", []),
        "dark_mode_count": color_summary.get("dark_mode_count"),
        "light_mode_count": color_summary.get("light_mode_count"),
        "sources": sources,
    }


def default_ideas(project_slug: str) -> dict[str, Any]:
    return {
        "project": project_slug,
        "idea_fields": [
            "idea_id",
            "title",
            "summary",
            "rationale",
            "pattern_category",
            "source_urls",
            "source_assets",
            "target_screens",
            "status",
            "created_at",
        ],
        "ideas": [],
    }


def _proposal_part(proposal_bundle: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not proposal_bundle:
        return {}
    value = proposal_bundle.get(key, {})
    return value if isinstance(value, dict) else {}


def _proposal_direction_id(proposal_bundle: dict[str, Any] | None) -> str | None:
    return _proposal_part(proposal_bundle, "visual_language").get("direction_id")


def _proposal_direction_name(proposal_bundle: dict[str, Any] | None) -> str | None:
    return _proposal_part(proposal_bundle, "visual_language").get("direction_name")


def _proposal_motifs(proposal_bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    motifs = _proposal_part(proposal_bundle, "component_motifs").get("motifs", [])
    return [motif for motif in motifs if isinstance(motif, dict)]


def _raw_value_tokens(values: tuple[int, ...]) -> dict[str, dict[str, int]]:
    return {str(value): {"value": value} for value in values}


def _proposal_contract_profile(proposal_bundle: dict[str, Any] | None) -> dict[str, Any]:
    visual_language = _proposal_part(proposal_bundle, "visual_language")
    direction_id = _proposal_direction_id(proposal_bundle) or ""
    surface_text = " ".join(
        [
            visual_language.get("surface_treatment", ""),
            *visual_language.get("composition_principles", []),
        ]
    ).lower()
    motion_text = (visual_language.get("motion_posture") or "").lower()
    motif_text = " ".join(
        " ".join(
            [
                motif.get("id", ""),
                motif.get("name", ""),
                motif.get("intent", ""),
                " ".join(motif.get("applicable_screens", [])),
            ]
        )
        for motif in _proposal_motifs(proposal_bundle)
    ).lower()

    if (
        direction_id == "utility_bold"
        or "tight spacing" in surface_text
        or "clean edges" in surface_text
        or "metric" in motif_text
    ):
        return {
            "density_profile": "compact",
            "spacing_rhythm": "tight_modular",
            "shape_profile": "crisp_modular",
            "motion_profile": "functional_fast",
            "spacing_values": (0, 4, 8, 12, 16, 20, 24, 32),
            "spacing_roles": {
                "screen.padding.horizontal": "spacing.16",
                "screen.padding.vertical": "spacing.20",
                "section.gap": "spacing.20",
                "stack.gap.default": "spacing.8",
                "stack.gap.tight": "spacing.4",
                "component.padding.card": "spacing.16",
                "component.padding.button.horizontal": "spacing.20",
            },
            "radius_values": {"sm": 6, "md": 10, "lg": 14},
            "shape_roles": {
                "card.corner": "radius.sm",
                "button.corner": "radius.md",
                "hero.corner": "radius.md",
                "badge.corner": "radius.sm",
            },
            "touch_min": 44,
            "elevation_values": {"0": 0, "1": 2, "2": 6},
            "disabled_opacity": 0.38,
            "motion_values": {
                "duration.fast": 100,
                "duration.normal": 180,
                "duration.slow": 240,
                "curve.standard": "standard_accelerated",
                "scale.pressed": 0.97,
            },
            "paragraph_spacing": 2,
            "light_surface_card": "color.white",
            "button_variant": "precision_block",
            "secondary_button_variant": "quiet_outline",
            "card_style": "segmented_modular",
            "button_elevation": "elevation.1",
            "secondary_button_elevation": "elevation.0",
            "card_elevation": "elevation.1",
            "hero_elevation": "elevation.2",
        }

    if (
        direction_id == "playful_modular"
        or "roomy icon moments" in surface_text
        or "reward" in motion_text
        or "badge" in motif_text
    ):
        return {
            "density_profile": "relaxed",
            "spacing_rhythm": "buoyant_modular",
            "shape_profile": "rounded_modular",
            "motion_profile": "reward_brisk",
            "spacing_values": (0, 4, 8, 12, 16, 18, 24, 32, 40),
            "spacing_roles": {
                "screen.padding.horizontal": "spacing.18",
                "screen.padding.vertical": "spacing.24",
                "section.gap": "spacing.24",
                "stack.gap.default": "spacing.12",
                "stack.gap.tight": "spacing.8",
                "component.padding.card": "spacing.18",
                "component.padding.button.horizontal": "spacing.24",
            },
            "radius_values": {"sm": 12, "md": 18, "lg": 24},
            "shape_roles": {
                "card.corner": "radius.md",
                "button.corner": "radius.lg",
                "hero.corner": "radius.lg",
                "badge.corner": "radius.lg",
            },
            "touch_min": 48,
            "elevation_values": {"0": 0, "1": 3, "2": 7},
            "disabled_opacity": 0.42,
            "motion_values": {
                "duration.fast": 110,
                "duration.normal": 200,
                "duration.slow": 260,
                "curve.standard": "ease_out_lively",
                "scale.pressed": 0.97,
            },
            "paragraph_spacing": 3,
            "light_surface_card": "color.neutral.100",
            "button_variant": "reward_pill",
            "secondary_button_variant": "supporting_soft",
            "card_style": "accented_modular",
            "button_elevation": "elevation.1",
            "secondary_button_elevation": "elevation.0",
            "card_elevation": "elevation.1",
            "hero_elevation": "elevation.2",
        }

    if (
        direction_id == "premium_cinematic"
        or "negative space" in surface_text
        or "minimal chrome" in surface_text
        or "immersive" in motif_text
    ):
        return {
            "density_profile": "spacious",
            "spacing_rhythm": "editorial_negative_space",
            "shape_profile": "restrained_refined",
            "motion_profile": "polished_slow",
            "spacing_values": (0, 4, 8, 12, 16, 24, 32, 48),
            "spacing_roles": {
                "screen.padding.horizontal": "spacing.24",
                "screen.padding.vertical": "spacing.24",
                "section.gap": "spacing.32",
                "stack.gap.default": "spacing.12",
                "stack.gap.tight": "spacing.8",
                "component.padding.card": "spacing.24",
                "component.padding.button.horizontal": "spacing.24",
            },
            "radius_values": {"sm": 4, "md": 10, "lg": 16},
            "shape_roles": {
                "card.corner": "radius.md",
                "button.corner": "radius.md",
                "hero.corner": "radius.lg",
                "badge.corner": "radius.sm",
            },
            "touch_min": 48,
            "elevation_values": {"0": 0, "1": 1, "2": 4},
            "disabled_opacity": 0.44,
            "motion_values": {
                "duration.fast": 130,
                "duration.normal": 260,
                "duration.slow": 340,
                "curve.standard": "ease_in_out_refined",
                "scale.pressed": 0.985,
            },
            "paragraph_spacing": 4,
            "light_surface_card": "color.white",
            "button_variant": "quiet_prominence",
            "secondary_button_variant": "quiet_text",
            "card_style": "quiet_frame",
            "button_elevation": "elevation.0",
            "secondary_button_elevation": "elevation.0",
            "card_elevation": "elevation.0",
            "hero_elevation": "elevation.1",
        }

    return {
        "density_profile": "airy",
        "spacing_rhythm": "breathing_room",
        "shape_profile": "rounded_soft",
        "motion_profile": "gentle",
        "spacing_values": (0, 4, 8, 12, 16, 20, 24, 28, 32, 40),
        "spacing_roles": {
            "screen.padding.horizontal": "spacing.20",
            "screen.padding.vertical": "spacing.24",
            "section.gap": "spacing.28",
            "stack.gap.default": "spacing.12",
            "stack.gap.tight": "spacing.8",
            "component.padding.card": "spacing.20",
            "component.padding.button.horizontal": "spacing.24",
        },
        "radius_values": {"sm": 10, "md": 16, "lg": 24},
        "shape_roles": {
            "card.corner": "radius.md",
            "button.corner": "radius.lg",
            "hero.corner": "radius.lg",
            "badge.corner": "radius.sm",
        },
        "touch_min": 48,
        "elevation_values": {"0": 0, "1": 2, "2": 5},
        "disabled_opacity": 0.46,
        "motion_values": {
            "duration.fast": 140,
            "duration.normal": 240,
            "duration.slow": 320,
            "curve.standard": "ease_out_soft",
            "scale.pressed": 0.99,
        },
        "paragraph_spacing": 4,
        "light_surface_card": "color.neutral.100",
        "button_variant": "pill_single_cta",
        "secondary_button_variant": "quiet_text",
        "card_style": "matte_layers",
        "button_elevation": "elevation.0",
        "secondary_button_elevation": "elevation.0",
        "card_elevation": "elevation.1",
        "hero_elevation": "elevation.0",
    }


def _proposal_context(proposal_bundle: dict[str, Any] | None) -> dict[str, Any]:
    visual_language = _proposal_part(proposal_bundle, "visual_language")
    contract_profile = _proposal_contract_profile(proposal_bundle)
    return {
        "direction_id": _proposal_direction_id(proposal_bundle),
        "direction_name": _proposal_direction_name(proposal_bundle),
        "surface_treatment": visual_language.get("surface_treatment"),
        "motion_posture": visual_language.get("motion_posture"),
        "density_profile": contract_profile["density_profile"],
        "spacing_rhythm": contract_profile["spacing_rhythm"],
        "shape_profile": contract_profile["shape_profile"],
        "motion_profile": contract_profile["motion_profile"],
    }


def default_brief(
    project_name: str,
    project_slug: str,
    platforms: list[str],
    inspiration_summary: dict[str, Any] | None,
    product_summary: str | None,
    proposal_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    visual_language = _proposal_part(proposal_bundle, "visual_language")
    typography_voice = _proposal_part(proposal_bundle, "typography_voice")
    source_rationale = _proposal_part(proposal_bundle, "source_rationale")
    proposal_context = _proposal_context(proposal_bundle)
    design_principles = source_rationale.get("direction_principles") or [
        "mobile-first hierarchy",
        "one-thumb primary actions",
        "semantic reuse before platform styling",
    ]
    tone = typography_voice.get("body_tone") or "to be defined"
    visual_keywords = list(dict.fromkeys(visual_language.get("atmosphere", []) + visual_language.get("composition_principles", [])))[:5]
    return {
        "contract_version": "1.0.0",
        "project": {
            "id": project_slug,
            "name": project_name,
            "product_type": "mobile_app",
            "summary": product_summary or "Draft mobile product summary.",
        },
        "platform_targets": platforms,
        "design_principles": design_principles,
        "brand": {
            "tone": tone,
            "visual_keywords": visual_keywords,
            "font_direction": typography_voice.get("font_family", "Preserve reusable cross-platform typography roles."),
        },
        "localization": {
            "base_locale": "en-US",
            "supported_locales": ["en-US"],
        },
        "accessibility": {
            "min_touch_target": 44,
            "dynamic_type_support": "required",
            "contrast_target": "WCAG_AA",
        },
        "content_strategy": {
            "placeholder_policy": "realistic",
            "copy_tone": tone,
        },
        "technical_constraints": {
            "orientation": "portrait",
            "supports_tablet": False,
            "density_profile": proposal_context["density_profile"],
            "primary_action_posture": _proposal_contract_profile(proposal_bundle)["button_variant"],
            "implementation_note": "Canonical contract first, platform code second.",
        },
        "deliverables": {
            "include_dark_theme": True,
            "include_design_tokens": True,
            "include_platform_mappings": True,
        },
        "inspiration_context": {
            "source_count": inspiration_summary.get("source_count", 0) if inspiration_summary else 0,
            "asset_count": inspiration_summary.get("asset_count", 0) if inspiration_summary else 0,
            "most_common_colors": inspiration_summary.get("most_common_colors", []) if inspiration_summary else [],
        },
        "proposal_context": {**proposal_context, "proposal_phase": "proposal"},
    }


def default_tokens(proposal_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    color_signal = _proposal_part(proposal_bundle, "visual_language").get("color_signal", {})
    contract_profile = _proposal_contract_profile(proposal_bundle)
    return {
        "contract_version": "1.0.0",
        "proposal_context": _proposal_context(proposal_bundle),
        "color": {
            "accent.500": {"value": color_signal.get("accent", "#2F6BFF")},
            "neutral.900": {"value": color_signal.get("ink", "#111827")},
            "neutral.700": {"value": color_signal.get("muted_ink", "#374151")},
            "neutral.100": {"value": color_signal.get("soft", "#F3F4F6")},
            "neutral.0": {"value": color_signal.get("canvas", "#FFFFFF")},
            "white": {"value": "#FFFFFF"},
            "black": {"value": "#000000"},
        },
        "spacing": _raw_value_tokens(contract_profile["spacing_values"]),
        "radius": {name: {"value": value} for name, value in contract_profile["radius_values"].items()},
        "size": {
            "icon.sm": {"value": 16},
            "icon.md": {"value": 24},
            "touch.min": {"value": contract_profile["touch_min"]},
        },
        "elevation": {name: {"value": value} for name, value in contract_profile["elevation_values"].items()},
        "opacity": {
            "disabled": {"value": contract_profile["disabled_opacity"]},
        },
        "motion": {
            "duration.fast": {"value": contract_profile["motion_values"]["duration.fast"]},
            "duration.normal": {"value": contract_profile["motion_values"]["duration.normal"]},
            "duration.slow": {"value": contract_profile["motion_values"]["duration.slow"]},
            "curve.standard": {"value": contract_profile["motion_values"]["curve.standard"]},
            "scale.pressed": {"value": contract_profile["motion_values"]["scale.pressed"]},
        },
        "border": {
            "thin": {"value": 1},
        },
        "z_index": {
            "base": {"value": 0},
            "modal": {"value": 1000},
        },
    }


def default_typography(proposal_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    typography_voice = _proposal_part(proposal_bundle, "typography_voice")
    proposal_context = _proposal_context(proposal_bundle)
    contract_profile = _proposal_contract_profile(proposal_bundle)
    scale_adjustments = typography_voice.get("scale_adjustments", {})
    tracking = typography_voice.get("tracking", {})
    return {
        "contract_version": "1.0.0",
        "proposal_context": {**proposal_context, "voice_name": typography_voice.get("voice_name")},
        "font_families": {
            "brand_sans": {
                "primary": typography_voice.get("font_family", "SF Pro"),
                "fallbacks": typography_voice.get("fallbacks", ["Inter", "System Sans"]),
            }
        },
        "font_weights": {
            "regular": 400,
            "medium": 500,
            "semibold": 600,
            "bold": 700,
        },
        "type_scales": {
            "sm": {
                "font_size": scale_adjustments.get("sm", {}).get("font_size", 14),
                "line_height": scale_adjustments.get("sm", {}).get("line_height", 20),
                "letter_spacing": tracking.get("sm", 0.0),
            },
            "md": {
                "font_size": scale_adjustments.get("md", {}).get("font_size", 16),
                "line_height": scale_adjustments.get("md", {}).get("line_height", 24),
                "letter_spacing": tracking.get("md", 0.0),
            },
            "lg": {
                "font_size": scale_adjustments.get("lg", {}).get("font_size", 20),
                "line_height": scale_adjustments.get("lg", {}).get("line_height", 28),
                "letter_spacing": tracking.get("lg", -0.2),
            },
            "xl": {
                "font_size": scale_adjustments.get("xl", {}).get("font_size", 28),
                "line_height": scale_adjustments.get("xl", {}).get("line_height", 36),
                "letter_spacing": tracking.get("xl", -0.4),
            },
        },
        "text_styles": {
            "display": {
                "family": "brand_sans",
                "weight": typography_voice.get("headline_weight", "bold"),
                "scale": "xl",
                "allow_font_scaling": True,
            },
            "title": {
                "family": "brand_sans",
                "weight": typography_voice.get("title_weight", "semibold"),
                "scale": "lg",
                "allow_font_scaling": True,
            },
            "body": {
                "family": "brand_sans",
                "weight": typography_voice.get("body_weight", "regular"),
                "scale": "md",
                "allow_font_scaling": True,
            },
            "caption": {"family": "brand_sans", "weight": "regular", "scale": "sm", "allow_font_scaling": True},
        },
        "defaults": {
            "paragraph_spacing": contract_profile["paragraph_spacing"],
            "allow_font_scaling": True,
            "truncate_strategy": "tail",
        },
    }


def default_semantics(proposal_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    color_signal = _proposal_part(proposal_bundle, "visual_language").get("color_signal", {})
    contract_profile = _proposal_contract_profile(proposal_bundle)
    proposal_context = _proposal_context(proposal_bundle)
    motifs = _proposal_motifs(proposal_bundle)
    primary_card_motif = motifs[0]["name"] if motifs else "primary modular grouping"
    hero_motif = next(
        (
            motif.get("name")
            for motif in motifs
            if "hero" in f"{motif.get('id', '')} {motif.get('name', '')}".lower()
        ),
        primary_card_motif,
    )
    return {
        "contract_version": "1.0.0",
        "proposal_context": {
            **proposal_context,
            "button_variant": contract_profile["button_variant"],
            "card_style": contract_profile["card_style"],
        },
        "themes": {
            "light": {
                "color_roles": {
                    "text.primary": "color.neutral.900",
                    "text.secondary": "color.neutral.700",
                    "text.onAction": "color.white",
                    "action.primary": "color.accent.500",
                    "surface.canvas": "color.neutral.0",
                    "surface.card": contract_profile["light_surface_card"],
                }
            },
            "dark": {
                "color_roles": {
                    "text.primary": color_signal.get("dark_text", "#FFFFFF"),
                    "text.secondary": color_signal.get("dark_muted_text", "#D1D5DB"),
                    "text.onAction": color_signal.get("dark_on_accent", "#111827"),
                    "action.primary": color_signal.get("accent_dark", "#7EA2FF"),
                    "surface.canvas": color_signal.get("dark_canvas", "#0F1115"),
                    "surface.card": color_signal.get("dark_surface", "#171A21"),
                }
            },
        },
        "text_roles": {
            "app.display": {"style": "display"},
            "app.title": {"style": "title"},
            "app.body": {"style": "body"},
            "app.caption": {"style": "caption"},
        },
        "spacing_roles": contract_profile["spacing_roles"],
        "shape_roles": contract_profile["shape_roles"],
        "state_roles": {
            "disabled.opacity": "opacity.disabled",
            "pressed.scale": "motion.scale.pressed",
            "press.duration": "motion.duration.fast",
            "enter.duration": "motion.duration.normal",
        },
        "component_roles": {
            "button.primary": {
                "kind": "button",
                "text_role": "app.body",
                "foreground": "text.onAction",
                "background": "action.primary",
                "corner": "button.corner",
                "min_height": "size.touch.min",
                "elevation": contract_profile["button_elevation"],
                "variant": contract_profile["button_variant"],
                "padding_role": "component.padding.button.horizontal",
                "density": contract_profile["density_profile"],
            },
            "button.secondary": {
                "kind": "button",
                "text_role": "app.body",
                "foreground": "text.primary",
                "background": "surface.card",
                "corner": "button.corner",
                "min_height": "size.touch.min",
                "elevation": contract_profile["secondary_button_elevation"],
                "variant": contract_profile["secondary_button_variant"],
                "padding_role": "component.padding.button.horizontal",
                "density": contract_profile["density_profile"],
            },
            "card.default": {
                "kind": "card",
                "background": "surface.card",
                "corner": "card.corner",
                "elevation": contract_profile["card_elevation"],
                "motif": primary_card_motif,
                "padding_role": "component.padding.card",
                "surface_style": contract_profile["card_style"],
                "density": contract_profile["density_profile"],
            },
            "card.hero": {
                "kind": "card",
                "background": "surface.card",
                "corner": "hero.corner",
                "elevation": contract_profile["hero_elevation"],
                "motif": hero_motif,
                "padding_role": "component.padding.card",
                "surface_style": contract_profile["card_style"],
                "density": contract_profile["density_profile"],
            },
        },
    }


def default_screens() -> dict[str, Any]:
    return {
        "contract_version": "1.0.0",
        "allowed_component_kinds": list(CANONICAL_COMPONENT_KINDS),
        "screen_rules": [
            "Use semantic roles instead of raw visual values.",
            "Favor one-thumb primary actions.",
            "Prefer progressive disclosure over dense dashboards.",
        ],
        "screens": [],
    }


def default_platform_mapping(platform: str) -> dict[str, Any]:
    base = {
        "platform": platform,
        "contract_version": "1.0.0",
        "guidance_scope": "used",
        "design_intent": {
            "summary": "",
            "principles": [],
        },
        "typography_guidance": {
            "app.display": "",
            "app.title": "",
            "app.body": "",
            "app.caption": "",
        },
        "visual_guidance": {
            "action.primary": "",
            "surface.canvas": "",
            "surface.card": "",
            "text.onAction": "",
            "text.primary": "",
            "text.secondary": "",
        },
        "component_guidance": {
            "button.primary": "",
            "card.default": "",
        },
        "layout_guidance": {
            "stack.vertical": "",
            "stack.horizontal": "",
            "scroll.vertical": "",
        },
        "interaction_guidance": {
            "disabled.opacity": "",
            "pressed.scale": "",
        },
        "asset_guidance": {
            "source_of_truth": "",
            "production_asset_note": "",
        },
        "implementation_notes": [],
        "gaps": [],
    }

    if platform == "flutter":
        base["design_intent"] = {
            "summary": "Implement the validated mobile contract on Flutter without reinterpreting hierarchy, spacing rhythm, or accessibility rules.",
            "principles": [
                "Centralize typography and colors in a shared theme layer.",
                "Preserve one dominant CTA per screen unless the contract expands it.",
            ],
        }
        base["typography_guidance"].update(
            {
                "app.display": "Use the hero headline style for onboarding or first-run emphasis. Preserve the contract font family, weight, and line-height in the Flutter theme.",
                "app.title": "Use the primary section or page title style. Keep dynamic type enabled and avoid local overrides.",
                "app.body": "Use the default long-form or explanatory text style. Preserve readable line-height and contrast.",
                "app.caption": "Use for support text only. Keep it secondary in emphasis, not in accessibility quality.",
            }
        )
        base["visual_guidance"].update(
            {
                "action.primary": "Use the primary accent color for the main CTA pattern. Keep contrast against text.onAction at AA or better.",
                "surface.canvas": "Treat this as the screen background surface. Avoid adding extra noise or gradients unless the contract explicitly asks for it.",
                "surface.card": "Use for elevated content clusters or modules that need separation from the canvas.",
                "text.onAction": "Reserve for text placed on the primary action surface. It must remain legible in all states.",
                "text.primary": "Use for default readable copy and titles on normal surfaces.",
                "text.secondary": "Use for supporting text, metadata, and lower-emphasis annotations.",
            }
        )
        base["component_guidance"].update(
            {
                "button.primary": "Implement as the single dominant CTA pattern. Keep tap target at least 44 logical pixels tall and avoid visual competition nearby.",
                "card.default": "Use as the default grouped content container. Keep padding and corner treatment aligned with the canonical tokens.",
            }
        )
        base["layout_guidance"].update(
            {
                "stack.vertical": "Default to a vertical content flow on mobile. Avoid dashboard density in the initial implementation.",
                "stack.horizontal": "Use sparingly for short paired items or segmented actions, not for major information flow.",
                "scroll.vertical": "Assume portrait-first vertical scrolling. Keep the primary action reachable without overlong initial layouts.",
            }
        )
        base["interaction_guidance"].update(
            {
                "disabled.opacity": "Disabled actions should remain legible and clearly unavailable, not simply faded into invisibility.",
                "pressed.scale": "Pressed feedback should be subtle and fast. Avoid exaggerated motion that fights the calm tone.",
            }
        )
        base["asset_guidance"] = {
            "source_of_truth": "Use the canonical contract plus inspiration notes as the design source of truth. Scraped images are references, not production UI assets.",
            "production_asset_note": "Any illustrations, icons, or marketing artwork should be specified as production assets separately before implementation.",
        }
        base["implementation_notes"] = [
            "Prefer shared theme primitives over per-screen styling decisions.",
            "Use the screen specs to drive layout, not the inspiration screenshots directly.",
        ]
    elif platform == "swiftui":
        base["design_intent"] = {
            "summary": "Implement the validated mobile contract in SwiftUI while keeping typography, hierarchy, and interaction tone aligned with the canonical design.",
            "principles": [
                "Push reusable visual rules into shared styles or modifiers.",
                "Keep semantic roles clearer than view-level styling tricks.",
            ],
        }
        base["typography_guidance"].update(
            {
                "app.display": "Reserve for hero moments such as onboarding and first-run steps. Keep scaling behavior accessible.",
                "app.title": "Use for page-level hierarchy and section headlines. Avoid introducing alternate title styles without contract changes.",
                "app.body": "Use for primary explanatory copy and content text.",
                "app.caption": "Use only for secondary metadata or support text.",
            }
        )
        base["visual_guidance"].update(
            {
                "action.primary": "Use as the dominant interactive accent for the main CTA and action-led components.",
                "surface.canvas": "Use as the baseline background surface for each screen.",
                "surface.card": "Use for grouped modules needing elevation or separation without crowding the canvas.",
                "text.onAction": "Use for text sitting on top of the primary action color and validate contrast in all states.",
                "text.primary": "Use for readable default content and headings on neutral surfaces.",
                "text.secondary": "Use for lower-emphasis supporting information without compromising legibility.",
            }
        )
        base["component_guidance"].update(
            {
                "button.primary": "Keep as the singular primary action treatment on a screen. Maintain clear spacing around it.",
                "card.default": "Use for modular grouped content. Keep shape, surface, and padding aligned with the contract rather than native defaults alone.",
            }
        )
        base["layout_guidance"].update(
            {
                "stack.vertical": "Favor clear vertical rhythm and progressive disclosure across the screen flow.",
                "stack.horizontal": "Use only where compact side-by-side grouping improves comprehension.",
                "scroll.vertical": "Assume a vertical mobile flow and keep early content focused.",
            }
        )
        base["interaction_guidance"].update(
            {
                "disabled.opacity": "Disabled states should communicate unavailable actions without losing readability.",
                "pressed.scale": "Pressed feedback should stay subtle and fast. Keep it supportive, not theatrical.",
            }
        )
        base["asset_guidance"] = {
            "source_of_truth": "The canonical contract defines the production design. Inspiration assets are references only.",
            "production_asset_note": "Any custom icons, illustrations, or imagery should be tracked as explicit production assets before implementation.",
        }
        base["implementation_notes"] = [
            "Prefer shared modifiers and style wrappers over screen-local styling drift.",
            "Keep accessibility and dynamic type equal in priority to visual fidelity.",
        ]
    else:
        base["design_intent"] = {
            "summary": "Implement the validated contract in Compose with a shared theme and reusable composable patterns, not per-screen reinvention.",
            "principles": [
                "Keep semantic hierarchy visible in the theme and composable structure.",
                "Use the contract as the source of truth for layout emphasis and interaction tone.",
            ],
        }
        base["typography_guidance"].update(
            {
                "app.display": "Reserve for hero or onboarding emphasis. Keep it rare so it retains hierarchy value.",
                "app.title": "Use for top-level screen and section titles.",
                "app.body": "Use for default content text and explanatory copy.",
                "app.caption": "Use for metadata and secondary annotations only.",
            }
        )
        base["visual_guidance"].update(
            {
                "action.primary": "Use as the dominant CTA color and keep it visually reserved for the most important action.",
                "surface.canvas": "Use as the main screen background surface.",
                "surface.card": "Use for grouped or elevated content modules.",
                "text.onAction": "Use for text placed on action-colored surfaces with strong contrast.",
                "text.primary": "Use for default readable content and titles.",
                "text.secondary": "Use for supporting text and metadata.",
            }
        )
        base["component_guidance"].update(
            {
                "button.primary": "Treat as the singular main CTA treatment. Keep spacing and prominence consistent.",
                "card.default": "Use as the standard grouped surface for content clusters or modules.",
            }
        )
        base["layout_guidance"].update(
            {
                "stack.vertical": "Favor vertical mobile flow and limit density in the first implementation pass.",
                "stack.horizontal": "Use where short paired content benefits from side-by-side grouping.",
                "scroll.vertical": "Assume portrait-first vertical scrolling.",
            }
        )
        base["interaction_guidance"].update(
            {
                "disabled.opacity": "Disabled actions should remain understandable and not disappear into the background.",
                "pressed.scale": "Pressed feedback should be present but understated.",
            }
        )
        base["asset_guidance"] = {
            "source_of_truth": "The canonical contract is the source of truth. Inspiration assets remain reference material only.",
            "production_asset_note": "Introduce production artwork through explicit design assets, not scraped screenshots.",
        }
        base["implementation_notes"] = [
            "Prefer theme-backed values and reusable composables over screen-local visual overrides.",
            "Keep motion and emphasis aligned with the calm, mobile-first design intent.",
        ]

    return base


def default_plan(project_name: str, platforms: list[str]) -> dict[str, Any]:
    return {
        "project": project_name,
        "status": "draft",
        "principle": "Canonical contract before platform code.",
        "phases": [
            {
                "id": "intake",
                "name": "Inspiration intake",
                "status": "ready",
                "deliverables": ["inspirations/index.json"],
            },
            {
                "id": "ideas",
                "name": "Idea capture",
                "status": "ready",
                "deliverables": ["ideas/index.json"],
            },
            {
                "id": "proposal",
                "name": "Opinionated design proposal",
                "status": "ready",
                "deliverables": [
                    "proposal/design_direction.md",
                    "proposal/design_signals.json",
                    "proposal/direction_options.json",
                    "proposal/visual_language.json",
                    "proposal/typography_voice.json",
                    "proposal/component_motifs.json",
                    "proposal/flow_narrative.md",
                    "proposal/anti_patterns.md",
                    "proposal/source_rationale.json",
                ],
            },
            {
                "id": "contract",
                "name": "Canonical contract",
                "status": "ready",
                "deliverables": [
                    "contract/brief.json",
                    "contract/tokens.json",
                    "contract/typography.json",
                    "contract/semantics.json",
                ],
            },
            {
                "id": "screens",
                "name": "Screen synthesis",
                "status": "ready",
                "deliverables": ["screens/index.json"],
            },
            {
                "id": "platforms",
                "name": "Platform guidance",
                "status": "ready",
                "deliverables": [f"platforms/{platform}.json" for platform in platforms],
            },
            {
                "id": "validation",
                "name": "Validation and review",
                "status": "ready",
                "deliverables": ["validation/report.json"],
            },
            {
                "id": "implementation",
                "name": "Implementation handoff",
                "status": "blocked",
                "depends_on": ["validation"],
            },
        ],
    }


def preview_summary(project_name: str, output_dir: Path, platforms: list[str], inspiration_summary: dict[str, Any] | None) -> str:
    source_count = inspiration_summary.get("source_count", 0) if inspiration_summary else 0
    asset_count = inspiration_summary.get("asset_count", 0) if inspiration_summary else 0
    return f"""# {project_name}

This workspace is the source of truth for mobile design synthesis.

- Platforms: {", ".join(platforms)}
- Inspiration sources: {source_count}
- Inspiration assets: {asset_count}

## Next steps

1. Review `inspirations/index.json`.
2. Add idea cards with `scripts/add_idea.py`.
3. Review the extracted evidence in `proposal/design_signals.json`.
4. Review ranked candidates in `proposal/direction_options.json`.
5. Generate and refine the opinionated proposal under `proposal/`.
6. Build the canonical files under `contract/` from that proposal.
7. Tighten `screens/` and `platforms/`.
8. Run `scripts/validate_design_contract.py --output-dir {output_dir}` before implementation work.
"""


ORCHESTRATOR_CONFIG = load_orchestrator_config()
SCREEN_EFFECT_PROFILES: dict[str, dict[str, dict[str, Any]]] = ORCHESTRATOR_CONFIG["screen_effect_profiles"]
CTA_POSTURE_BY_BUTTON_VARIANT = {
    key: set(values)
    for key, values in ORCHESTRATOR_CONFIG["validation_policies"]["cta_posture_by_button_variant"].items()
}
CHROME_DENSITY_BY_CONTRACT_DENSITY = {
    key: set(values)
    for key, values in ORCHESTRATOR_CONFIG["validation_policies"]["chrome_density_by_contract_density"].items()
}

def screen_effect_profile(direction_id: str, screen_id: str) -> dict[str, Any]:
    direction_profile = SCREEN_EFFECT_PROFILES.get(direction_id, SCREEN_EFFECT_PROFILES["calm_editorial"])
    merged = dict(direction_profile.get("default", {}))
    merged.update(direction_profile.get(screen_id, {}))
    return merged


def _component_text(component: dict[str, Any]) -> str:
    fragments: list[str] = []
    for key in ("content", "label"):
        value = component.get(key)
        if isinstance(value, str):
            fragments.append(value)
    if isinstance(component.get("items"), list):
        fragments.extend(str(item) for item in component["items"])
    return " ".join(fragments).lower()


def _motif_tokens(motif_id: str) -> list[str]:
    return [token for token in motif_id.replace("-", "_").split("_") if len(token) > 2]


def flatten_token_refs(tokens: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for category, values in tokens.items():
        if category == "contract_version" or not isinstance(values, dict):
            continue
        for name in values:
            refs.add(f"{category}.{name}")
    return refs


def flatten_theme_color_roles(semantics: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for theme in semantics.get("themes", {}).values():
        refs.update(theme.get("color_roles", {}).keys())
    return refs


def is_hex_color(value: str) -> bool:
    return bool(re.fullmatch(r"#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})", value))


def validate_output_dir(output_dir: Path, required_platforms: list[str] | None = None) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checks: dict[str, str] = {}

    loaded: dict[str, dict[str, Any]] = {}
    for relative_path, required_keys in REQUIRED_FILES.items():
        file_path = output_dir / relative_path
        if not file_path.exists():
            errors.append({"code": "missing_file", "message": f"Missing required file: {relative_path}"})
            checks[relative_path] = "failed"
            continue
        data = read_json(file_path)
        loaded[relative_path] = data
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            errors.append(
                {
                    "code": "missing_keys",
                    "message": f"{relative_path} is missing keys: {', '.join(missing_keys)}",
                }
            )
            checks[relative_path] = "failed"
        else:
            checks[relative_path] = "passed"

    for relative_path in PROPOSAL_MARKDOWN_FILES:
        file_path = output_dir / relative_path
        if not file_path.exists():
            errors.append({"code": "missing_file", "message": f"Missing required file: {relative_path}"})
            checks[relative_path] = "failed"
            continue
        if len(file_path.read_text().strip()) < 40:
            errors.append({"code": "proposal_incomplete", "message": f"{relative_path} is too short to capture a usable proposal direction"})
            checks[relative_path] = "failed"
        else:
            checks[relative_path] = "passed"

    if errors:
        return {"status": "failed", "errors": errors, "warnings": warnings, "checks": checks}

    proposal_signals = loaded["proposal/design_signals.json"]
    proposal_options = loaded["proposal/direction_options.json"]
    proposal_candidates = loaded["proposal/proposal_candidates.json"]
    proposal_visual = loaded["proposal/visual_language.json"]
    proposal_typography = loaded["proposal/typography_voice.json"]
    proposal_motifs = loaded["proposal/component_motifs.json"]
    proposal_rationale = loaded["proposal/source_rationale.json"]
    review_packet = (output_dir / "proposal" / "review_packet.md").read_text().strip()
    brief = loaded["contract/brief.json"]
    tokens = loaded["contract/tokens.json"]
    typography = loaded["contract/typography.json"]
    semantics = loaded["contract/semantics.json"]
    screens = loaded["screens/index.json"]
    inspirations = load_optional_json(output_dir / "inspirations" / "index.json")
    ideas = load_optional_json(output_dir / "ideas" / "index.json")

    requested_platforms = required_platforms or brief.get("platform_targets", [])
    invalid_platforms = [platform for platform in brief.get("platform_targets", []) if platform not in DEFAULT_PLATFORMS]
    if invalid_platforms:
        errors.append({"code": "invalid_platform", "message": f"Unsupported platforms in brief: {', '.join(invalid_platforms)}"})

    proposal_direction_id = proposal_visual.get("direction_id")
    signal_scores = proposal_signals.get("archetype_scores", [])
    signal_clusters = proposal_signals.get("signal_clusters", {})
    cluster_entries = signal_clusters.get("clusters", [])
    if not signal_scores:
        errors.append({"code": "proposal_incomplete", "message": "proposal/design_signals.json must include scored direction evidence"})
    elif signal_scores[0].get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_mismatch", "message": "proposal/design_signals.json does not align with the selected visual direction"})
    if not cluster_entries:
        errors.append({"code": "proposal_incomplete", "message": "proposal/design_signals.json must include clustered signal evidence"})
    else:
        cluster_ranks = [entry.get("rank") for entry in cluster_entries]
        if sorted(cluster_ranks) != list(range(1, len(cluster_entries) + 1)):
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json signal_clusters ranks must be contiguous and start at 1"})
        expected_cluster_order = sorted(cluster_entries, key=lambda entry: (-entry.get("score", 0), entry.get("cluster_id", "")))
        actual_cluster_ids = [entry.get("cluster_id") for entry in sorted(cluster_entries, key=lambda entry: entry.get("rank", 10**6))]
        expected_cluster_ids = [entry.get("cluster_id") for entry in expected_cluster_order]
        if actual_cluster_ids != expected_cluster_ids:
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json signal_clusters does not preserve deterministic ordering"})
        active_cluster_ids = [entry.get("cluster_id") for entry in expected_cluster_order if entry.get("score", 0) > 0]
        if signal_clusters.get("active_cluster_ids", []) != active_cluster_ids:
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json active_cluster_ids does not match the clustered evidence"})
        if signal_clusters.get("active_cluster_count") != len(active_cluster_ids):
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json active_cluster_count does not match active_cluster_ids"})
        expected_dominant_cluster_id = active_cluster_ids[0] if active_cluster_ids else (expected_cluster_ids[0] if expected_cluster_ids else None)
        if signal_clusters.get("dominant_cluster_id") != expected_dominant_cluster_id:
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json dominant_cluster_id does not match the ranked clusters"})
        if signal_clusters.get("cluster_count") != len(cluster_entries):
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json cluster_count does not match the number of clusters"})
        for entry in cluster_entries:
            for required_key in (
                "cluster_id",
                "label",
                "score",
                "rank",
                "matched_keywords",
                "matched_categories",
                "matched_screens",
                "matched_sources",
                "direction_influence",
            ):
                if required_key not in entry:
                    errors.append({"code": "proposal_incomplete", "message": f"proposal/design_signals.json cluster {entry.get('cluster_id')!r} is missing {required_key}"})
            if entry.get("score", 0) > 0 and not entry.get("direction_influence"):
                errors.append({"code": "proposal_signal_mismatch", "message": f"proposal/design_signals.json cluster {entry.get('cluster_id')!r} is active but has no direction influence"})
        top_scorecard = signal_scores[0] if signal_scores else {}
        if active_cluster_ids and top_scorecard.get("cluster_score", 0) <= 0:
            errors.append({"code": "proposal_signal_mismatch", "message": "proposal/design_signals.json top scored direction is not backed by clustered signals"})
        cluster_entry_ids = {entry.get("cluster_id") for entry in cluster_entries}
        for scorecard in signal_scores:
            if "cluster_score" not in scorecard or "raw_keyword_score" not in scorecard:
                errors.append({"code": "proposal_incomplete", "message": f"proposal/design_signals.json scorecard for {scorecard.get('direction_id')!r} is missing cluster-aware scoring fields"})
            for cluster_match in scorecard.get("cluster_matches", []):
                if cluster_match.get("cluster_id") not in cluster_entry_ids:
                    errors.append({"code": "proposal_signal_mismatch", "message": f"proposal/design_signals.json scorecard for {scorecard.get('direction_id')!r} references unknown cluster {cluster_match.get('cluster_id')!r}"})
    if proposal_options.get("project") != brief.get("project", {}).get("name"):
        errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json project does not match contract/brief.json"})
    option_entries = proposal_options.get("options", [])
    if not option_entries:
        errors.append({"code": "proposal_incomplete", "message": "proposal/direction_options.json must include scored options"})
    else:
        selected_entries = [entry for entry in option_entries if entry.get("selected")]
        if len(selected_entries) != 1:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json must mark exactly one selected option"})
        ranks = [entry.get("rank") for entry in option_entries]
        if sorted(ranks) != list(range(1, len(option_entries) + 1)):
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json ranks must be contiguous and start at 1"})
        expected_order = sorted(option_entries, key=lambda entry: (-entry.get("score", 0), entry.get("direction_id", "")))
        expected_ids = [entry.get("direction_id") for entry in expected_order]
        actual_ids = [entry.get("direction_id") for entry in sorted(option_entries, key=lambda entry: entry.get("rank", 10**6))]
        if actual_ids != expected_ids:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json does not preserve deterministic score ordering"})
        selected_direction_id = proposal_options.get("selected_direction_id")
        if selected_direction_id != proposal_direction_id:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json selected_direction_id does not match the selected visual direction"})
        if selected_entries and selected_entries[0].get("direction_id") != selected_direction_id:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json selected option does not match selected_direction_id"})
        if option_entries[0].get("direction_id") != selected_direction_id:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json top-ranked option must be the selected direction"})
    if proposal_candidates.get("project") != brief.get("project", {}).get("name"):
        errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json project does not match contract/brief.json"})
    candidate_entries = proposal_candidates.get("candidates", [])
    if not candidate_entries:
        errors.append({"code": "proposal_incomplete", "message": "proposal/proposal_candidates.json must include proposal candidates"})
    else:
        if proposal_candidates.get("candidate_count") != len(candidate_entries):
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json candidate_count does not match the number of candidates"})
        if len(candidate_entries) < 2 or len(candidate_entries) > 3:
            errors.append({"code": "proposal_incomplete", "message": "proposal/proposal_candidates.json must keep 2-3 review candidates"})
        selected_candidate_entries = [entry for entry in candidate_entries if entry.get("selected")]
        if len(selected_candidate_entries) != 1:
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json must mark exactly one selected candidate"})
        candidate_ranks = [entry.get("rank") for entry in candidate_entries]
        if sorted(candidate_ranks) != list(range(1, len(candidate_entries) + 1)):
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json ranks must be contiguous and start at 1"})
        expected_candidate_ids = [
            entry.get("direction_id")
            for entry in sorted(option_entries, key=lambda entry: entry.get("rank", 10**6))[: len(candidate_entries)]
        ]
        actual_candidate_ids = [
            entry.get("direction_id")
            for entry in sorted(candidate_entries, key=lambda entry: entry.get("rank", 10**6))
        ]
        if actual_candidate_ids != expected_candidate_ids:
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json does not align with the top ranked direction options"})
        selected_candidate_id = proposal_candidates.get("selected_direction_id")
        if selected_candidate_id != proposal_direction_id or selected_candidate_id != proposal_options.get("selected_direction_id"):
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json selected_direction_id does not match the selected proposal direction"})
        if selected_candidate_entries and selected_candidate_entries[0].get("direction_id") != selected_candidate_id:
            errors.append({"code": "proposal_mismatch", "message": "proposal/proposal_candidates.json selected candidate does not match selected_direction_id"})
        for candidate in candidate_entries:
            for required_key in (
                "direction_id",
                "direction_name",
                "rank",
                "selected",
                "score",
                "visual_thesis",
                "why_this_app",
                "key_strengths",
                "tradeoffs",
                "selection_rationale",
                "rejection_rationale",
                "proposal_implications",
                "evidence",
            ):
                if required_key not in candidate:
                    errors.append({"code": "proposal_incomplete", "message": f"proposal/proposal_candidates.json candidate {candidate.get('direction_id')!r} is missing {required_key}"})
            if len(candidate.get("key_strengths", [])) < 2:
                errors.append({"code": "proposal_incomplete", "message": f"proposal/proposal_candidates.json candidate {candidate.get('direction_id')!r} needs at least two key strengths"})
            for implication_group in ("tokens", "semantics", "screens"):
                if not candidate.get("proposal_implications", {}).get(implication_group):
                    errors.append({"code": "proposal_incomplete", "message": f"proposal/proposal_candidates.json candidate {candidate.get('direction_id')!r} is missing proposal implications for {implication_group}"})
            if candidate.get("selected") and not candidate.get("selection_rationale"):
                errors.append({"code": "proposal_incomplete", "message": f"proposal/proposal_candidates.json selected candidate {candidate.get('direction_id')!r} needs selection_rationale"})
            if not candidate.get("selected") and not candidate.get("rejection_rationale"):
                errors.append({"code": "proposal_incomplete", "message": f"proposal/proposal_candidates.json rejected candidate {candidate.get('direction_id')!r} needs rejection_rationale"})
    if len(proposal_candidates.get("non_negotiables", [])) < 2:
        errors.append({"code": "proposal_incomplete", "message": "proposal/proposal_candidates.json must include non_negotiables"})
    if len(proposal_candidates.get("open_questions", [])) < 2:
        errors.append({"code": "proposal_incomplete", "message": "proposal/proposal_candidates.json must include open_questions"})
    if "## Selected Direction" not in review_packet or "## Candidate Review" not in review_packet:
        errors.append({"code": "proposal_incomplete", "message": "proposal/review_packet.md must include selected and candidate review sections"})
    if proposal_visual.get("direction_name") not in review_packet:
        errors.append({"code": "proposal_mismatch", "message": "proposal/review_packet.md does not mention the selected direction"})
    for candidate in candidate_entries:
        if candidate.get("direction_name") and candidate["direction_name"] not in review_packet:
            errors.append({"code": "proposal_mismatch", "message": f"proposal/review_packet.md does not include candidate {candidate['direction_name']}"})
    if proposal_signals.get("project") != brief.get("project", {}).get("name"):
        errors.append({"code": "proposal_mismatch", "message": "proposal/design_signals.json project does not match contract/brief.json"})
    if not proposal_signals.get("screen_pressure", {}).get("recommended_screens"):
        errors.append({"code": "proposal_incomplete", "message": "proposal/design_signals.json must recommend at least one screen"})
    if not proposal_signals.get("motif_candidates", {}).get("candidates"):
        errors.append({"code": "proposal_incomplete", "message": "proposal/design_signals.json must include motif candidates"})
    if not proposal_direction_id:
        errors.append({"code": "proposal_incomplete", "message": "proposal/visual_language.json is missing direction_id"})
    if proposal_typography.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_mismatch", "message": "proposal typography voice does not match the visual direction"})
    if proposal_motifs.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_mismatch", "message": "proposal component motifs do not match the visual direction"})
    if proposal_rationale.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_mismatch", "message": "proposal source rationale does not match the visual direction"})
    if len(proposal_visual.get("composition_principles", [])) < 2:
        errors.append({"code": "proposal_incomplete", "message": "proposal visual language needs at least two composition principles"})
    if len(proposal_typography.get("usage_principles", [])) < 2:
        errors.append({"code": "proposal_incomplete", "message": "proposal typography voice needs at least two usage principles"})
    if not proposal_motifs.get("motifs"):
        errors.append({"code": "proposal_incomplete", "message": "proposal component motifs must define at least one reusable motif"})

    brief_proposal = brief.get("proposal_context", {})
    tokens_proposal = tokens.get("proposal_context", {})
    typography_proposal = typography.get("proposal_context", {})
    semantics_proposal = semantics.get("proposal_context", {})
    if brief_proposal.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_dependency_missing", "message": "contract/brief.json is not aligned to the current proposal direction"})
    if tokens_proposal.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_dependency_missing", "message": "contract/tokens.json is not aligned to the current proposal direction"})
    if typography_proposal.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_dependency_missing", "message": "contract/typography.json is not aligned to the current proposal direction"})
    if semantics_proposal.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_dependency_missing", "message": "contract/semantics.json is not aligned to the current proposal direction"})
    screens_proposal = screens.get("proposal_context", {})
    if screens_proposal.get("direction_id") != proposal_direction_id:
        errors.append({"code": "proposal_dependency_missing", "message": "screens/index.json is not aligned to the current proposal direction"})
    for key in ("surface_treatment", "motion_posture"):
        expected = proposal_visual.get(key)
        for relative_path, context in (
            ("contract/brief.json", brief_proposal),
            ("contract/tokens.json", tokens_proposal),
            ("contract/typography.json", typography_proposal),
            ("contract/semantics.json", semantics_proposal),
        ):
            if context.get(key) != expected:
                errors.append(
                    {
                        "code": "proposal_dependency_missing",
                        "message": f"{relative_path} is not aligned to proposal/visual_language.json {key}",
                    }
                )
    for key in ("density_profile", "spacing_rhythm", "shape_profile", "motion_profile"):
        expected = tokens_proposal.get(key)
        if not expected:
            errors.append({"code": "proposal_dependency_missing", "message": f"contract/tokens.json proposal_context is missing {key}"})
            continue
        for relative_path, context in (
            ("contract/brief.json", brief_proposal),
            ("contract/typography.json", typography_proposal),
            ("contract/semantics.json", semantics_proposal),
        ):
            if context.get(key) != expected:
                errors.append(
                    {
                        "code": "proposal_dependency_missing",
                        "message": f"{relative_path} proposal_context {key} does not match contract/tokens.json",
                    }
                )
    if brief.get("technical_constraints", {}).get("density_profile") != tokens_proposal.get("density_profile"):
        errors.append({"code": "proposal_dependency_missing", "message": "contract/brief.json technical_constraints density_profile does not match the selected proposal posture"})
    if brief.get("technical_constraints", {}).get("primary_action_posture") != semantics_proposal.get("button_variant"):
        errors.append({"code": "proposal_dependency_missing", "message": "contract/brief.json primary_action_posture does not match contract/semantics.json"})
    for key in ("button_variant", "card_style"):
        if not semantics_proposal.get(key):
            errors.append({"code": "proposal_dependency_missing", "message": f"contract/semantics.json proposal_context is missing {key}"})

    if proposal_visual.get("direction_name") != proposal_rationale.get("direction_name"):
        errors.append({"code": "proposal_mismatch", "message": "proposal direction_name does not match across proposal artifacts"})

    token_refs = flatten_token_refs(tokens)
    font_families = set(typography.get("font_families", {}).keys())
    font_weights = set(typography.get("font_weights", {}).keys())
    type_scales = set(typography.get("type_scales", {}).keys())
    text_styles = typography.get("text_styles", {})

    for style_name, style in text_styles.items():
        if style.get("family") not in font_families:
            errors.append({"code": "invalid_typography", "message": f"text_styles.{style_name} references unknown family"})
        if style.get("weight") not in font_weights:
            errors.append({"code": "invalid_typography", "message": f"text_styles.{style_name} references unknown weight"})
        if style.get("scale") not in type_scales:
            errors.append({"code": "invalid_typography", "message": f"text_styles.{style_name} references unknown scale"})

    text_roles = semantics.get("text_roles", {})
    for role_name, role in text_roles.items():
        if role.get("style") not in text_styles:
            errors.append({"code": "invalid_semantic_ref", "message": f"text_roles.{role_name} references unknown text style"})

    shape_roles = semantics.get("shape_roles", {})
    for role_name, token_ref in semantics.get("spacing_roles", {}).items():
        if token_ref not in token_refs:
            errors.append({"code": "invalid_token_ref", "message": f"spacing_roles.{role_name} references missing token {token_ref}"})
    for role_name, token_ref in shape_roles.items():
        if token_ref not in token_refs:
            errors.append({"code": "invalid_token_ref", "message": f"shape_roles.{role_name} references missing token {token_ref}"})
    for role_name, token_ref in semantics.get("state_roles", {}).items():
        if isinstance(token_ref, str) and token_ref not in token_refs:
            errors.append({"code": "invalid_token_ref", "message": f"state_roles.{role_name} references missing token {token_ref}"})

    color_roles = flatten_theme_color_roles(semantics)
    for theme_name, theme in semantics.get("themes", {}).items():
        for role_name, value in theme.get("color_roles", {}).items():
            if isinstance(value, str) and not (value in token_refs or is_hex_color(value)):
                errors.append(
                    {
                        "code": "invalid_color_role",
                        "message": f"themes.{theme_name}.color_roles.{role_name} must point to a token ref or hex color",
                    }
                )

    component_roles = semantics.get("component_roles", {})
    for role_name, role in component_roles.items():
        kind = role.get("kind")
        if kind not in CANONICAL_COMPONENT_KINDS:
            errors.append({"code": "invalid_component_kind", "message": f"component_roles.{role_name} uses unsupported kind {kind}"})
        if role.get("text_role") and role["text_role"] not in text_roles:
            errors.append({"code": "invalid_semantic_ref", "message": f"component_roles.{role_name} references unknown text role"})
        if role.get("foreground") and role["foreground"] not in color_roles:
            errors.append({"code": "invalid_semantic_ref", "message": f"component_roles.{role_name} references unknown color role {role['foreground']}"})
        if role.get("background") and role["background"] not in color_roles:
            errors.append({"code": "invalid_semantic_ref", "message": f"component_roles.{role_name} references unknown color role {role['background']}"})
        if role.get("corner") and role["corner"] not in shape_roles:
            errors.append({"code": "invalid_semantic_ref", "message": f"component_roles.{role_name} references unknown shape role {role['corner']}"})
        for property_name in ("min_height", "elevation"):
            if role.get(property_name) and role[property_name] not in token_refs:
                errors.append(
                    {
                        "code": "invalid_token_ref",
                        "message": f"component_roles.{role_name}.{property_name} references missing token {role[property_name]}",
                    }
                )

    proposal_motif_ids = {
        motif.get("id")
        for motif in proposal_motifs.get("motifs", [])
        if isinstance(motif, dict) and motif.get("id")
    }
    allowed_cta_postures = CTA_POSTURE_BY_BUTTON_VARIANT.get(semantics_proposal.get("button_variant"), set())
    allowed_chrome_densities = CHROME_DENSITY_BY_CONTRACT_DENSITY.get(tokens_proposal.get("density_profile"), set())
    allowed_kinds = set(screens.get("allowed_component_kinds", []))
    for screen in screens.get("screens", []):
        missing_structure_keys = [key for key in ("layout_strategy", "cta_posture", "chrome_density", "card_usage", "motif_application") if key not in screen]
        if missing_structure_keys:
            errors.append(
                {
                    "code": "invalid_screen_structure",
                    "message": f"screen {screen.get('screen_id')} is missing structure keys: {', '.join(missing_structure_keys)}",
                }
            )
        motif_application = screen.get("motif_application", {})
        if not isinstance(motif_application, dict):
            errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} motif_application must be an object"})
        else:
            if not motif_application.get("primary_motif"):
                errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} motif_application is missing primary_motif"})
            placement = motif_application.get("placement", [])
            if not isinstance(placement, list) or not placement:
                errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} motif_application must include placement"})
            guided_motifs = screen.get("proposal_alignment", {}).get("primary_motifs", [])
            if guided_motifs and motif_application.get("primary_motif") not in guided_motifs:
                errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} primary_motif does not match proposal_alignment.primary_motifs"})

        primary_button_indexes = [
            index
            for index, component in enumerate(screen.get("components", []))
            if component.get("semantic_role") == "button.primary"
        ]
        if screen.get("cta_posture") == "none" and primary_button_indexes:
            errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} should not include button.primary when cta_posture is none"})
        if screen.get("cta_posture") != "none" and not primary_button_indexes:
            errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} is missing button.primary for cta_posture {screen.get('cta_posture')}"})
        if primary_button_indexes and screen.get("cta_posture") in {"footer_single", "delayed_footer"}:
            if primary_button_indexes[-1] != len(screen.get("components", [])) - 1:
                errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} should end with button.primary for cta_posture {screen.get('cta_posture')}"})
        if primary_button_indexes and screen.get("cta_posture") == "inline_action_strip":
            first_list_index = next(
                (
                    index
                    for index, component in enumerate(screen.get("components", []))
                    if component.get("kind") in {"list", "divider"}
                ),
                None,
            )
            if first_list_index is not None and primary_button_indexes[0] > first_list_index:
                errors.append({"code": "invalid_screen_structure", "message": f"screen {screen.get('screen_id')} should place button.primary before supporting list chrome for inline_action_strip"})
        for component in screen.get("components", []):
            kind = component.get("kind")
            if kind not in allowed_kinds:
                errors.append({"code": "invalid_screen_kind", "message": f"screen {screen.get('screen_id')} uses unsupported kind {kind}"})
            semantic_role = component.get("semantic_role")
            if kind == "text":
                if semantic_role and semantic_role not in text_roles:
                    errors.append({"code": "invalid_screen_role", "message": f"screen {screen.get('screen_id')} text component references unknown text role"})
            elif semantic_role and semantic_role not in component_roles:
                errors.append({"code": "invalid_screen_role", "message": f"screen {screen.get('screen_id')} component references unknown component role"})

        effect_profile = screen_effect_profile(proposal_direction_id or "calm_editorial", screen.get("screen_id", ""))
        for field_name in ("layout_strategy", "cta_posture", "chrome_density", "card_usage"):
            expected = effect_profile.get(field_name)
            if expected and screen.get(field_name) != expected:
                errors.append(
                    {
                        "code": "screen_structure_stale",
                        "message": f"screen {screen.get('screen_id')} {field_name}={screen.get(field_name)!r} does not match the selected proposal effect {expected!r}",
                    }
                )

        component_kinds = [component.get("kind") for component in screen.get("components", [])]
        text_roles_in_screen = {
            component.get("semantic_role")
            for component in screen.get("components", [])
            if component.get("kind") == "text" and component.get("semantic_role")
        }
        for required_kind in effect_profile.get("required_component_kinds", ()):
            if required_kind not in component_kinds:
                errors.append(
                    {
                        "code": "screen_structure_stale",
                        "message": f"screen {screen.get('screen_id')} is missing required component kind {required_kind} for the selected proposal effect",
                    }
                )
        for forbidden_kind in effect_profile.get("forbidden_component_kinds", ()):
            if forbidden_kind in component_kinds:
                errors.append(
                    {
                        "code": "screen_structure_stale",
                        "message": f"screen {screen.get('screen_id')} includes forbidden component kind {forbidden_kind} for the selected proposal effect",
                    }
                )
        for required_text_role in effect_profile.get("required_text_roles", ()):
            if required_text_role not in text_roles_in_screen:
                errors.append(
                    {
                        "code": "screen_structure_stale",
                        "message": f"screen {screen.get('screen_id')} is missing required text role {required_text_role} for the selected proposal effect",
                    }
                )
        if allowed_cta_postures and screen.get("cta_posture") not in allowed_cta_postures:
            errors.append(
                {
                    "code": "screen_contract_drift",
                    "message": f"screen {screen.get('screen_id')} cta_posture {screen.get('cta_posture')!r} does not reflect button_variant {semantics_proposal.get('button_variant')!r}",
                }
            )
        if allowed_chrome_densities and screen.get("chrome_density") not in allowed_chrome_densities:
            errors.append(
                {
                    "code": "screen_contract_drift",
                    "message": f"screen {screen.get('screen_id')} chrome_density {screen.get('chrome_density')!r} does not reflect density_profile {tokens_proposal.get('density_profile')!r}",
                }
            )

        if isinstance(motif_application, dict):
            primary_motif = motif_application.get("primary_motif")
            secondary_motifs = motif_application.get("secondary_motifs", [])
            if primary_motif and primary_motif not in proposal_motif_ids:
                errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} primary_motif {primary_motif!r} is not in proposal/component_motifs.json"})
            for motif_id in secondary_motifs:
                if motif_id not in proposal_motif_ids:
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} secondary motif {motif_id!r} is not in proposal/component_motifs.json"})

            component_lookup = {
                component.get("id"): component
                for component in screen.get("components", [])
                if component.get("id")
            }
            placement_motif_ids: list[str] = []
            guided_motifs = screen.get("proposal_alignment", {}).get("primary_motifs", [])
            for placement in motif_application.get("placement", []):
                if not isinstance(placement, dict):
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} has non-object motif placement"})
                    continue
                component_id = placement.get("component_id")
                motif_id = placement.get("motif_id")
                if component_id not in component_lookup:
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} motif placement references missing component {component_id!r}"})
                    continue
                if motif_id not in proposal_motif_ids:
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} motif placement references unknown motif {motif_id!r}"})
                    continue
                if guided_motifs and motif_id not in guided_motifs:
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} motif placement {motif_id!r} is not tied to proposal_alignment.primary_motifs"})
                component_text = _component_text(component_lookup[component_id])
                if _motif_tokens(motif_id) and not any(token in component_text for token in _motif_tokens(motif_id)):
                    errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} component {component_id!r} does not materially reflect motif {motif_id!r}"})
                placement_motif_ids.append(motif_id)
            if primary_motif and primary_motif not in placement_motif_ids:
                errors.append({"code": "screen_motif_drift", "message": f"screen {screen.get('screen_id')} primary_motif {primary_motif!r} is not actually used in motif placement"})

    used_component_roles = {
        component.get("semantic_role")
        for screen in screens.get("screens", [])
        for component in screen.get("components", [])
        if component.get("semantic_role") and component.get("kind") != "text"
    }
    used_text_roles = {
        component.get("semantic_role")
        for screen in screens.get("screens", [])
        for component in screen.get("components", [])
        if component.get("semantic_role") and component.get("kind") == "text"
    }
    used_color_roles = set()
    used_layout_roles = set()
    used_state_roles = set()
    for screen in screens.get("screens", []):
        layout = screen.get("layout", {})
        if layout.get("background_role"):
            used_color_roles.add(layout["background_role"])
        if layout.get("scroll") == "vertical":
            used_layout_roles.add("scroll.vertical")
        for component in screen.get("components", []):
            role_name = component.get("semantic_role")
            if component.get("kind") != "text" and role_name in component_roles:
                role = component_roles[role_name]
                if role.get("foreground"):
                    used_color_roles.add(role["foreground"])
                if role.get("background"):
                    used_color_roles.add(role["background"])
                if role_name == "button.primary":
                    used_state_roles.update({"disabled.opacity", "pressed.scale"})

    if inspirations is None:
        warnings.append({"code": "inspirations_missing", "message": "No inspirations/index.json file was found."})
    elif inspirations.get("summary", {}).get("asset_count", 0) == 0:
        warnings.append({"code": "inspirations_empty", "message": "Inspiration intake has no imported assets yet."})

    source_coverage = proposal_rationale.get("source_coverage", {})
    covered_sources = source_coverage.get("covered_sources", [])
    if inspirations is not None:
        expected_source_count = inspirations.get("summary", {}).get("source_count", 0)
        covered_source_count = source_coverage.get("covered_source_count", len(covered_sources))
        if expected_source_count and covered_source_count < expected_source_count:
            errors.append(
                {
                    "code": "proposal_coverage_missing",
                    "message": f"proposal/source_rationale.json covers {covered_source_count} of {expected_source_count} inspiration sources",
                }
            )
        signal_source_count = proposal_signals.get("source_patterns", {}).get("source_count")
        if signal_source_count != expected_source_count:
            errors.append(
                {
                    "code": "proposal_signal_mismatch",
                    "message": f"proposal/design_signals.json reports {signal_source_count} sources but inspirations/index.json reports {expected_source_count}",
                }
            )

    if ideas is None:
        warnings.append({"code": "ideas_missing", "message": "No ideas/index.json file was found."})
    elif not ideas.get("ideas"):
        warnings.append({"code": "ideas_empty", "message": "Idea capture has not started yet."})
    else:
        idea_coverage = proposal_rationale.get("idea_coverage", {})
        covered_idea_count = idea_coverage.get("covered_idea_count", len(idea_coverage.get("covered_ideas", [])))
        idea_count = len(ideas.get("ideas", []))
        if covered_idea_count < idea_count:
            errors.append(
                {
                    "code": "proposal_coverage_missing",
                    "message": f"proposal/source_rationale.json covers {covered_idea_count} of {idea_count} captured ideas",
                }
            )
        signal_idea_count = proposal_signals.get("idea_patterns", {}).get("idea_count")
        if signal_idea_count != idea_count:
            errors.append(
                {
                    "code": "proposal_signal_mismatch",
                    "message": f"proposal/design_signals.json reports {signal_idea_count} ideas but ideas/index.json reports {idea_count}",
                }
            )
    if signal_scores and option_entries:
        signal_direction_ids = [entry.get("direction_id") for entry in signal_scores]
        option_direction_ids = [entry.get("direction_id") for entry in sorted(option_entries, key=lambda entry: entry.get("rank", 10**6))]
        if signal_direction_ids != option_direction_ids:
            errors.append({"code": "proposal_mismatch", "message": "proposal/direction_options.json does not align with proposal/design_signals.json archetype ordering"})

    if not screens.get("screens"):
        warnings.append({"code": "screens_empty", "message": "No screens have been defined yet."})

    for platform in requested_platforms:
        mapping_path = output_dir / "platforms" / f"{platform}.json"
        if not mapping_path.exists():
            errors.append({"code": "missing_platform_mapping", "message": f"Missing platform mapping: platforms/{platform}.json"})
            continue
        mapping = read_json(mapping_path)
        required_mapping_keys = (
            "platform",
            "contract_version",
            "guidance_scope",
            "design_intent",
            "typography_guidance",
            "visual_guidance",
            "component_guidance",
            "layout_guidance",
            "interaction_guidance",
            "asset_guidance",
            "implementation_notes",
            "gaps",
        )
        missing_mapping_keys = [key for key in required_mapping_keys if key not in mapping]
        if missing_mapping_keys:
            errors.append(
                {
                    "code": "missing_keys",
                    "message": f"platforms/{platform}.json is missing keys: {', '.join(missing_mapping_keys)}",
                }
            )
            continue
        if mapping.get("platform") != platform:
            errors.append({"code": "platform_mismatch", "message": f"platforms/{platform}.json has platform={mapping.get('platform')}"})
        for role_name in used_text_roles:
            if role_name not in mapping.get("typography_guidance", {}):
                errors.append({"code": "missing_platform_guidance", "message": f"{platform} typography_guidance is missing {role_name}"})
        for role_name in used_component_roles:
            if role_name not in mapping.get("component_guidance", {}):
                errors.append({"code": "missing_platform_guidance", "message": f"{platform} component_guidance is missing {role_name}"})
        for role_name in used_color_roles:
            if role_name not in mapping.get("visual_guidance", {}):
                errors.append({"code": "missing_platform_guidance", "message": f"{platform} visual_guidance is missing {role_name}"})
        for role_name in used_layout_roles:
            if role_name not in mapping.get("layout_guidance", {}):
                warnings.append({"code": "missing_layout_guidance", "message": f"{platform} layout_guidance is missing {role_name}"})
        for role_name in used_state_roles:
            if role_name not in mapping.get("interaction_guidance", {}):
                warnings.append({"code": "missing_interaction_guidance", "message": f"{platform} interaction_guidance is missing {role_name}"})
        blocking_gaps = [
            gap for gap in mapping.get("gaps", [])
            if isinstance(gap, dict) and gap.get("blocking")
        ]
        if blocking_gaps:
            errors.append(
                {
                    "code": "platform_mapping_incomplete",
                    "message": f"{platform} has {len(blocking_gaps)} blocking platform gaps",
                }
            )

    status = "failed" if errors else ("warning" if warnings else "passed")
    return {"status": status, "errors": errors, "warnings": warnings, "checks": checks}


def validation_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Validation Report", "", f"- Status: {report['status']}"]
    if report.get("errors"):
        lines.extend(["", "## Errors"])
        for error in report["errors"]:
            lines.append(f"- {error['code']}: {error['message']}")
    if report.get("warnings"):
        lines.extend(["", "## Warnings"])
        for warning in report["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")
    if report.get("checks"):
        lines.extend(["", "## Checks"])
        for check_name, status in sorted(report["checks"].items()):
            lines.append(f"- {check_name}: {status}")
    return "\n".join(lines)


def run_pipeline(
    output_dir: Path,
    project_name: str,
    platforms: list[str],
    phases: list[str],
    scrape_root: Path | None = None,
    force: bool = False,
    product_summary: str | None = None,
) -> dict[str, Any]:
    run_id = new_run_id()
    started_at = now_iso()
    actions: list[dict[str, str]] = []

    ensure_dir(output_dir)
    for relative_dir in (
        "inspirations",
        "ideas",
        "contract",
        "screens",
        "platforms",
        "metadata",
        "realization",
        "preview",
        "validation",
    ):
        ensure_dir(output_dir / relative_dir)

    project_slug = slugify(project_name)
    inspiration_summary: dict[str, Any] | None = None

    if "ingest" in phases:
        if scrape_root is None:
            inspiration_summary = {
                "imported_at": now_iso(),
                "scrape_root": None,
                "source_count": 0,
                "asset_count": 0,
                "duplicate_group_count": 0,
                "most_common_colors": [],
                "sources": [],
            }
        else:
            inspiration_summary = summarize_scrape_root(scrape_root)
        scaffold_json(output_dir / "inspirations" / "index.json", inspiration_summary, actions, force=force)
    elif (output_dir / "inspirations" / "index.json").exists():
        inspiration_summary = read_json(output_dir / "inspirations" / "index.json")

    if "ideas" in phases:
        scaffold_json(output_dir / "ideas" / "index.json", default_ideas(project_slug), actions, force=force)

    if "contract" in phases:
        scaffold_json(
            output_dir / "contract" / "brief.json",
            default_brief(project_name, project_slug, platforms, inspiration_summary, product_summary),
            actions,
            force=force,
        )
        scaffold_json(output_dir / "contract" / "tokens.json", default_tokens(), actions, force=force)
        scaffold_json(output_dir / "contract" / "typography.json", default_typography(), actions, force=force)
        scaffold_json(output_dir / "contract" / "semantics.json", default_semantics(), actions, force=force)
        scaffold_json(output_dir / "screens" / "index.json", default_screens(), actions, force=force)
        scaffold_json(output_dir / "realization" / "plan.json", default_plan(project_name, platforms), actions, force=force)

    if "platforms" in phases:
        for platform in platforms:
            scaffold_json(
                output_dir / "platforms" / f"{platform}.json",
                default_platform_mapping(platform),
                actions,
                force=force,
            )

    scaffold_markdown(
        output_dir / "preview" / "summary.md",
        preview_summary(project_name, output_dir, platforms, inspiration_summary),
        actions,
        force=force,
    )

    validation_report = None
    if "validate" in phases:
        validation_report = validate_output_dir(output_dir, required_platforms=platforms)
        write_json(output_dir / "validation" / "report.json", validation_report)
        write_markdown(output_dir / "validation" / "report.md", validation_markdown(validation_report))
        actions.append({"path": str(output_dir / "validation" / "report.json"), "action": "updated"})
        actions.append({"path": str(output_dir / "validation" / "report.md"), "action": "updated"})

    completed_at = now_iso()
    run_report = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed" if not validation_report or validation_report["status"] != "failed" else "failed",
        "project": project_name,
        "output_dir": str(output_dir),
        "platform_targets": platforms,
        "phases": phases,
        "scrape_root": str(scrape_root) if scrape_root else None,
        "actions": actions,
        "validation_status": validation_report["status"] if validation_report else None,
    }
    write_json(output_dir / "metadata" / f"orchestrator_run_{run_id}.json", run_report)
    write_json(
        output_dir / "metadata" / "index.json",
        {
            "project": project_name,
            "project_slug": project_slug,
            "output_dir": str(output_dir),
            "last_run_id": run_id,
            "platform_targets": platforms,
            "last_validation_status": validation_report["status"] if validation_report else None,
            "artifacts": {
                "inspirations": "inspirations/index.json",
                "ideas": "ideas/index.json",
                "brief": "contract/brief.json",
                "tokens": "contract/tokens.json",
                "typography": "contract/typography.json",
                "semantics": "contract/semantics.json",
                "screens": "screens/index.json",
                "plan": "realization/plan.json",
                "preview": "preview/summary.md",
                "validation": "validation/report.json" if validation_report else None,
            },
        },
    )
    return run_report


def append_idea(
    output_dir: Path,
    title: str,
    summary: str,
    rationale: str,
    pattern_category: str,
    source_urls: list[str],
    source_assets: list[str],
    target_screens: list[str],
    status: str,
) -> dict[str, Any]:
    ideas_path = output_dir / "ideas" / "index.json"
    if ideas_path.exists():
        idea_store = read_json(ideas_path)
    else:
        idea_store = default_ideas(output_dir.name)

    idea = {
        "idea_id": f"idea-{uuid.uuid4().hex[:8]}",
        "title": title,
        "summary": summary,
        "rationale": rationale,
        "pattern_category": pattern_category,
        "source_urls": source_urls,
        "source_assets": source_assets,
        "target_screens": target_screens,
        "status": status,
        "created_at": now_iso(),
    }
    idea_store.setdefault("ideas", []).append(idea)
    write_json(ideas_path, idea_store)
    return idea

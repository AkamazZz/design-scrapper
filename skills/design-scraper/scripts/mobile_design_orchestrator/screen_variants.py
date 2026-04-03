from __future__ import annotations

from collections.abc import Iterable, Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.project import now_iso, read_json, write_json
from mobile_design_orchestrator.scene_graph import SceneBuildResult, VariantBlueprint, build_variant_scene
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

SCREEN_VARIANT_SCHEMA_VERSION = "2.0.0"
DEFAULT_VARIANT_COUNT = 3


def _bp(
    key: str,
    label: str,
    layout_family: str,
    density: str,
    emphasis: str,
    sections: tuple[str, ...],
    *,
    primary_limit: int = 1,
    secondary_limit: int = 2,
    action_source: str = "jobs",
    navigation_mode: str = "tabs",
    evidence_limit: int = 2,
    critic_focus: tuple[str, ...] = (),
    base_score: float = 0.9,
) -> VariantBlueprint:
    return VariantBlueprint(
        key=key,
        label=label,
        layout_family=layout_family,
        density=density,
        emphasis=emphasis,
        sections=sections,
        primary_limit=primary_limit,
        secondary_limit=secondary_limit,
        action_source=action_source,
        navigation_mode=navigation_mode,
        evidence_limit=evidence_limit,
        critic_focus=critic_focus,
        base_score=base_score,
    )


PURPOSE_VARIANT_LIBRARY: dict[str, tuple[VariantBlueprint, ...]] = {
    "global_navigation": (
        _bp(
            "navigation_spine",
            "Navigation Spine",
            "command_shell",
            "balanced",
            "orientation",
            ("header", "navigation", "status", "secondary_list"),
            action_source="navigation",
            critic_focus=("route clarity", "active destination affordance", "badge restraint"),
            base_score=0.96,
        ),
        _bp(
            "context_hub",
            "Context Hub",
            "hub_stack",
            "balanced",
            "primary_data",
            ("header", "hero", "navigation", "secondary_grid"),
            primary_limit=1,
            secondary_limit=2,
            action_source="mixed",
            critic_focus=("context before route change", "navigation persistence", "quick orientation"),
            base_score=0.92,
        ),
        _bp(
            "quick_switcher",
            "Quick Switcher",
            "switcher_stack",
            "dense",
            "actions",
            ("header", "navigation", "action_strip", "secondary_list"),
            action_source="mixed",
            critic_focus=("fast switching", "compact chrome", "supporting utility modules"),
            base_score=0.88,
        ),
    ),
    "primary_overview": (
        _bp(
            "overview_hero",
            "Overview Hero",
            "metric_first_dashboard",
            "balanced",
            "primary_data",
            ("header", "hero", "action_strip", "secondary_grid", "navigation"),
            primary_limit=2,
            secondary_limit=3,
            action_source="jobs",
            critic_focus=("first viewport hierarchy", "adjacent next action", "secondary restraint"),
            base_score=0.96,
        ),
        _bp(
            "action_first",
            "Action First",
            "next_action_stack",
            "compact",
            "actions",
            ("header", "action_strip", "hero", "secondary_grid", "navigation"),
            primary_limit=1,
            secondary_limit=2,
            action_source="mixed",
            critic_focus=("next action clarity", "metric recall", "lightweight navigation"),
            base_score=0.92,
        ),
        _bp(
            "evidence_dense",
            "Evidence Dense",
            "segmented_modules",
            "dense",
            "evidence",
            ("header", "hero", "primary_list", "secondary_list", "evidence", "navigation"),
            primary_limit=1,
            secondary_limit=3,
            action_source="jobs",
            evidence_limit=3,
            critic_focus=("evidence grounding", "module segmentation", "high density legibility"),
            base_score=0.88,
        ),
    ),
    "user_introduction": (
        _bp(
            "value_then_setup",
            "Value Then Setup",
            "hero_stack",
            "airy",
            "primary_data",
            ("header", "hero", "action_strip", "status"),
            primary_limit=1,
            secondary_limit=1,
            action_source="jobs",
            critic_focus=("value framing", "low setup anxiety", "single clear next step"),
            base_score=0.96,
        ),
        _bp(
            "stepwise_setup",
            "Stepwise Setup",
            "progressive_setup",
            "balanced",
            "actions",
            ("header", "status", "hero", "action_strip", "secondary_list"),
            primary_limit=1,
            secondary_limit=2,
            action_source="jobs",
            critic_focus=("step clarity", "progressive disclosure", "supporting reassurance"),
            base_score=0.92,
        ),
        _bp(
            "reassurance_flow",
            "Reassurance Flow",
            "proof_led_intro",
            "balanced",
            "evidence",
            ("header", "hero", "evidence", "action_strip"),
            primary_limit=1,
            action_source="jobs",
            evidence_limit=3,
            critic_focus=("trust markers", "proof before commitment", "gentle pacing"),
            base_score=0.88,
        ),
    ),
    "contextual_detail": (
        _bp(
            "lead_detail",
            "Lead Detail",
            "segmented_detail",
            "balanced",
            "primary_data",
            ("header", "hero", "action_strip", "secondary_list", "navigation"),
            primary_limit=2,
            secondary_limit=2,
            action_source="mixed",
            critic_focus=("lead entity clarity", "next step proximity", "detail depth"),
            base_score=0.96,
        ),
        _bp(
            "task_followthrough",
            "Task Followthrough",
            "task_followthrough",
            "compact",
            "actions",
            ("header", "action_strip", "hero", "primary_list", "secondary_list"),
            primary_limit=1,
            secondary_limit=2,
            action_source="mixed",
            critic_focus=("task momentum", "decision support", "supporting evidence ordering"),
            base_score=0.92,
        ),
        _bp(
            "supporting_evidence",
            "Supporting Evidence",
            "evidence_detail",
            "dense",
            "evidence",
            ("header", "hero", "secondary_list", "evidence", "navigation"),
            primary_limit=1,
            secondary_limit=3,
            evidence_limit=3,
            critic_focus=("evidence framing", "history legibility", "supporting context discipline"),
            base_score=0.88,
        ),
    ),
    "account_preferences": (
        _bp(
            "summary_preferences",
            "Summary Preferences",
            "summary_stack",
            "balanced",
            "primary_data",
            ("header", "hero", "secondary_list", "action_strip"),
            primary_limit=2,
            secondary_limit=3,
            action_source="jobs",
            critic_focus=("account summary", "clear edit pathway", "supporting settings grouping"),
            base_score=0.96,
        ),
        _bp(
            "edit_focus",
            "Edit Focus",
            "edit_focus",
            "compact",
            "actions",
            ("header", "action_strip", "primary_list", "secondary_list", "status"),
            primary_limit=1,
            secondary_limit=3,
            action_source="jobs",
            critic_focus=("editing confidence", "save affordance", "error resilience"),
            base_score=0.92,
        ),
        _bp(
            "support_context",
            "Support Context",
            "support_context",
            "dense",
            "evidence",
            ("header", "hero", "secondary_list", "evidence"),
            primary_limit=1,
            secondary_limit=3,
            evidence_limit=2,
            critic_focus=("support discoverability", "preference context", "lightweight proof cues"),
            base_score=0.88,
        ),
    ),
    "habit_progress": (
        _bp(
            "streak_hero",
            "Streak Hero",
            "progress_hero",
            "balanced",
            "primary_data",
            ("header", "hero", "secondary_grid", "action_strip"),
            primary_limit=2,
            secondary_limit=2,
            action_source="jobs",
            critic_focus=("momentum at a glance", "trend clarity", "supporting actions"),
            base_score=0.96,
        ),
        _bp(
            "milestone_board",
            "Milestone Board",
            "milestone_board",
            "balanced",
            "actions",
            ("header", "status", "hero", "secondary_grid", "action_strip"),
            primary_limit=1,
            secondary_limit=3,
            action_source="mixed",
            critic_focus=("milestone visibility", "next goal clarity", "state legibility"),
            base_score=0.92,
        ),
        _bp(
            "comparison_dense",
            "Comparison Dense",
            "comparison_stack",
            "dense",
            "evidence",
            ("header", "hero", "primary_list", "secondary_list", "evidence"),
            primary_limit=1,
            secondary_limit=3,
            evidence_limit=3,
            critic_focus=("historical comparison", "dense data scanning", "proof of improvement"),
            base_score=0.88,
        ),
    ),
    "subscription_conversion": (
        _bp(
            "value_first",
            "Value First",
            "offer_stack",
            "balanced",
            "primary_data",
            ("header", "hero", "secondary_list", "action_strip", "evidence"),
            primary_limit=2,
            secondary_limit=2,
            action_source="jobs",
            evidence_limit=2,
            critic_focus=("value before price", "single dominant CTA", "trust reinforcement"),
            base_score=0.96,
        ),
        _bp(
            "plan_compare",
            "Plan Compare",
            "plan_compare",
            "dense",
            "actions",
            ("header", "hero", "primary_list", "secondary_list", "action_strip"),
            primary_limit=1,
            secondary_limit=3,
            action_source="jobs",
            critic_focus=("plan clarity", "comparison legibility", "conversion focus"),
            base_score=0.92,
        ),
        _bp(
            "trust_led",
            "Trust Led",
            "trust_offer",
            "balanced",
            "evidence",
            ("header", "hero", "evidence", "secondary_list", "action_strip"),
            primary_limit=1,
            secondary_limit=2,
            evidence_limit=3,
            critic_focus=("trust first", "proof density", "pricing restraint"),
            base_score=0.88,
        ),
    ),
}

DEFAULT_VARIANTS: tuple[VariantBlueprint, ...] = (
    _bp(
        "balanced_stack",
        "Balanced Stack",
        "balanced_stack",
        "balanced",
        "primary_data",
        ("header", "hero", "secondary_list", "action_strip"),
        primary_limit=1,
        secondary_limit=2,
        action_source="jobs",
        critic_focus=("clear hierarchy", "one primary action", "supporting context order"),
        base_score=0.95,
    ),
    _bp(
        "pathway_led",
        "Pathway Led",
        "pathway_led",
        "compact",
        "actions",
        ("header", "action_strip", "hero", "navigation", "secondary_list"),
        primary_limit=1,
        secondary_limit=2,
        action_source="mixed",
        critic_focus=("path to completion", "orientation", "compact context"),
        base_score=0.91,
    ),
    _bp(
        "context_dense",
        "Context Dense",
        "context_dense",
        "dense",
        "evidence",
        ("header", "hero", "primary_list", "secondary_list", "evidence"),
        primary_limit=1,
        secondary_limit=3,
        evidence_limit=2,
        critic_focus=("context completeness", "proof cues", "legible density"),
        base_score=0.87,
    ),
)


def generate_screen_variants(
    output_dir: Path,
    *,
    run_id: str,
    workspace_version: str = "v2",
    max_variants_per_screen: int = DEFAULT_VARIANT_COUNT,
    screen_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    index = _required_json(output_dir / "screen_briefs" / "index.json", "screen_briefs_missing")
    brief_paths = _screen_brief_paths(index)
    ordered_screen_ids = _ordered_screen_ids(index=index, brief_paths=brief_paths, requested=screen_ids)
    generated_at = now_iso()
    metadata = build_artifact_version_metadata(
        phase="screen_variants",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=SCREEN_VARIANT_SCHEMA_VERSION,
    )

    actions: list[dict[str, str]] = []
    variants_by_screen: dict[str, list[str]] = {}
    total_variants = 0

    for screen_id in ordered_screen_ids:
        brief_path = _resolve_output_path(output_dir=output_dir, path=brief_paths[screen_id])
        brief = _required_json(brief_path, "screen_brief_missing")
        lineage = _build_lineage(output_dir=output_dir, brief_path=brief_path, brief=brief)
        variants = _variants_for_brief(
            brief=brief,
            lineage=lineage,
            metadata=metadata,
            max_variants=max_variants_per_screen,
        )
        screen_paths: list[str] = []
        for variant in variants:
            path = output_dir / "screen_variants" / screen_id / f"variant_{variant['variant_key']}.json"
            existed = path.exists()
            write_json(path, variant)
            actions.append({"path": str(path), "action": "updated" if existed else "created"})
            screen_paths.append(str(path.relative_to(output_dir)))
            total_variants += 1
        variants_by_screen[screen_id] = screen_paths

    return {
        "actions": actions,
        "generated_at": generated_at,
        "screen_count": len(ordered_screen_ids),
        "screen_ids": ordered_screen_ids,
        "variant_count": total_variants,
        "variants_by_screen": variants_by_screen,
    }


def _variants_for_brief(
    *,
    brief: Mapping[str, Any],
    lineage: Mapping[str, Any],
    metadata: Mapping[str, Any],
    max_variants: int,
) -> list[dict[str, Any]]:
    blueprints = PURPOSE_VARIANT_LIBRARY.get(str(brief.get("purpose") or ""), DEFAULT_VARIANTS)
    requested = max(1, max_variants)
    selected_blueprints = blueprints[:requested]
    built_variants: list[dict[str, Any]] = []

    for blueprint in selected_blueprints:
        variant_id = f"{brief['screen_id']}--{blueprint.key}"
        scene = build_variant_scene(brief, blueprint, variant_id=variant_id, lineage=lineage)
        selection_score, score_breakdown = _selection_score(brief=brief, blueprint=blueprint, scene=scene)
        variant_payload = {
            "metadata": dict(metadata),
            "schema_version": SCREEN_VARIANT_SCHEMA_VERSION,
            "variant_id": variant_id,
            "variant_key": blueprint.key,
            "screen_id": brief["screen_id"],
            "scene_graph": scene.scene_graph.to_dict(),
            "data_bindings": [dict(item) for item in scene.data_bindings],
            "states": _states_for_variant(brief=brief, blueprint=blueprint, scene=scene),
            "critic_inputs": _critic_inputs(
                brief=brief,
                blueprint=blueprint,
                scene=scene,
                lineage=lineage,
                score_breakdown=score_breakdown,
            ),
            "selection_score": selection_score,
            "lineage": dict(lineage),
        }
        built_variants.append(variant_payload)

    return sorted(
        built_variants,
        key=lambda item: (-float(item["selection_score"]), str(item["variant_id"])),
    )


def _screen_brief_paths(index: Mapping[str, Any]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    base_dir = Path("screen_briefs")
    for record in index.get("briefs", []):
        if not isinstance(record, Mapping):
            continue
        screen_id = str(record.get("screen_id") or "").strip()
        path_value = str(record.get("path") or "").strip()
        if screen_id and path_value:
            mapping[screen_id] = Path(path_value)
    for screen_id in index.get("screen_ids", []):
        screen_name = str(screen_id).strip()
        if screen_name and screen_name not in mapping:
            mapping[screen_name] = base_dir / f"{screen_name}.json"
    return mapping


def _ordered_screen_ids(
    *,
    index: Mapping[str, Any],
    brief_paths: Mapping[str, Path],
    requested: Iterable[str] | None,
) -> list[str]:
    if requested is not None:
        ordered: list[str] = []
        for screen_id in requested:
            normalized = str(screen_id).strip()
            if normalized and normalized in brief_paths and normalized not in ordered:
                ordered.append(normalized)
        return ordered
    ordered = []
    for screen_id in index.get("screen_ids", []):
        normalized = str(screen_id).strip()
        if normalized and normalized in brief_paths and normalized not in ordered:
            ordered.append(normalized)
    for screen_id in sorted(brief_paths):
        if screen_id not in ordered:
            ordered.append(screen_id)
    return ordered


def _resolve_output_path(*, output_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return output_dir / path


def _build_lineage(*, output_dir: Path, brief_path: Path, brief: Mapping[str, Any]) -> dict[str, Any]:
    evidence_refs = [_evidence_reference(item, index) for index, item in enumerate(brief.get("source_evidence", []), start=1)]
    relative_path = str(brief_path)
    if brief_path.is_absolute():
        relative_path = str(brief_path.relative_to(output_dir))
    fingerprint = hashlib.sha256(
        json.dumps(brief, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return {
        "source_index_path": "screen_briefs/index.json",
        "source_brief_path": relative_path,
        "source_brief_fingerprint": fingerprint,
        "source_brief_generated_at": ((brief.get("metadata", {}) or {}).get("generated_at")),
        "source_schema_version": brief.get("schema_version"),
        "source_idea_ids": list(brief.get("source_idea_ids", [])),
        "evidence_refs": evidence_refs,
    }


def _evidence_reference(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        item = {"kind": "unknown", "value": str(item)}
    kind = str(item.get("kind") or "unknown")
    identity = (
        item.get("idea_id")
        or item.get("source_url")
        or item.get("story")
        or ",".join(str(asset) for asset in item.get("sample_asset_ids", [])[:2])
        or ",".join(str(asset) for asset in item.get("source_assets", [])[:2])
        or f"{kind}-{index:02d}"
    )
    digest = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:12]
    summary = _evidence_summary(item)
    payload = {
        "evidence_ref": f"evidence-{index:02d}-{digest}",
        "kind": kind,
        "summary": summary,
    }
    for key in ("idea_id", "source_url", "story"):
        if item.get(key):
            payload[key] = item[key]
    if item.get("source_assets"):
        payload["source_assets"] = list(item.get("source_assets", [])[:4])
    if item.get("sample_asset_ids"):
        payload["sample_asset_ids"] = list(item.get("sample_asset_ids", [])[:4])
    return payload


def _evidence_summary(item: Mapping[str, Any]) -> str:
    kind = str(item.get("kind") or "evidence")
    if kind == "idea":
        return str(item.get("title") or item.get("idea_id") or "Idea evidence")
    if kind == "source_url":
        return "Source URL"
    if kind == "proposal_guidance":
        return "Proposal guidance"
    if kind == "analysis_records":
        return f"Analysis sample ({item.get('record_count') or 0} records)"
    return kind.replace("_", " ").title()


def _selection_score(
    *,
    brief: Mapping[str, Any],
    blueprint: VariantBlueprint,
    scene: SceneBuildResult,
) -> tuple[float, dict[str, float]]:
    primary_count = len(brief.get("primary_data", []))
    secondary_count = len(brief.get("secondary_data", []))
    navigation_count = len(brief.get("navigation_edges", []))
    state_count = len(brief.get("required_states", []))
    motif_count = len((brief.get("direction_context", {}) or {}).get("primary_motifs", []))
    total_bindings = max(1, primary_count + secondary_count)
    realized_bindings = min(len(scene.data_bindings), total_bindings)

    breakdown = {
        "base_fit": round(blueprint.base_score, 3),
        "data_coverage": round(realized_bindings / total_bindings, 3),
        "navigation_support": round(
            1.0
            if navigation_count == 0
            else (
                1.0
                if "navigation" in blueprint.sections or blueprint.action_source in {"navigation", "mixed"}
                else 0.72
            ),
            3,
        ),
        "state_resilience": round(
            1.0
            if state_count <= 2 or {"status", "evidence"} & set(blueprint.sections)
            else 0.84,
            3,
        ),
        "motif_alignment": round(1.0 if motif_count == 0 or "hero" in blueprint.sections else 0.86, 3),
    }
    score = blueprint.base_score
    score += 0.02 * breakdown["data_coverage"]
    score += 0.01 * (breakdown["navigation_support"] - 0.8)
    score += 0.005 * (breakdown["state_resilience"] - 0.8)
    score += 0.005 * (breakdown["motif_alignment"] - 0.8)
    return round(min(score, 0.999), 3), breakdown


def _states_for_variant(
    *,
    brief: Mapping[str, Any],
    blueprint: VariantBlueprint,
    scene: SceneBuildResult,
) -> list[dict[str, Any]]:
    section_ids = scene.section_node_ids
    content_targets = [
        section_ids[name]
        for name in ("hero", "primary_list", "secondary_grid", "secondary_list")
        if name in section_ids
    ]
    action_target = section_ids.get("action_strip")
    navigation_target = section_ids.get("navigation")
    header_target = section_ids.get("header")
    states: list[dict[str, Any]] = []

    for raw_state in brief.get("required_states", []):
        state_name = str(raw_state).strip()
        if not state_name:
            continue
        modifiers: list[dict[str, Any]] = []
        notes: list[str] = []
        if state_name == "default":
            notes.append("Keep the baseline hierarchy intact.")
        elif state_name == "loading":
            loading_targets = content_targets or ([header_target] if header_target else [])
            modifiers.extend({"node_id": node_id, "mutation": "skeletonize"} for node_id in loading_targets)
            notes.append("Show skeleton structure without hiding layout intent.")
        elif state_name == "empty":
            target = content_targets[0] if content_targets else header_target
            if target:
                modifiers.append({"node_id": target, "mutation": "replace_with_empty_message"})
            notes.append("Keep the next step visible even when primary content is empty.")
        elif state_name == "error":
            target = action_target or header_target
            if target:
                modifiers.append({"node_id": target, "mutation": "inject_error_banner"})
            notes.append("Present recovery inline without collapsing the main hierarchy.")
        elif state_name in {"goal_hit", "completed", "save_success"}:
            target = action_target or (content_targets[0] if content_targets else header_target)
            if target:
                modifiers.append({"node_id": target, "mutation": "emphasize_success_feedback"})
            notes.append("Celebrate completion without overwhelming the primary surface.")
        elif state_name == "step_incomplete":
            if action_target:
                modifiers.append({"node_id": action_target, "mutation": "disable_primary_action"})
            notes.append("Expose missing requirements before moving forward.")
        elif state_name == "permission_needed":
            target = action_target or header_target
            if target:
                modifiers.append({"node_id": target, "mutation": "insert_permission_request"})
            notes.append("Frame permissions as a contextual ask, not a dead end.")
        elif state_name == "editing":
            target = content_targets[0] if content_targets else header_target
            if target:
                modifiers.append({"node_id": target, "mutation": "toggle_edit_mode"})
            notes.append("Keep save and cancel affordances explicit.")
        elif state_name == "comparison_expanded":
            target = section_ids.get("secondary_list") or section_ids.get("secondary_grid")
            if target:
                modifiers.append({"node_id": target, "mutation": "expand_supporting_comparison"})
            notes.append("Expanded comparison should not bury the primary offer.")
        elif state_name == "purchase_pending":
            if action_target:
                modifiers.append({"node_id": action_target, "mutation": "show_pending_progress"})
            notes.append("Keep purchase feedback immediate and reversible.")
        elif state_name == "purchase_error":
            if action_target:
                modifiers.append({"node_id": action_target, "mutation": "show_purchase_error"})
            notes.append("Preserve plan context while surfacing the failure.")
        elif state_name == "active_tab_changed":
            if navigation_target:
                modifiers.append({"node_id": navigation_target, "mutation": "highlight_active_destination"})
            notes.append("Route change should be obvious without extra chrome.")
        else:
            target = content_targets[0] if content_targets else header_target
            if target:
                modifiers.append({"node_id": target, "mutation": "apply_state_treatment", "state": state_name})
            notes.append(
                f"Reflect `{state_name}` without breaking the {blueprint.layout_family.replace('_', ' ')} structure."
            )
        affected = sorted({modifier["node_id"] for modifier in modifiers if modifier.get("node_id")})
        states.append(
            {
                "state_id": state_name,
                "label": state_name.replace("_", " ").title(),
                "affected_node_ids": affected,
                "scene_modifiers": modifiers,
                "notes": notes,
            }
        )
    return states


def _critic_inputs(
    *,
    brief: Mapping[str, Any],
    blueprint: VariantBlueprint,
    scene: SceneBuildResult,
    lineage: Mapping[str, Any],
    score_breakdown: Mapping[str, float],
) -> dict[str, Any]:
    jobs = [str(item) for item in brief.get("jobs_to_be_done", []) if str(item).strip()]
    design_risks = [str(item) for item in brief.get("design_risks", []) if str(item).strip()]
    checks = [
        f"Protect {blueprint.emphasis.replace('_', ' ')} in the first viewport.",
        *design_risks[:2],
    ]
    if brief.get("navigation_edges"):
        checks.append("Preserve navigation orientation while variant-specific modules reflow.")
    if brief.get("required_states"):
        checks.append(
            "Support the required states without inventing new screen architecture."
        )
    return {
        "critic_version": "1",
        "variant_label": blueprint.label,
        "variant_family": blueprint.layout_family,
        "focus": list(blueprint.critic_focus),
        "jobs_to_be_done": jobs,
        "design_risks": design_risks,
        "focus_node_ids": list(scene.focus_node_ids),
        "checks": checks,
        "score_breakdown": dict(score_breakdown),
        "lineage_refs": [item["evidence_ref"] for item in lineage.get("evidence_refs", [])],
        "brief_fingerprint": lineage.get("source_brief_fingerprint"),
    }


def _required_json(path: Path, failure_code: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{failure_code}: missing file {path}")
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{failure_code}: expected object in {path}")
    return data

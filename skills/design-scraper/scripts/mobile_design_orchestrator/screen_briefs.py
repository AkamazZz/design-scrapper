from __future__ import annotations

from pathlib import Path
from typing import Any

from mobile_design_orchestrator.project import default_ideas, load_optional_json, now_iso, read_json, slugify, write_json
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

SCREEN_BRIEF_SCHEMA_VERSION = "2.0.0"
MAX_EVIDENCE_ASSETS = 12

SCREEN_PURPOSES = {
    "app_shell": "global_navigation",
    "home": "primary_overview",
    "onboarding": "user_introduction",
    "detail": "contextual_detail",
    "profile": "account_preferences",
    "progress": "habit_progress",
    "paywall": "subscription_conversion",
}

SCREEN_DATA_MAP = {
    "app_shell": {
        "primary": ["navigation.destinations", "navigation.active_route"],
        "secondary": ["system.badges", "global.search_entry"],
        "jobs": ["Move between primary product areas without losing orientation."],
    },
    "home": {
        "primary": ["dashboard.primary_metrics", "coach.next_action", "progress.summary"],
        "secondary": ["quick_actions", "recent_activity", "secondary_modules"],
        "jobs": ["Understand current status quickly.", "Identify the next action without scanning the whole screen."],
    },
    "onboarding": {
        "primary": ["user.goals", "plan.preferences", "personalization.inputs"],
        "secondary": ["trust_markers", "coach.introduction"],
        "jobs": ["Understand the product promise.", "Set initial goals with minimal friction."],
    },
    "detail": {
        "primary": ["detail.primary_entity", "detail.metrics", "detail.next_action"],
        "secondary": ["supporting_context", "history", "related_items"],
        "jobs": ["Inspect one entity in depth.", "Take the next contextual action confidently."],
    },
    "profile": {
        "primary": ["account.identity", "plan.status", "preferences.core"],
        "secondary": ["history", "device.connections", "support_links"],
        "jobs": ["Adjust account and plan settings.", "Review important profile context quickly."],
    },
    "progress": {
        "primary": ["progress.streaks", "progress.milestones", "progress.trend"],
        "secondary": ["history", "comparisons", "next_goal"],
        "jobs": ["Understand momentum over time.", "See what to improve next."],
    },
    "paywall": {
        "primary": ["subscription.value_props", "subscription.plan_options", "subscription.primary_cta"],
        "secondary": ["comparison_table", "trust_signals", "faq_short"],
        "jobs": ["Evaluate upgrade value quickly.", "Choose or dismiss the offer without confusion."],
    },
}

SCREEN_STATE_MAP = {
    "app_shell": ["default", "active_tab_changed"],
    "home": ["default", "loading", "empty", "error", "goal_hit"],
    "onboarding": ["default", "step_incomplete", "permission_needed", "completed"],
    "detail": ["default", "loading", "empty", "error"],
    "profile": ["default", "editing", "save_success", "error"],
    "progress": ["default", "loading", "empty", "goal_hit"],
    "paywall": ["default", "comparison_expanded", "purchase_pending", "purchase_error"],
}


def _required_json(path: Path, failure_code: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{failure_code}: missing file {path}")
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{failure_code}: expected object in {path}")
    return data


def _proposal_bundle(output_dir: Path) -> dict[str, Any]:
    return {
        "design_signals": _required_json(output_dir / "proposal" / "design_signals.json", "proposal_missing"),
        "visual_language": _required_json(output_dir / "proposal" / "visual_language.json", "proposal_missing"),
        "component_motifs": _required_json(output_dir / "proposal" / "component_motifs.json", "proposal_missing"),
        "source_rationale": _required_json(output_dir / "proposal" / "source_rationale.json", "proposal_missing"),
        "typography_voice": _required_json(output_dir / "proposal" / "typography_voice.json", "proposal_missing"),
    }


def _default_screen_ids(ideas: dict[str, Any], proposal_bundle: dict[str, Any]) -> list[str]:
    recommended = [
        entry.get("screen_id")
        for entry in proposal_bundle.get("source_rationale", {}).get("recommended_screens", [])
        if isinstance(entry, dict) and entry.get("screen_id")
    ]
    ordered: list[str] = []
    for screen_id in recommended:
        if screen_id not in ordered:
            ordered.append(screen_id)
    explicit: list[str] = []
    categories = set()
    for idea in ideas.get("ideas", []):
        explicit.extend(idea.get("target_screens", []))
        if idea.get("pattern_category"):
            categories.add(idea["pattern_category"])
    for screen_id in explicit:
        if screen_id and screen_id not in ordered:
            ordered.append(screen_id)
    if not ordered:
        if "onboarding" in categories:
            ordered.append("onboarding")
        if {"dashboard", "home", "navigation"} & categories:
            ordered.append("home")
        if {"detail", "content", "card", "form"} & categories:
            ordered.append("detail")
        if {"profile"} & categories:
            ordered.append("profile")
        if {"progress"} & categories:
            ordered.append("progress")
    if not ordered:
        ordered = ["home", "detail"]
    if "app_shell" not in ordered:
        ordered.insert(0, "app_shell")
    return ordered


def _screen_ideas(ideas: dict[str, Any], screen_id: str) -> list[dict[str, Any]]:
    matches = [
        idea
        for idea in ideas.get("ideas", [])
        if isinstance(idea, dict)
        and (screen_id in idea.get("target_screens", []) or (screen_id == "home" and not idea.get("target_screens")))
    ]
    return matches


def _screen_guidance(proposal_bundle: dict[str, Any], screen_id: str) -> dict[str, Any]:
    for entry in proposal_bundle.get("source_rationale", {}).get("recommended_screens", []):
        if isinstance(entry, dict) and entry.get("screen_id") == screen_id:
            return entry
    return {}


def _motifs_for_screen(proposal_bundle: dict[str, Any], screen_id: str, guidance: dict[str, Any]) -> list[str]:
    guided = [motif_id for motif_id in guidance.get("primary_motifs", []) if motif_id]
    if guided:
        return guided
    motifs = []
    for motif in proposal_bundle.get("component_motifs", {}).get("motifs", []):
        if isinstance(motif, dict) and screen_id in motif.get("applicable_screens", []) and motif.get("id"):
            motifs.append(motif["id"])
    return motifs


def _navigation_edges(screen_id: str, screen_ids: list[str]) -> list[dict[str, Any]]:
    available = set(screen_ids)
    lookup = {
        "app_shell": ["home", "detail", "progress", "profile", "paywall"],
        "home": ["detail", "progress", "profile", "paywall", "app_shell"],
        "onboarding": ["home"],
        "detail": ["home", "progress", "app_shell"],
        "profile": ["home", "app_shell"],
        "progress": ["home", "detail", "app_shell"],
        "paywall": ["home", "app_shell"],
    }
    targets = [target for target in lookup.get(screen_id, ["home"]) if target in available and target != screen_id]
    if not targets:
        targets = [target for target in screen_ids if target != screen_id][:1]
    return [
        {
            "action": "navigate",
            "target_screen_id": target,
            "priority": "primary" if index == 0 else "secondary",
        }
        for index, target in enumerate(targets)
    ]


def _source_evidence(
    screen_id: str,
    screen_ideas: list[dict[str, Any]],
    guidance: dict[str, Any],
    analysis_manifest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for idea in screen_ideas:
        key = f"idea::{idea.get('idea_id')}"
        if key not in seen_keys:
            evidence.append(
                {
                    "kind": "idea",
                    "idea_id": idea.get("idea_id"),
                    "title": idea.get("title"),
                    "confidence": idea.get("confidence"),
                    "source_urls": idea.get("source_urls", []),
                    "source_assets": idea.get("source_assets", [])[:MAX_EVIDENCE_ASSETS],
                }
            )
            seen_keys.add(key)
    for source_url in sorted({url for idea in screen_ideas for url in idea.get("source_urls", [])}):
        key = f"url::{source_url}"
        if key not in seen_keys:
            evidence.append({"kind": "source_url", "source_url": source_url})
            seen_keys.add(key)
    if guidance.get("story"):
        evidence.append(
            {
                "kind": "proposal_guidance",
                "story": guidance.get("story"),
                "primary_motifs": guidance.get("primary_motifs", []),
            }
        )
    if analysis_manifest:
        matched_records = []
        for record in analysis_manifest.get("records", []):
            if not isinstance(record, dict):
                continue
            purpose = record.get("purpose_guess")
            if screen_id == "home" and purpose == "dashboard":
                matched_records.append(record)
            elif screen_id == "detail" and purpose == "detail":
                matched_records.append(record)
            elif screen_id == "profile" and purpose == "profile":
                matched_records.append(record)
            elif screen_id == "onboarding" and purpose == "onboarding":
                matched_records.append(record)
        if matched_records:
            sample = matched_records[:MAX_EVIDENCE_ASSETS]
            evidence.append(
                {
                    "kind": "analysis_records",
                    "record_count": len(matched_records),
                    "sample_asset_ids": [record.get("asset_id") for record in sample if record.get("asset_id")],
                    "sample_source_urls": sorted({record.get("source_url") for record in sample if record.get("source_url")}),
                }
            )
    if not evidence:
        evidence.append({"kind": "fallback", "reason": f"No direct evidence mapped for `{screen_id}`; using planner defaults."})
    return evidence


def _design_risks(screen_id: str, direction_name: str, motifs: list[str]) -> list[str]:
    motif_text = ", ".join(motif.replace("_", " ") for motif in motifs) if motifs else "default motif set"
    risks = [
        f"Do not let `{screen_id}` drift away from the selected direction `{direction_name}`.",
        f"Keep motif usage focused; avoid turning {motif_text} into decorative noise.",
        "Preserve clear hierarchy before adding secondary surfaces or copy.",
    ]
    if screen_id == "home":
        risks.append("Do not let too many competing modules hide the primary next action.")
    if screen_id == "paywall":
        risks.append("Do not bury pricing clarity under brand atmosphere.")
    if screen_id == "onboarding":
        risks.append("Do not make early setup feel longer than the value it unlocks.")
    return risks


def _screen_brief_record(
    *,
    screen_id: str,
    screen_ids: list[str],
    screen_ideas: list[dict[str, Any]],
    proposal_bundle: dict[str, Any],
    contract_brief: dict[str, Any] | None,
    analysis_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    guidance = _screen_guidance(proposal_bundle, screen_id)
    motifs = _motifs_for_screen(proposal_bundle, screen_id, guidance)
    purpose = SCREEN_PURPOSES.get(screen_id, "mobile_flow_step")
    screen_data = SCREEN_DATA_MAP.get(
        screen_id,
        {
            "primary": [f"{screen_id}.primary_entity"],
            "secondary": [f"{screen_id}.supporting_context"],
            "jobs": [f"Complete the main `{screen_id}` task without unnecessary context switching."],
        },
    )
    project_summary = ((contract_brief or {}).get("project") or {}).get("summary")
    direction_name = proposal_bundle.get("visual_language", {}).get("direction_name", "Mobile design direction")
    return {
        "schema_version": SCREEN_BRIEF_SCHEMA_VERSION,
        "screen_id": screen_id,
        "title": guidance.get("story") or screen_id.replace("_", " ").title(),
        "purpose": purpose,
        "jobs_to_be_done": list(screen_data["jobs"]),
        "primary_data": list(screen_data["primary"]),
        "secondary_data": list(screen_data["secondary"]),
        "required_states": list(SCREEN_STATE_MAP.get(screen_id, ["default", "loading", "error"])),
        "navigation_edges": _navigation_edges(screen_id, screen_ids),
        "source_evidence": _source_evidence(screen_id, screen_ideas, guidance, analysis_manifest),
        "design_risks": _design_risks(screen_id, direction_name, motifs),
        "source_idea_ids": [idea.get("idea_id") for idea in screen_ideas if idea.get("idea_id")],
        "direction_context": {
            "direction_id": proposal_bundle.get("visual_language", {}).get("direction_id"),
            "direction_name": direction_name,
            "motion_posture": proposal_bundle.get("visual_language", {}).get("motion_posture"),
            "composition_principles": proposal_bundle.get("visual_language", {}).get("composition_principles", []),
            "primary_motifs": motifs,
        },
        "planning_context": {
            "story": guidance.get("story"),
            "product_summary": project_summary,
            "top_idea_titles": [idea.get("title") for idea in screen_ideas[:3] if idea.get("title")],
        },
    }


def generate_screen_briefs(
    output_dir: Path,
    *,
    run_id: str,
    workspace_version: str = "v2",
) -> dict[str, Any]:
    ideas = load_optional_json(output_dir / "ideas" / "index.json") or default_ideas(slugify(output_dir.name))
    proposal_bundle = _proposal_bundle(output_dir)
    analysis_manifest = load_optional_json(output_dir / "analysis" / "screen_manifest.json")
    contract_brief = load_optional_json(output_dir / "contract" / "brief.json")
    screen_ids = _default_screen_ids(ideas, proposal_bundle)
    generated_at = now_iso()
    metadata = build_artifact_version_metadata(
        phase="screen_briefs",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=SCREEN_BRIEF_SCHEMA_VERSION,
    )

    brief_records = [
        _screen_brief_record(
            screen_id=screen_id,
            screen_ids=screen_ids,
            screen_ideas=_screen_ideas(ideas, screen_id),
            proposal_bundle=proposal_bundle,
            contract_brief=contract_brief,
            analysis_manifest=analysis_manifest,
        )
        for screen_id in screen_ids
    ]

    index_payload = {
        "schema_version": SCREEN_BRIEF_SCHEMA_VERSION,
        "project": ((contract_brief or {}).get("project") or {}).get("name") or output_dir.name,
        "generated_at": generated_at,
        "metadata": metadata,
        "screen_ids": screen_ids,
        "primary_screen": proposal_bundle.get("source_rationale", {}).get("signal_summary", {}).get("primary_screen"),
        "direction_id": proposal_bundle.get("visual_language", {}).get("direction_id"),
        "direction_name": proposal_bundle.get("visual_language", {}).get("direction_name"),
        "briefs": [
            {
                "screen_id": record["screen_id"],
                "path": f"screen_briefs/{record['screen_id']}.json",
                "purpose": record["purpose"],
                "required_states": record["required_states"],
                "primary_motifs": record["direction_context"]["primary_motifs"],
            }
            for record in brief_records
        ],
    }

    actions: list[dict[str, str]] = []
    index_path = output_dir / "screen_briefs" / "index.json"
    index_existed = index_path.exists()
    write_json(index_path, index_payload)
    actions.append({"path": str(index_path), "action": "updated" if index_existed else "created"})
    for record in brief_records:
        path = output_dir / "screen_briefs" / f"{record['screen_id']}.json"
        existed = path.exists()
        payload = {"metadata": metadata, **record}
        write_json(path, payload)
        actions.append({"path": str(path), "action": "updated" if existed else "created"})
    return {
        "actions": actions,
        "screen_count": len(brief_records),
        "screen_ids": screen_ids,
    }

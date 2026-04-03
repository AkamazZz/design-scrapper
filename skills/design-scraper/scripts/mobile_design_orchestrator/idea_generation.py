from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.project import default_ideas, load_optional_json, now_iso, read_json, slugify, write_json
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

IDEA_SCHEMA_VERSION = "2.0.0"

IDEA_RULES = {
    "dashboard": {
        "keywords": ("dashboard", "home", "today", "summary", "progress", "stats", "metrics", "gauge", "ring"),
        "title": "Evidence-backed home dashboard",
        "summary": "Let the home screen lead with the highest-signal metrics and next actions instead of a flat feed.",
        "rationale": "The source mix suggests a dashboard-first structure with visible progress and quick orientation.",
        "target_screens": ["home"],
    },
    "onboarding": {
        "keywords": ("onboard", "welcome", "intro", "coach", "setup", "start"),
        "title": "Guided onboarding ramp",
        "summary": "Use early screens to frame the product goal, personalize targets, and reduce first-run ambiguity.",
        "rationale": "The references imply that first-run clarity matters enough to justify a guided setup path.",
        "target_screens": ["onboarding"],
    },
    "detail": {
        "keywords": ("detail", "entry", "session", "program", "meal", "item"),
        "title": "Focused detail screen hierarchy",
        "summary": "Keep one primary object per detail screen and bias the layout toward scanability over decoration.",
        "rationale": "The asset set supports deeper drill-in flows that still need to stay operationally clear.",
        "target_screens": ["detail"],
    },
    "form": {
        "keywords": ("form", "input", "log", "search", "scan", "add", "edit"),
        "title": "Fast capture workflow",
        "summary": "Design input-heavy flows for speed, with clear defaults, compact controls, and decisive actions.",
        "rationale": "Repeated capture-oriented cues in the sources point to frequent entry flows that need low friction.",
        "target_screens": ["composer", "detail"],
    },
    "navigation": {
        "keywords": ("tab", "nav", "menu", "browse", "discover", "library", "feed"),
        "title": "Predictable navigation spine",
        "summary": "Use a small, stable navigation model so the product remains easy to traverse as features expand.",
        "rationale": "The reference set is broad enough that navigation consistency is a stronger constraint than novelty.",
        "target_screens": ["app_shell"],
    },
    "profile": {
        "keywords": ("profile", "account", "settings", "membership", "plan"),
        "title": "Operational account surface",
        "summary": "Treat account settings as a practical control surface with plan, preferences, and history easy to locate.",
        "rationale": "Sources containing account and settings cues usually demand a reliable utility layer.",
        "target_screens": ["profile"],
    },
    "progress": {
        "keywords": ("streak", "history", "badge", "calendar", "progress", "achievement"),
        "title": "Progress and retention layer",
        "summary": "Translate repeat engagement into visible progress states so retention comes from feedback, not reminders alone.",
        "rationale": "The source set includes enough progress-oriented signals to justify a dedicated retention pattern.",
        "target_screens": ["home", "detail"],
    },
}

MAX_SOURCE_ASSETS_PER_IDEA = 12


def _stable_idea_id(pattern_category: str, source_urls: list[str], source_assets: list[str]) -> str:
    payload = "|".join([pattern_category, *sorted(source_urls), *sorted(source_assets)])
    return f"idea-auto-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8]}"


def _idea_fields(existing_ideas: dict[str, Any] | None, project_slug: str) -> list[str]:
    base_fields = list((existing_ideas or default_ideas(project_slug)).get("idea_fields", []))
    extras = ["confidence", "evidence", "review_status", "auto_generated"]
    for field in extras:
        if field not in base_fields:
            base_fields.append(field)
    return base_fields


def _collect_evidence(inspirations: dict[str, Any], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {
        category: {
            "source_urls": set(),
            "source_assets": set(),
            "matched_terms": set(),
            "asset_count": 0,
        }
        for category in IDEA_RULES
    }

    manifest_lookup: dict[str, dict[str, Any]] = {}
    if analysis:
        for record in analysis.get("records", []):
            if isinstance(record, dict):
                manifest_lookup[record.get("asset_id")] = record

    for source in inspirations.get("sources", []):
        source_url = source.get("source_url")
        source_text = " ".join(
            [
                source.get("source") or "",
                source.get("title") or "",
                source.get("author") or "",
                source.get("source_url") or "",
            ]
        ).lower()
        for asset in source.get("assets", []):
            duplicate = asset.get("duplicate") or {}
            if not duplicate.get("included", True):
                continue
            asset_id = asset.get("asset_id")
            manifest_text = ""
            manifest_record = manifest_lookup.get(asset_id)
            if manifest_record:
                manifest_text = " ".join(
                    [
                        manifest_record.get("purpose_guess") or "",
                        " ".join(manifest_record.get("component_tags", [])),
                    ]
                ).lower()
            text = " ".join(
                [
                    source_text,
                    asset.get("canonical_url") or "",
                    asset.get("relative_path") or "",
                    asset.get("mime_type") or "",
                    manifest_text,
                ]
            ).lower()
            for category, rule in IDEA_RULES.items():
                matches = [keyword for keyword in rule["keywords"] if keyword in text]
                if matches:
                    bucket = by_category[category]
                    if source_url:
                        bucket["source_urls"].add(source_url)
                    if asset_id:
                        bucket["source_assets"].add(asset_id)
                    bucket["matched_terms"].update(matches)
                    bucket["asset_count"] += 1

    screen_like_assets = sum(
        1
        for source in inspirations.get("sources", [])
        for asset in source.get("assets", [])
        if (asset.get("kind") == "image" and (asset.get("duplicate") or {}).get("included", True))
    )
    if screen_like_assets:
        by_category["dashboard"]["asset_count"] = max(by_category["dashboard"]["asset_count"], screen_like_assets)
        by_category["navigation"]["asset_count"] = max(by_category["navigation"]["asset_count"], max(1, screen_like_assets // 3))
    return by_category


def generate_automated_ideas(
    inspirations: dict[str, Any],
    existing_ideas: dict[str, Any] | None = None,
    analysis_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = inspirations.get("project") or "mobile-project"
    project_slug = slugify(project)
    created_at = inspirations.get("ingested_at") or inspirations.get("selected_run", {}).get("completed_at") or now_iso()
    evidence = _collect_evidence(inspirations, analysis_manifest)
    generated_ideas: list[dict[str, Any]] = []

    for category, rule in IDEA_RULES.items():
        bucket = evidence[category]
        source_urls = sorted(bucket["source_urls"])
        source_assets = sorted(bucket["source_assets"])
        sampled_assets = source_assets[:MAX_SOURCE_ASSETS_PER_IDEA]
        matched_terms = sorted(bucket["matched_terms"])
        asset_count = bucket["asset_count"]
        if not source_urls and asset_count < 2 and category not in {"dashboard", "navigation"}:
            continue
        confidence = min(0.95, round(0.35 + (0.1 * len(source_urls)) + (0.04 * min(asset_count, 5)) + (0.03 * len(matched_terms)), 2))
        idea_id = _stable_idea_id(category, source_urls, source_assets)
        generated_ideas.append(
            {
                "idea_id": idea_id,
                "title": rule["title"],
                "summary": rule["summary"],
                "rationale": rule["rationale"],
                "pattern_category": category,
                "source_urls": source_urls,
                "source_assets": sampled_assets,
                "target_screens": list(rule["target_screens"]),
                "status": "candidate",
                "created_at": created_at,
                "confidence": confidence,
                "evidence": {
                    "matched_terms": matched_terms,
                    "source_count": len(source_urls),
                    "asset_count": asset_count,
                    "asset_sample_count": len(sampled_assets),
                },
                "review_status": "needs_review",
                "auto_generated": True,
            }
        )

    generated_ideas.sort(key=lambda item: (-item.get("confidence", 0), item.get("pattern_category", ""), item.get("idea_id", "")))
    existing_ids = {idea.get("idea_id") for idea in (existing_ideas or {}).get("ideas", []) if isinstance(idea, dict)}
    merge_candidates = [idea for idea in generated_ideas if idea["idea_id"] not in existing_ids]
    return {
        "schema_version": IDEA_SCHEMA_VERSION,
        "project": project_slug,
        "generated_at": created_at,
        "generator": "deterministic_heuristics_v1",
        "idea_fields": _idea_fields(existing_ideas, project_slug),
        "ideas": generated_ideas,
        "merge_candidates": merge_candidates,
        "merge_summary": {
            "generated_count": len(generated_ideas),
            "new_count": len(merge_candidates),
            "existing_count": len(existing_ids),
        },
    }


def build_review_queue(auto_generated: dict[str, Any]) -> dict[str, Any]:
    items = []
    for priority, idea in enumerate(auto_generated.get("merge_candidates", []), start=1):
        items.append(
            {
                "priority": priority,
                "idea_id": idea.get("idea_id"),
                "title": idea.get("title"),
                "pattern_category": idea.get("pattern_category"),
                "confidence": idea.get("confidence"),
                "review_status": idea.get("review_status"),
                "source_urls": idea.get("source_urls", []),
                "source_assets": idea.get("source_assets", []),
            }
        )
    return {
        "schema_version": IDEA_SCHEMA_VERSION,
        "project": auto_generated.get("project"),
        "generated_at": auto_generated.get("generated_at"),
        "item_count": len(items),
        "items": items,
    }


def merge_generated_ideas(existing_ideas: dict[str, Any] | None, auto_generated: dict[str, Any]) -> dict[str, Any]:
    project_slug = auto_generated.get("project") or slugify((existing_ideas or {}).get("project") or "mobile-project")
    merged = existing_ideas.copy() if isinstance(existing_ideas, dict) else default_ideas(project_slug)
    merged["project"] = merged.get("project") or project_slug
    merged["idea_fields"] = _idea_fields(existing_ideas, project_slug)
    existing_items = [idea for idea in merged.get("ideas", []) if isinstance(idea, dict)]
    existing_ids = {idea.get("idea_id") for idea in existing_items}
    for idea in auto_generated.get("merge_candidates", []):
        if idea.get("idea_id") not in existing_ids:
            existing_items.append(idea)
            existing_ids.add(idea.get("idea_id"))
    merged["ideas"] = existing_items
    return merged


def write_automated_idea_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    workspace_version: str = "v2",
) -> dict[str, Any]:
    inspirations_path = output_dir / "inspirations" / "index.json"
    if not inspirations_path.exists():
        raise FileNotFoundError(f"ideas_input_missing: missing file {inspirations_path}")
    inspirations = read_json(inspirations_path)
    project_slug = slugify(inspirations.get("project") or output_dir.name)
    ideas_path = output_dir / "ideas" / "index.json"
    existing_ideas = load_optional_json(ideas_path) or default_ideas(project_slug)
    analysis_manifest = load_optional_json(output_dir / "analysis" / "screen_manifest.json")

    auto_generated = generate_automated_ideas(inspirations, existing_ideas=existing_ideas, analysis_manifest=analysis_manifest)
    metadata = build_artifact_version_metadata(
        phase="ideas",
        run_id=run_id,
        generated_at=auto_generated.get("generated_at") or now_iso(),
        workspace_version=workspace_version,
        schema_version=IDEA_SCHEMA_VERSION,
    )
    auto_generated["metadata"] = metadata

    review_queue = build_review_queue(auto_generated)
    review_queue["metadata"] = metadata

    merged = merge_generated_ideas(existing_ideas, auto_generated)
    actions: list[dict[str, str]] = []
    for path, payload in (
        (output_dir / "ideas" / "auto_generated.json", auto_generated),
        (output_dir / "ideas" / "review_queue.json", review_queue),
        (ideas_path, merged),
    ):
        existed = path.exists()
        write_json(path, payload)
        actions.append({"path": str(path), "action": "updated" if existed else "created"})
    return {
        "actions": actions,
        "generated_count": auto_generated["merge_summary"]["generated_count"],
        "new_count": auto_generated["merge_summary"]["new_count"],
    }

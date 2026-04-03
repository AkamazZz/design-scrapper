from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.project import (
    CANONICAL_COMPONENT_KINDS,
    load_optional_json,
    now_iso,
    read_json,
    screen_effect_profile,
    write_json,
)
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

SELECTED_SCREENS_SCHEMA_VERSION = "2.0.0"
DEFAULT_CONTRACT_VERSION = "1.0.0"
DEFAULT_LAYOUT = {
    "safe_area": True,
    "scroll": "vertical",
    "background_role": "surface.canvas",
    "padding_role": "screen.padding.horizontal",
}
DEFAULT_SCREEN_RULES = (
    "Use semantic roles instead of raw visual values.",
    "Favor one-thumb primary actions.",
    "Use inspirations and linked ideas as rationale, not as direct platform markup.",
)


@dataclass(frozen=True)
class BriefRecord:
    screen_id: str
    path: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class VariantRecord:
    screen_id: str
    variant_id: str
    path: str
    payload: dict[str, Any]
    selection_score: float
    critic_score: float | None
    effective_score: float
    score_source: str


def _required_json(path: Path, failure_code: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{failure_code}: missing file {path}")
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{failure_code}: expected object in {path}")
    return data


def _relative_path(path: Path, output_dir: Path) -> str:
    if path.is_absolute():
        try:
            return path.relative_to(output_dir).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _first_present(*values: Any) -> Any:
    for value in values:
        if _is_present(value):
            return value
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("overall_score", "critic_score", "final_score", "score", "value", "selection_score"):
            score = _coerce_float(value.get(key))
            if score is not None:
                return score
    return None


def _nested_get(value: Any, *path: str) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _merge_dicts(*values: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(value)
    return merged


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _dedupe_preserve_order(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    ordered: list[Any] = []
    for value in values:
        key = value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(value)
    return ordered


def _load_briefs(output_dir: Path) -> tuple[dict[str, Any], list[BriefRecord]]:
    index_payload = _required_json(output_dir / "screen_briefs" / "index.json", "screen_briefs_missing")
    brief_paths: dict[str, str] = {}
    for entry in index_payload.get("briefs", []):
        if not isinstance(entry, dict):
            continue
        screen_id = entry.get("screen_id")
        path = entry.get("path")
        if screen_id and isinstance(path, str) and path.strip():
            brief_paths[screen_id] = path

    ordered_screen_ids = [screen_id for screen_id in index_payload.get("screen_ids", []) if isinstance(screen_id, str) and screen_id]
    if not ordered_screen_ids:
        ordered_screen_ids = sorted(brief_paths)

    records: list[BriefRecord] = []
    seen_screen_ids: set[str] = set()
    for screen_id in ordered_screen_ids:
        relative_path = brief_paths.get(screen_id, f"screen_briefs/{screen_id}.json")
        path = output_dir / relative_path
        payload = _required_json(path, "screen_brief_missing")
        records.append(BriefRecord(screen_id=screen_id, path=relative_path, payload=payload))
        seen_screen_ids.add(screen_id)

    for path in sorted((output_dir / "screen_briefs").glob("*.json")):
        if path.name == "index.json":
            continue
        payload = _required_json(path, "screen_brief_missing")
        screen_id = payload.get("screen_id")
        if not isinstance(screen_id, str) or not screen_id or screen_id in seen_screen_ids:
            continue
        records.append(BriefRecord(screen_id=screen_id, path=_relative_path(path, output_dir), payload=payload))
        seen_screen_ids.add(screen_id)

    return index_payload, records


def _review_scores(output_dir: Path) -> dict[str, dict[str, Any]]:
    payload = load_optional_json(output_dir / "review" / "scores.json") or {}
    if not isinstance(payload, dict):
        return {}
    scores: dict[str, dict[str, Any]] = {}

    def add_score(variant_id: str, raw: Any) -> None:
        if not variant_id:
            return
        score = _coerce_float(raw)
        if score is None and isinstance(raw, dict):
            for key in ("critic_score", "overall_score", "final_score", "score"):
                score = _coerce_float(raw.get(key))
                if score is not None:
                    break
        if score is None:
            return
        scores[variant_id] = {
            "critic_score": score,
            "raw": raw if isinstance(raw, dict) else {"score": score},
        }

    for key in ("scores", "variants", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and isinstance(entry.get("variant_id"), str):
                    add_score(entry["variant_id"], entry)
        elif isinstance(value, dict):
            for variant_id, entry in value.items():
                if isinstance(variant_id, str):
                    add_score(variant_id, entry)

    if not scores:
        for variant_id, entry in payload.items():
            if variant_id in {"scores", "variants", "results", "items"} or not isinstance(variant_id, str):
                continue
            add_score(variant_id, entry)
    return scores


def _variant_index_entries(index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("variants", "records", "items", "screens"):
        value = index_payload.get(key)
        if isinstance(value, list):
            entries.extend(entry for entry in value if isinstance(entry, dict))
    return entries


def _iter_variant_candidates(output_dir: Path) -> list[tuple[dict[str, Any], str | None, Path | None]]:
    variants_dir = output_dir / "screen_variants"
    if not variants_dir.exists():
        raise FileNotFoundError(f"screen_variants_missing: missing directory {variants_dir}")

    candidates: list[tuple[dict[str, Any], str | None, Path | None]] = []
    index_payload = load_optional_json(variants_dir / "index.json") or {}
    if isinstance(index_payload, dict):
        for entry in _variant_index_entries(index_payload):
            relative_path = entry.get("path")
            if isinstance(relative_path, str) and relative_path.strip():
                path = output_dir / relative_path
                candidates.append((entry, relative_path, path))
            elif entry.get("variant_id"):
                candidates.append((entry, None, None))

    for path in sorted(variants_dir.rglob("*.json")):
        if path.name == "index.json":
            continue
        candidates.append(({}, _relative_path(path, output_dir), path))
    return candidates


def _infer_screen_id(path: Path | None, payload: dict[str, Any]) -> str | None:
    screen_id = payload.get("screen_id")
    if isinstance(screen_id, str) and screen_id:
        return screen_id
    if path is None:
        return None
    parent_name = path.parent.name
    if parent_name and parent_name != "screen_variants":
        return parent_name
    stem = path.stem
    if stem and stem != "index":
        return stem
    return None


def _infer_variant_id(path: Path | None, payload: dict[str, Any]) -> str | None:
    variant_id = payload.get("variant_id")
    if isinstance(variant_id, str) and variant_id:
        return variant_id
    if path is None:
        return None
    return path.stem if path.stem and path.stem != "index" else None


def _load_variants(output_dir: Path) -> dict[str, list[VariantRecord]]:
    review_scores = _review_scores(output_dir)
    grouped: dict[str, list[VariantRecord]] = {}
    seen_keys: set[tuple[str, str]] = set()
    for seed_payload, relative_path, path in _iter_variant_candidates(output_dir):
        payload = dict(seed_payload)
        if path is not None and path.exists():
            loaded = read_json(path)
            if not isinstance(loaded, dict):
                continue
            payload.update(loaded)
            relative_path = _relative_path(path, output_dir)

        screen_id = _infer_screen_id(path, payload)
        variant_id = _infer_variant_id(path, payload)
        if not screen_id or not variant_id:
            continue

        dedupe_key = (screen_id, variant_id)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        selection_score = _coerce_float(payload.get("selection_score"))
        if selection_score is None:
            selection_score = _coerce_float(seed_payload.get("selection_score")) or 0.0

        review_entry = review_scores.get(variant_id, {})
        critic_score = _coerce_float(payload.get("critic_score"))
        if critic_score is None:
            critic_score = _coerce_float(review_entry.get("critic_score"))

        score_source = "critic_score" if critic_score is not None else "selection_score"
        effective_score = critic_score if critic_score is not None else selection_score

        record = VariantRecord(
            screen_id=screen_id,
            variant_id=variant_id,
            path=relative_path or f"screen_variants/{screen_id}/{variant_id}.json",
            payload=payload,
            selection_score=selection_score,
            critic_score=critic_score,
            effective_score=effective_score,
            score_source=score_source,
        )
        grouped.setdefault(screen_id, []).append(record)
    return grouped


def _candidate_sort_key(candidate: VariantRecord) -> tuple[Any, ...]:
    return (
        -candidate.effective_score,
        0 if candidate.score_source == "critic_score" else 1,
        -candidate.selection_score,
        candidate.variant_id,
        candidate.path,
    )


def _winner_for_screen(candidates: list[VariantRecord]) -> VariantRecord:
    return sorted(candidates, key=_candidate_sort_key)[0]


def _variant_history(candidates: list[VariantRecord], selected_variant_id: str) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=_candidate_sort_key):
        history.append(
            {
                "variant_id": candidate.variant_id,
                "path": candidate.path,
                "selected": candidate.variant_id == selected_variant_id,
                "selection_score": candidate.selection_score,
                "critic_score": candidate.critic_score,
                "effective_score": candidate.effective_score,
                "score_source": candidate.score_source,
            }
        )
    return history


def _build_default_data_bindings(brief: dict[str, Any]) -> dict[str, Any]:
    bindings: dict[str, Any] = {}
    primary_data = _as_list(brief.get("primary_data"))
    secondary_data = _as_list(brief.get("secondary_data"))
    if primary_data:
        bindings["primary_data"] = primary_data
    if secondary_data:
        bindings["secondary_data"] = secondary_data
    return bindings


def _source_urls_from_evidence(source_evidence: list[Any]) -> list[str]:
    source_urls: list[str] = []
    for entry in source_evidence:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("source_url"), str) and entry["source_url"]:
            source_urls.append(entry["source_url"])
        for source_url in entry.get("source_urls", []):
            if isinstance(source_url, str) and source_url:
                source_urls.append(source_url)
    return _dedupe_preserve_order(source_urls)


def _scene_graph_components(scene_graph: Any) -> list[dict[str, Any]]:
    if not isinstance(scene_graph, dict):
        return []
    for key in ("components", "nodes", "elements", "layers"):
        value = scene_graph.get(key)
        if isinstance(value, list) and all(isinstance(entry, dict) for entry in value):
            return list(value)
    for key in ("regions", "children", "sections"):
        value = scene_graph.get(key)
        if not isinstance(value, list):
            continue
        components: list[dict[str, Any]] = []
        for entry in value:
            if isinstance(entry, dict):
                components.extend(_scene_graph_components(entry))
        if components:
            return components
    return []


def _proposal_alignment(
    brief: dict[str, Any],
    winner_payload: dict[str, Any],
    existing_screen: dict[str, Any],
    scene_graph: dict[str, Any],
) -> dict[str, Any]:
    direction_context = brief.get("direction_context", {}) if isinstance(brief.get("direction_context"), dict) else {}
    planning_context = brief.get("planning_context", {}) if isinstance(brief.get("planning_context"), dict) else {}
    return _merge_dicts(
        {
            "direction_id": direction_context.get("direction_id"),
            "direction_name": direction_context.get("direction_name"),
            "primary_motifs": _as_list(direction_context.get("primary_motifs")),
            "story": planning_context.get("story"),
            "motion_posture": direction_context.get("motion_posture"),
            "composition_principles": _as_list(direction_context.get("composition_principles")),
        },
        existing_screen.get("proposal_alignment"),
        scene_graph.get("proposal_alignment"),
        winner_payload.get("proposal_alignment"),
    )


def _motif_application(
    brief: dict[str, Any],
    winner_payload: dict[str, Any],
    existing_screen: dict[str, Any],
    scene_graph: dict[str, Any],
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_motif_application = existing_screen.get("motif_application") if isinstance(existing_screen.get("motif_application"), dict) else {}
    scene_graph_motif_application = scene_graph.get("motif_application") if isinstance(scene_graph.get("motif_application"), dict) else {}
    winner_motif_application = winner_payload.get("motif_application") if isinstance(winner_payload.get("motif_application"), dict) else {}
    proposal_motifs = _as_list(_nested_get(brief, "direction_context", "primary_motifs"))

    placement = _as_list(
        _first_present(
            existing_motif_application.get("placement"),
            scene_graph_motif_application.get("placement"),
            winner_motif_application.get("placement"),
            [],
        )
    )
    if not placement:
        scene_graph_placements = [
            {
                "component_id": entry.get("node_id"),
                "motif_id": entry.get("motif_id"),
                "purpose": entry.get("treatment"),
            }
            for entry in _as_list(scene_graph.get("motif_applications"))
            if isinstance(entry, dict) and entry.get("node_id") and entry.get("motif_id")
        ]
        placement = scene_graph_placements

    primary_motif = _first_present(
        existing_motif_application.get("primary_motif"),
        scene_graph_motif_application.get("primary_motif"),
        winner_motif_application.get("primary_motif"),
        placement[0].get("motif_id") if placement and isinstance(placement[0], dict) else None,
        proposal_motifs[0] if proposal_motifs else None,
    )
    secondary_motifs = _as_list(
        _first_present(
            existing_motif_application.get("secondary_motifs"),
            scene_graph_motif_application.get("secondary_motifs"),
            winner_motif_application.get("secondary_motifs"),
            proposal_motifs[1:],
        )
    )
    if not placement and primary_motif:
        first_component_id = next((component.get("id") for component in components if isinstance(component.get("id"), str) and component["id"]), None)
        if first_component_id:
            placement = [{"component_id": first_component_id, "motif_id": primary_motif, "purpose": "anchor_surface"}]
    return {
        "primary_motif": primary_motif,
        "secondary_motifs": secondary_motifs,
        "placement": placement,
    }


def _layout_payload(winner_payload: dict[str, Any], existing_screen: dict[str, Any], scene_graph: dict[str, Any]) -> dict[str, Any]:
    return _merge_dicts(DEFAULT_LAYOUT, existing_screen.get("layout"), scene_graph.get("layout"), winner_payload.get("layout"))


def _screen_payload(
    *,
    screen_id: str,
    brief_record: BriefRecord,
    candidates: list[VariantRecord],
    existing_screen: dict[str, Any],
    direction_id: str,
) -> dict[str, Any]:
    winner = _winner_for_screen(candidates)
    winner_payload = winner.payload
    brief = brief_record.payload
    scene_graph = winner_payload.get("scene_graph") if isinstance(winner_payload.get("scene_graph"), dict) else {}
    effect_profile = screen_effect_profile(direction_id or "calm_editorial", screen_id)
    components = _as_list(
        _first_present(
            existing_screen.get("components"),
            winner_payload.get("components"),
            scene_graph.get("components"),
            _scene_graph_components(scene_graph),
        )
    )
    proposal_alignment = _proposal_alignment(brief, winner_payload, existing_screen, scene_graph)
    source_evidence = _as_list(_first_present(winner_payload.get("source_evidence"), brief.get("source_evidence"), existing_screen.get("source_evidence"), []))
    data_bindings = _first_present(winner_payload.get("data_bindings"), existing_screen.get("data_bindings"), _build_default_data_bindings(brief), {})
    states = _as_list(_first_present(winner_payload.get("states"), existing_screen.get("states"), brief.get("required_states"), []))
    navigation_edges = _as_list(_first_present(winner_payload.get("navigation_edges"), brief.get("navigation_edges"), existing_screen.get("navigation_edges"), []))
    source_urls = _as_list(_first_present(winner_payload.get("source_urls"), existing_screen.get("source_urls"), _source_urls_from_evidence(source_evidence), []))
    payload = dict(existing_screen)
    payload.update(
        {
            "screen_id": screen_id,
            "route": _first_present(existing_screen.get("route"), winner_payload.get("route"), f"/{screen_id.replace('_', '-')}"),
            "purpose": _first_present(existing_screen.get("purpose"), brief.get("purpose"), winner_payload.get("purpose")),
            "jobs_to_be_done": _as_list(_first_present(existing_screen.get("jobs_to_be_done"), brief.get("jobs_to_be_done"), winner_payload.get("jobs_to_be_done"), [])),
            "layout_strategy": _first_present(
                existing_screen.get("layout_strategy"),
                winner_payload.get("layout_strategy"),
                scene_graph.get("layout_strategy"),
                _nested_get(scene_graph, "structure", "layout_strategy"),
                effect_profile.get("layout_strategy"),
                "selected_variant",
            ),
            "cta_posture": _first_present(
                existing_screen.get("cta_posture"),
                winner_payload.get("cta_posture"),
                scene_graph.get("cta_posture"),
                _nested_get(scene_graph, "structure", "cta_posture"),
                effect_profile.get("cta_posture"),
                "none",
            ),
            "chrome_density": _first_present(
                existing_screen.get("chrome_density"),
                winner_payload.get("chrome_density"),
                scene_graph.get("chrome_density"),
                _nested_get(scene_graph, "structure", "chrome_density"),
                effect_profile.get("chrome_density"),
                "medium",
            ),
            "card_usage": _first_present(
                existing_screen.get("card_usage"),
                winner_payload.get("card_usage"),
                scene_graph.get("card_usage"),
                _nested_get(scene_graph, "structure", "card_usage"),
                effect_profile.get("card_usage"),
                "supporting_modules",
            ),
            "layout": _layout_payload(winner_payload, existing_screen, scene_graph),
            "components": components,
            "data_bindings": data_bindings if isinstance(data_bindings, dict) else {},
            "states": states,
            "navigation_edges": navigation_edges,
            "source_evidence": source_evidence,
            "proposal_alignment": proposal_alignment,
            "motif_application": _motif_application(brief, winner_payload, existing_screen, scene_graph, components),
            "source_idea_ids": _as_list(_first_present(winner_payload.get("source_idea_ids"), brief.get("source_idea_ids"), existing_screen.get("source_idea_ids"), [])),
            "source_urls": source_urls,
            "selected_variant_id": winner.variant_id,
            "source_screen_brief": brief_record.path,
            "source_variant_path": winner.path,
            "selection_score": winner.selection_score,
            "selection_source": winner.score_source,
            "critic_score": winner.critic_score,
            "variant_history": _variant_history(candidates, winner.variant_id),
        }
    )
    return payload


def _screen_rules(existing_screens: dict[str, Any], brief_records: list[BriefRecord]) -> list[str]:
    existing_rules = existing_screens.get("screen_rules")
    if isinstance(existing_rules, list) and existing_rules:
        return existing_rules
    composition_principles: list[str] = []
    for record in brief_records:
        composition_principles.extend(_as_list(_nested_get(record.payload, "direction_context", "composition_principles")))
    return _dedupe_preserve_order([DEFAULT_SCREEN_RULES[0], DEFAULT_SCREEN_RULES[1], *composition_principles, DEFAULT_SCREEN_RULES[2]])


def publish_selected_screens(
    output_dir: Path,
    *,
    run_id: str,
    workspace_version: str = "v2",
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    generated_at = now_iso()
    brief_index, brief_records = _load_briefs(output_dir)
    if not brief_records:
        raise ValueError("screen_briefs_missing: no screen briefs were found")

    variants_by_screen = _load_variants(output_dir)
    if not variants_by_screen:
        raise ValueError("screen_variants_missing: no screen variants were found")

    existing_screens_payload = load_optional_json(output_dir / "screens" / "index.json") or {}
    existing_screens_lookup = {
        screen.get("screen_id"): screen
        for screen in existing_screens_payload.get("screens", [])
        if isinstance(screen, dict) and isinstance(screen.get("screen_id"), str)
    }

    contract_brief = load_optional_json(output_dir / "contract" / "brief.json") or {}
    inspirations = load_optional_json(output_dir / "inspirations" / "index.json") or {}
    proposal_visual = load_optional_json(output_dir / "proposal" / "visual_language.json") or {}
    proposal_typography = load_optional_json(output_dir / "proposal" / "typography_voice.json") or {}

    direction_id = (
        proposal_visual.get("direction_id")
        or brief_index.get("direction_id")
        or _nested_get(brief_records[0].payload, "direction_context", "direction_id")
        or _nested_get(existing_screens_payload, "proposal_context", "direction_id")
        or "calm_editorial"
    )
    direction_name = (
        proposal_visual.get("direction_name")
        or brief_index.get("direction_name")
        or _nested_get(brief_records[0].payload, "direction_context", "direction_name")
        or _nested_get(existing_screens_payload, "proposal_context", "direction_name")
    )
    voice_name = proposal_typography.get("voice_name") or _nested_get(existing_screens_payload, "proposal_context", "voice_name")

    published_screens: list[dict[str, Any]] = []
    missing_screen_ids: list[str] = []
    selected_variant_ids: dict[str, str] = {}
    selection_sources: dict[str, str] = {}
    for brief_record in brief_records:
        candidates = variants_by_screen.get(brief_record.screen_id, [])
        if not candidates:
            missing_screen_ids.append(brief_record.screen_id)
            continue
        screen_payload = _screen_payload(
            screen_id=brief_record.screen_id,
            brief_record=brief_record,
            candidates=candidates,
            existing_screen=existing_screens_lookup.get(brief_record.screen_id, {}),
            direction_id=direction_id,
        )
        published_screens.append(screen_payload)
        selected_variant_ids[brief_record.screen_id] = screen_payload["selected_variant_id"]
        selection_sources[brief_record.screen_id] = screen_payload["selection_source"]

    if not published_screens:
        raise ValueError("screen_variant_selection_failed: no screens could be published")

    status = "partial" if missing_screen_ids else "completed"
    metadata = build_artifact_version_metadata(
        phase="screen_variants",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=SELECTED_SCREENS_SCHEMA_VERSION,
        status=status,
    )
    metadata["publication_step"] = "selected_screens"

    screens_payload = {
        "contract_version": existing_screens_payload.get("contract_version", DEFAULT_CONTRACT_VERSION),
        "allowed_component_kinds": existing_screens_payload.get("allowed_component_kinds", list(CANONICAL_COMPONENT_KINDS)),
        "screen_rules": _screen_rules(existing_screens_payload, brief_records),
        "project": (
            existing_screens_payload.get("project")
            or brief_index.get("project")
            or _nested_get(contract_brief, "project", "name")
            or output_dir.name
        ),
        "inspiration_summary": existing_screens_payload.get("inspiration_summary", inspirations.get("summary", {})),
        "proposal_context": _merge_dicts(
            {
                "direction_id": direction_id,
                "direction_name": direction_name,
                "voice_name": voice_name,
                "screen_structure_phase": _nested_get(existing_screens_payload, "proposal_context", "screen_structure_phase") or "phase_4_selected_screens",
            },
            existing_screens_payload.get("proposal_context"),
            {"direction_id": direction_id, "direction_name": direction_name, "voice_name": voice_name},
        ),
        "metadata": metadata,
        "selection_summary": {
            "selected_screen_count": len(published_screens),
            "missing_screen_ids": missing_screen_ids,
            "selected_variant_ids": selected_variant_ids,
            "selection_sources": selection_sources,
        },
        "screens": published_screens,
    }

    screen_path = output_dir / "screens" / "index.json"
    existed = screen_path.exists()
    write_json(screen_path, screens_payload)
    return {
        "status": status,
        "actions": [{"path": str(screen_path), "action": "updated" if existed else "created"}],
        "screen_count": len(published_screens),
        "screen_ids": [screen["screen_id"] for screen in published_screens],
        "missing_screen_ids": missing_screen_ids,
        "selected_variant_ids": selected_variant_ids,
        "selection_sources": selection_sources,
    }

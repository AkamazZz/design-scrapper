from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from mobile_design_orchestrator.project import now_iso, read_json, slugify
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

REVIEW_SCHEMA_VERSION = "0.1.0"
PREVIEW_RENDERER_VERSION = "deterministic_text_preview_v1"

_VARIANT_LIST_KEYS = ("variants", "screen_variants", "records")
_TEXT_FIELDS = ("content", "label", "title", "subtitle", "value", "caption", "placeholder", "name", "text")
_CONTEXT_MERGE_KEYS = ("brief", "screen_brief", "source_brief", "direction_context", "proposal_alignment", "motif_application")
_INTERACTIVE_KINDS = {"button", "toggle", "checkbox", "radio", "chip", "tab_bar", "nav_bar", "text_field", "secure_field"}
_MEDIA_KINDS = {"image", "icon", "avatar"}
_HEADLINE_ROLE_TOKENS = ("headline", "title", "hero", "heading")


def review_artifact_envelope(
    *,
    project: str,
    artifact_type: str,
    generated_at: str,
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "project": project,
        "artifact_type": artifact_type,
        "generated_at": generated_at,
        "record_count": len(records),
        "metadata": metadata,
        "records": records,
    }
    if summary is not None:
        payload["summary"] = summary
    return payload


def discover_variant_files(screen_variants_dir: Path) -> list[Path]:
    if not screen_variants_dir.exists():
        raise FileNotFoundError(f"Missing screen variants directory: {screen_variants_dir}")
    return sorted(path for path in screen_variants_dir.rglob("*.json") if path.is_file())


def load_review_variants(screen_variants_dir: Path) -> list[dict[str, Any]]:
    screen_variants_dir = screen_variants_dir.resolve()
    records: list[dict[str, Any]] = []
    for source_path in discover_variant_files(screen_variants_dir):
        try:
            payload = read_json(source_path)
        except Exception as exc:  # pragma: no cover - surfaced directly to the caller
            raise ValueError(f"Failed to read JSON from {source_path}: {exc}") from exc
        source_ref = str(source_path.relative_to(screen_variants_dir))
        records.extend(_extract_variants(payload, source_ref))
    records.sort(key=lambda item: (item["screen_id"], item["variant_id"], item["source_path"], item["variant_index"]))
    return records


def component_text(component: Mapping[str, Any]) -> str:
    fragments: list[str] = []
    for field in _TEXT_FIELDS:
        value = component.get(field)
        if isinstance(value, str) and value.strip():
            fragments.append(value.strip())
    items = component.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str) and item.strip():
                fragments.append(item.strip())
            elif isinstance(item, Mapping):
                for field in _TEXT_FIELDS:
                    value = item.get(field)
                    if isinstance(value, str) and value.strip():
                        fragments.append(value.strip())
    return " | ".join(fragments)


def tokenize_text(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        tokens: set[str] = set()
        for item in value:
            tokens.update(tokenize_text(item))
        return tokens
    if isinstance(value, Mapping):
        tokens: set[str] = set()
        for item in value.values():
            tokens.update(tokenize_text(item))
        return tokens
    return set(re.findall(r"[a-z0-9]{3,}", str(value).lower()))


def build_variant_preview(variant: Mapping[str, Any], *, max_components: int = 8) -> dict[str, Any]:
    components = [component for component in variant.get("components", []) if isinstance(component, Mapping)]
    lines = [
        f"{variant.get('screen_title', 'Untitled Screen')} [{variant.get('screen_id', 'screen')}]",
        (
            f"layout={variant.get('layout_strategy', 'unspecified')} | "
            f"cta={variant.get('cta_posture', 'unspecified')} | "
            f"density={variant.get('chrome_density', 'unspecified')} | "
            f"cards={variant.get('card_usage', 'unspecified')}"
        ),
    ]
    purpose = variant.get("purpose")
    if purpose:
        lines.append(f"purpose={purpose}")
    primary_motif = (variant.get("motif_application") or {}).get("primary_motif")
    if primary_motif:
        lines.append(f"motif={primary_motif}")
    for index, component in enumerate(components[:max_components], start=1):
        lines.append(f"{index:02d}. {_component_preview_line(component)}")
    if len(components) > max_components:
        lines.append(f"... +{len(components) - max_components} more components")
    return {
        "renderer": PREVIEW_RENDERER_VERSION,
        "variant_key": variant.get("variant_key"),
        "line_count": len(lines),
        "component_excerpt_count": min(len(components), max_components),
        "component_total": len(components),
        "lines": lines,
    }


def build_review_summary_artifact(
    variants: Iterable[Mapping[str, Any]],
    scores: Iterable[Mapping[str, Any]],
    *,
    project: str,
    source_dir: Path,
    generated_at: str | None = None,
    run_id: str = "manual",
    workspace_version: str = "v2",
) -> dict[str, Any]:
    generated_at = generated_at or now_iso()
    variants_list = [dict(variant) for variant in variants]
    score_lookup = {str(score.get("variant_key")): dict(score) for score in scores}
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for variant in variants_list:
        grouped[variant["screen_id"]].append(variant)

    records: list[dict[str, Any]] = []
    screen_order = sorted(grouped)
    for screen_id in screen_order:
        ranked = sorted(
            grouped[screen_id],
            key=lambda item: (
                -_score_value(score_lookup.get(item["variant_key"])),
                item.get("variant_name", ""),
                item["variant_id"],
            ),
        )
        for rank, variant in enumerate(ranked, start=1):
            score = score_lookup.get(variant["variant_key"], {})
            preview = build_variant_preview(variant)
            records.append(
                {
                    "screen_id": variant["screen_id"],
                    "screen_title": variant.get("screen_title"),
                    "variant_id": variant["variant_id"],
                    "variant_name": variant.get("variant_name"),
                    "variant_key": variant["variant_key"],
                    "source_path": variant["source_path"],
                    "rank_within_screen": rank,
                    "overall_score": _score_value(score),
                    "dimension_scores": {
                        name: _score_value((score.get("dimensions") or {}).get(name))
                        for name in ("direction_fit", "hierarchy_clarity", "density", "task_fit")
                    },
                    "structure": {
                        "layout_strategy": variant.get("layout_strategy"),
                        "cta_posture": variant.get("cta_posture"),
                        "chrome_density": variant.get("chrome_density"),
                        "card_usage": variant.get("card_usage"),
                    },
                    "measurements": dict(variant.get("measurements", {})),
                    "preview": preview,
                    "highlights": _collect_dimension_notes(score, "signals"),
                    "concerns": _collect_dimension_notes(score, "issues"),
                }
            )

    overview = {
        "screen_count": len(screen_order),
        "variant_count": len(records),
        "source_file_count": len({record["source_path"] for record in records}),
        "average_overall_score": _average(record["overall_score"] for record in records),
        "average_dimension_scores": {
            name: _average(record["dimension_scores"].get(name, 0) for record in records)
            for name in ("direction_fit", "hierarchy_clarity", "density", "task_fit")
        },
    }
    metadata = build_artifact_version_metadata(
        phase="critic",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=REVIEW_SCHEMA_VERSION,
    )
    metadata.update(
        {
            "source_dir": str(source_dir),
            "renderer_version": PREVIEW_RENDERER_VERSION,
        }
    )
    return review_artifact_envelope(
        project=project,
        artifact_type="review_summary",
        generated_at=generated_at,
        records=records,
        metadata=metadata,
        summary=overview,
    )


def render_review_summary_markdown(summary_artifact: Mapping[str, Any]) -> str:
    summary = summary_artifact.get("summary", {})
    records = [record for record in summary_artifact.get("records", []) if isinstance(record, Mapping)]
    lines = [
        "# Review Summary",
        "",
        f"- Project: `{summary_artifact.get('project', 'mobile-project')}`",
        f"- Generated: `{summary_artifact.get('generated_at', '')}`",
        f"- Variants: `{summary.get('variant_count', 0)}` across `{summary.get('screen_count', 0)}` screens",
        f"- Average overall score: `{summary.get('average_overall_score', 0)}/100`",
        "",
    ]
    if not records:
        lines.extend(
            [
                "No screen variants were found under the input directory.",
                "",
                "Add JSON artifacts under `screen_variants/` and rerun this renderer.",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    grouped: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("screen_id", "screen"))].append(record)

    for screen_id in sorted(grouped):
        screen_records = sorted(grouped[screen_id], key=lambda item: (item.get("rank_within_screen", 999), -int(item.get("overall_score", 0))))
        lines.append(f"## {screen_records[0].get('screen_title') or _display_name(screen_id)}")
        lines.append("")
        for record in screen_records:
            lines.append(
                f"### {record.get('variant_name') or record.get('variant_id')} · {record.get('overall_score', 0)}/100"
            )
            lines.append(
                "- "
                + " | ".join(
                    [
                        f"direction_fit={record.get('dimension_scores', {}).get('direction_fit', 0)}",
                        f"hierarchy_clarity={record.get('dimension_scores', {}).get('hierarchy_clarity', 0)}",
                        f"density={record.get('dimension_scores', {}).get('density', 0)}",
                        f"task_fit={record.get('dimension_scores', {}).get('task_fit', 0)}",
                    ]
                )
            )
            structure = record.get("structure", {})
            lines.append(
                "- "
                + " | ".join(
                    [
                        f"layout=`{structure.get('layout_strategy') or 'unspecified'}`",
                        f"cta=`{structure.get('cta_posture') or 'unspecified'}`",
                        f"density=`{structure.get('chrome_density') or 'unspecified'}`",
                        f"cards=`{structure.get('card_usage') or 'unspecified'}`",
                    ]
                )
            )
            for highlight in record.get("highlights", [])[:2]:
                lines.append(f"- Highlight: {highlight}")
            for concern in record.get("concerns", [])[:2]:
                lines.append(f"- Concern: {concern}")
            lines.append("```text")
            lines.extend(record.get("preview", {}).get("lines", []))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def infer_project_slug(source_dir: Path, explicit_project: str | None = None) -> str:
    if explicit_project:
        return slugify(explicit_project)
    if source_dir.name == "screen_variants":
        return slugify(source_dir.parent.name)
    return slugify(source_dir.name)


def _extract_variants(payload: Any, source_ref: str) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            if isinstance(item, Mapping):
                nested = _extract_variants(item, source_ref)
                if nested:
                    extracted.extend(nested)
                elif _looks_like_variant(item):
                    extracted.append(_normalize_variant(item, source_ref=source_ref, variant_index=index))
        return extracted

    if not isinstance(payload, Mapping):
        return extracted

    screens = payload.get("screens")
    if isinstance(screens, list):
        for screen_index, screen in enumerate(screens):
            if not isinstance(screen, Mapping):
                continue
            members = _variant_members(screen)
            if members:
                for variant_index, member in enumerate(members):
                    merged = _merge_context(screen, member)
                    extracted.append(_normalize_variant(merged, source_ref=source_ref, variant_index=variant_index))
            elif _looks_like_variant(screen):
                extracted.append(_normalize_variant(screen, source_ref=source_ref, variant_index=screen_index))
        if extracted:
            return extracted

    members = _variant_members(payload)
    if members:
        for variant_index, member in enumerate(members):
            merged = _merge_context(payload, member)
            extracted.append(_normalize_variant(merged, source_ref=source_ref, variant_index=variant_index))
        return extracted

    if _looks_like_variant(payload):
        extracted.append(_normalize_variant(payload, source_ref=source_ref, variant_index=0))
    return extracted


def _variant_members(container: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    members: list[Mapping[str, Any]] = []
    for key in _VARIANT_LIST_KEYS:
        value = container.get(key)
        if isinstance(value, list):
            members.extend(item for item in value if isinstance(item, Mapping))
        elif isinstance(value, Mapping):
            for screen_id in sorted(value):
                mapped = value[screen_id]
                if isinstance(mapped, list):
                    for item in mapped:
                        if isinstance(item, Mapping):
                            enriched = dict(item)
                            enriched.setdefault("screen_id", screen_id)
                            members.append(enriched)
                elif isinstance(mapped, Mapping):
                    enriched = dict(mapped)
                    enriched.setdefault("screen_id", screen_id)
                    members.append(enriched)
    return members


def _looks_like_variant(candidate: Mapping[str, Any]) -> bool:
    return any(
        key in candidate
        for key in (
            "screen_id",
            "variant_id",
            "components",
            "scene_graph",
            "layout_strategy",
            "cta_posture",
            "chrome_density",
            "card_usage",
            "brief",
            "screen_brief",
        )
    )


def _merge_context(parent: Mapping[str, Any], child: Mapping[str, Any]) -> dict[str, Any]:
    merged = {key: value for key, value in parent.items() if key not in _VARIANT_LIST_KEYS and key != "screens"}
    for key, value in child.items():
        if key in _CONTEXT_MERGE_KEYS and isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _normalize_variant(record: Mapping[str, Any], *, source_ref: str, variant_index: int) -> dict[str, Any]:
    brief = _variant_brief(record)
    screen_id = _first_present(
        record.get("screen_id"),
        record.get("screen"),
        brief.get("screen_id"),
        f"screen-{variant_index + 1}",
    )
    screen_id = slugify(str(screen_id))
    variant_name = _first_present(record.get("variant_name"), record.get("name"), record.get("title"), record.get("variant_id"))
    variant_id = slugify(str(_first_present(record.get("variant_id"), variant_name, f"{screen_id}-v{variant_index + 1}")))
    screen_title = _first_present(record.get("screen_title"), brief.get("title"), record.get("title"), _display_name(screen_id))
    components = _extract_components(record)
    text_fragments = [component_text(component) for component in components if component_text(component)]
    normalized = {
        "screen_id": screen_id,
        "screen_title": str(screen_title),
        "variant_id": variant_id,
        "variant_name": str(_first_present(variant_name, variant_id)),
        "variant_key": f"{screen_id}::{variant_id}",
        "variant_index": variant_index,
        "source_path": source_ref,
        "layout_strategy": _string_or_default(record.get("layout_strategy")),
        "cta_posture": _string_or_default(record.get("cta_posture")),
        "chrome_density": _string_or_default(record.get("chrome_density")),
        "card_usage": _string_or_default(record.get("card_usage")),
        "motif_application": dict(record.get("motif_application", {})) if isinstance(record.get("motif_application"), Mapping) else {},
        "proposal_alignment": dict(record.get("proposal_alignment", {})) if isinstance(record.get("proposal_alignment"), Mapping) else {},
        "direction_context": _direction_context(record, brief),
        "purpose": _first_present(record.get("purpose"), brief.get("purpose")),
        "jobs_to_be_done": _string_list(_first_present(record.get("jobs_to_be_done"), brief.get("jobs_to_be_done"), [])),
        "primary_data": _string_list(_first_present(record.get("primary_data"), brief.get("primary_data"), [])),
        "secondary_data": _string_list(_first_present(record.get("secondary_data"), brief.get("secondary_data"), [])),
        "required_states": _string_list(_first_present(record.get("required_states"), brief.get("required_states"), [])),
        "navigation_edges": _dict_list(_first_present(record.get("navigation_edges"), brief.get("navigation_edges"), [])),
        "components": components,
        "text_fragments": text_fragments,
    }
    normalized["measurements"] = _variant_measurements(normalized)
    return normalized


def _variant_brief(record: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("brief", "screen_brief", "source_brief"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _direction_context(record: Mapping[str, Any], brief: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for source in (brief.get("direction_context"), record.get("direction_context"), record.get("proposal_alignment")):
        if isinstance(source, Mapping):
            context.update(source)
    return context


def _extract_components(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    components = record.get("components")
    if isinstance(components, list):
        return [
            _normalize_component(component, path=str(index), depth=0)
            for index, component in enumerate(components)
            if isinstance(component, Mapping)
        ]
    scene_graph = record.get("scene_graph")
    if isinstance(scene_graph, Mapping):
        return _flatten_scene_graph(scene_graph)
    return []


def _flatten_scene_graph(scene_graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def walk(node: Mapping[str, Any], *, path: str, depth: int) -> None:
        normalized = _normalize_component(node, path=path, depth=depth)
        if normalized["kind"] not in {"root", "screen", "scene"} or normalized["semantic_role"] or component_text(normalized):
            nodes.append(normalized)
        children = _node_children(node)
        for index, child in enumerate(children):
            walk(child, path=f"{path}.{index}", depth=depth + 1)

    root = scene_graph.get("root")
    if isinstance(root, Mapping):
        walk(root, path="0", depth=0)
    else:
        walked = False
        for index, node in enumerate(_node_children(scene_graph)):
            walked = True
            walk(node, path=str(index), depth=0)
        if not walked:
            walk(scene_graph, path="0", depth=0)
    return nodes


def _node_children(node: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    children: list[Mapping[str, Any]] = []
    for key in ("children", "nodes", "components"):
        value = node.get(key)
        if isinstance(value, list):
            children.extend(item for item in value if isinstance(item, Mapping))
    return children


def _normalize_component(component: Mapping[str, Any], *, path: str, depth: int) -> dict[str, Any]:
    kind = _first_present(component.get("kind"), component.get("node_type"), component.get("type"), "container")
    semantic_role = _first_present(component.get("semantic_role"), component.get("role"))
    normalized = {
        "id": _first_present(component.get("id"), component.get("node_id"), component.get("component_id"), f"node-{path}"),
        "kind": slugify(str(kind)).replace("-", "_"),
        "semantic_role": semantic_role,
        "content": component.get("content"),
        "label": component.get("label"),
        "title": component.get("title"),
        "subtitle": component.get("subtitle"),
        "items": component.get("items"),
        "depth": depth,
        "path": path,
    }
    return normalized


def _variant_measurements(variant: Mapping[str, Any]) -> dict[str, Any]:
    components = [component for component in variant.get("components", []) if isinstance(component, Mapping)]
    texts = [component_text(component) for component in components]
    primary_button_index = next(
        (
            index
            for index, component in enumerate(components)
            if component.get("semantic_role") == "button.primary"
        ),
        None,
    )
    headline_count = sum(1 for component in components if _is_headline_component(component))
    unique_roles = sorted(
        {
            str(component.get("semantic_role"))
            for component in components
            if component.get("semantic_role")
        }
    )
    measurements = {
        "component_count": len(components),
        "text_component_count": sum(1 for component in components if component.get("kind") == "text"),
        "text_word_count": sum(len(re.findall(r"[a-z0-9]+", text.lower())) for text in texts if text),
        "interactive_count": sum(1 for component in components if component.get("kind") in _INTERACTIVE_KINDS),
        "media_count": sum(1 for component in components if component.get("kind") in _MEDIA_KINDS),
        "card_count": sum(1 for component in components if component.get("kind") == "card"),
        "list_count": sum(1 for component in components if component.get("kind") in {"list", "list_item"}),
        "progress_count": sum(1 for component in components if component.get("kind") == "progress"),
        "navigation_count": sum(1 for component in components if component.get("kind") in {"tab_bar", "nav_bar"}),
        "form_count": sum(1 for component in components if component.get("kind") in {"text_field", "secure_field", "toggle", "checkbox", "radio"}),
        "primary_button_count": sum(1 for component in components if component.get("semantic_role") == "button.primary"),
        "primary_button_index": primary_button_index,
        "headline_count": headline_count,
        "text_role_count": sum(
            1
            for role in unique_roles
            if any(token in role.lower() for token in _HEADLINE_ROLE_TOKENS) or role.lower().startswith("text.")
        ),
        "unique_kind_count": len({component.get("kind") for component in components if component.get("kind")}),
        "unique_role_count": len(unique_roles),
    }
    return measurements


def _component_preview_line(component: Mapping[str, Any]) -> str:
    role = component.get("semantic_role")
    kind = component.get("kind", "component")
    text = component_text(component)
    label = role or kind
    if text:
        snippet = text.replace("\n", " ").strip()
        if len(snippet) > 72:
            snippet = snippet[:69].rstrip() + "..."
        return f"{label} ({kind}) :: {snippet}"
    return f"{label} ({kind})"


def _collect_dimension_notes(score: Mapping[str, Any], field: str) -> list[str]:
    notes: list[str] = []
    dimensions = score.get("dimensions", {})
    if not isinstance(dimensions, Mapping):
        return notes
    for dimension in ("direction_fit", "hierarchy_clarity", "density", "task_fit"):
        detail = dimensions.get(dimension, {})
        if not isinstance(detail, Mapping):
            continue
        for note in detail.get(field, []):
            if isinstance(note, str) and note not in notes:
                notes.append(note)
    return notes


def _score_value(score_or_dimension: Mapping[str, Any] | None) -> int:
    if not isinstance(score_or_dimension, Mapping):
        return 0
    overall = score_or_dimension.get("overall")
    if isinstance(overall, Mapping):
        return int(overall.get("score", 0))
    return int(score_or_dimension.get("score", 0))


def _average(values: Iterable[object]) -> int:
    numbers = [int(value) for value in values]
    if not numbers:
        return 0
    return int(round(sum(numbers) / len(numbers)))


def _first_present(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value.strip()
            continue
        return value
    return ""


def _string_or_default(value: object, default: str = "unspecified") -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _is_headline_component(component: Mapping[str, Any]) -> bool:
    role = str(component.get("semantic_role") or "").lower()
    if any(token in role for token in _HEADLINE_ROLE_TOKENS):
        return True
    text = component_text(component)
    if component.get("kind") == "text" and 2 <= len(tokenize_text(text)) <= 10:
        return True
    return False


def _display_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SCENE_GRAPH_SCHEMA_VERSION = "2.0.0"


@dataclass(frozen=True)
class VariantBlueprint:
    key: str
    label: str
    layout_family: str
    density: str
    emphasis: str
    sections: tuple[str, ...]
    primary_limit: int = 1
    secondary_limit: int = 2
    action_source: str = "jobs"
    navigation_mode: str = "tabs"
    evidence_limit: int = 2
    critic_focus: tuple[str, ...] = ()
    base_score: float = 0.9


@dataclass(frozen=True)
class SceneNode:
    node_id: str
    kind: str
    role: str
    label: str
    children: tuple[str, ...] = ()
    binding_ids: tuple[str, ...] = ()
    state_tags: tuple[str, ...] = ()
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_id": self.node_id,
            "kind": self.kind,
            "role": self.role,
            "label": self.label,
        }
        if self.children:
            payload["children"] = list(self.children)
        if self.binding_ids:
            payload["binding_ids"] = list(self.binding_ids)
        if self.state_tags:
            payload["state_tags"] = list(self.state_tags)
        if self.props:
            payload["props"] = dict(self.props)
        return payload


@dataclass(frozen=True)
class SceneGraph:
    graph_id: str
    root_id: str
    layout: dict[str, Any]
    nodes: tuple[SceneNode, ...]
    motif_applications: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCENE_GRAPH_SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "root_id": self.root_id,
            "layout": dict(self.layout),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": self._edges(),
            "motif_applications": [dict(item) for item in self.motif_applications],
        }

    def _edges(self) -> list[dict[str, str]]:
        edges: list[dict[str, str]] = []
        for node in self.nodes:
            for child_id in node.children:
                edges.append({"from": node.node_id, "relation": "contains", "to": child_id})
        return edges


@dataclass(frozen=True)
class SceneBuildResult:
    scene_graph: SceneGraph
    data_bindings: tuple[dict[str, Any], ...]
    focus_node_ids: tuple[str, ...]
    section_node_ids: dict[str, str]


def build_variant_scene(
    brief: Mapping[str, Any],
    blueprint: VariantBlueprint,
    *,
    variant_id: str,
    lineage: Mapping[str, Any],
) -> SceneBuildResult:
    prefix = _slugify(variant_id)
    primary_specs = _binding_specs(brief.get("primary_data", []), priority="primary")
    secondary_specs = _binding_specs(brief.get("secondary_data", []), priority="secondary")
    navigation_edges = _navigation_specs(brief.get("navigation_edges", []))
    evidence_refs = _evidence_specs(lineage.get("evidence_refs", []))
    jobs = [str(item).strip() for item in brief.get("jobs_to_be_done", []) if str(item).strip()]
    states = [str(item).strip() for item in brief.get("required_states", []) if str(item).strip()]
    motifs = [str(item).strip() for item in (brief.get("direction_context", {}) or {}).get("primary_motifs", []) if str(item).strip()]
    title = str(brief.get("title") or _humanize_token(str(brief.get("screen_id") or "screen")))
    purpose_label = _humanize_token(str(brief.get("purpose") or "mobile_flow_step"))
    direction_name = str((brief.get("direction_context", {}) or {}).get("direction_name") or "Mobile direction")
    story = str((brief.get("planning_context", {}) or {}).get("story") or "")

    root_id = _node_id(prefix, "root")
    safe_area_id = _node_id(prefix, "safe_area")
    scroll_id = _node_id(prefix, "scroll")
    child_section_ids: list[str] = []
    nodes: list[SceneNode] = []
    section_node_ids: dict[str, str] = {}
    data_bindings: list[dict[str, Any]] = []
    focus_node_ids: list[str] = []
    motif_applications: list[dict[str, Any]] = []

    remaining_primary = list(primary_specs)
    remaining_secondary = list(secondary_specs)
    evidence_queue = list(evidence_refs)
    navigation_queue = list(navigation_edges)

    def take(pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
        if count <= 0:
            return []
        taken = pool[:count]
        del pool[: len(taken)]
        return taken

    def append_section(name: str, section_nodes: Sequence[SceneNode], *, focus: bool = False, motif_role: str | None = None) -> None:
        if not section_nodes:
            return
        section_id = section_nodes[0].node_id
        section_node_ids[name] = section_id
        child_section_ids.append(section_id)
        nodes.extend(section_nodes)
        if focus:
            focus_node_ids.append(section_id)
        if motif_role and motifs:
            motif_id = motifs[min(len(motif_applications), len(motifs) - 1)]
            motif_applications.append({"motif_id": motif_id, "node_id": section_id, "treatment": motif_role})

    for section_name in blueprint.sections:
        if section_name == "header":
            append_section(
                "header",
                _build_header_section(
                    prefix=prefix,
                    title=title,
                    purpose_label=purpose_label,
                    direction_name=direction_name,
                    story=story,
                    motifs=motifs,
                ),
                focus=blueprint.emphasis == "orientation",
                motif_role="context",
            )
            continue
        if section_name == "hero":
            hero_specs = take(remaining_primary, blueprint.primary_limit)
            if not hero_specs:
                hero_specs = take(remaining_secondary, 1)
            append_section(
                "hero",
                _build_binding_section(
                    prefix=prefix,
                    section_name="hero",
                    label="Hero",
                    specs=hero_specs,
                    data_bindings=data_bindings,
                    kind="card",
                    role="section.hero",
                    presentation="hero_stack",
                    summary=story or _first(jobs) or direction_name,
                ),
                focus=blueprint.emphasis in {"primary_data", "actions", "evidence"},
                motif_role="anchor",
            )
            continue
        if section_name == "action_strip":
            action_items = _action_items(
                jobs=jobs,
                navigation=navigation_edges,
                source=blueprint.action_source,
            )
            append_section(
                "action_strip",
                _build_action_section(prefix=prefix, section_name="action_strip", items=action_items),
                focus=blueprint.emphasis == "actions",
                motif_role="action",
            )
            continue
        if section_name == "primary_list":
            append_section(
                "primary_list",
                _build_binding_section(
                    prefix=prefix,
                    section_name="primary_list",
                    label="Primary content",
                    specs=take(remaining_primary, max(len(remaining_primary), 1)),
                    data_bindings=data_bindings,
                    kind="list_item",
                    role="section.primary_list",
                    presentation="segmented_list",
                ),
                motif_role="support",
            )
            continue
        if section_name == "secondary_grid":
            append_section(
                "secondary_grid",
                _build_binding_section(
                    prefix=prefix,
                    section_name="secondary_grid",
                    label="Supporting modules",
                    specs=take(remaining_secondary, blueprint.secondary_limit),
                    data_bindings=data_bindings,
                    kind="card",
                    role="section.secondary_grid",
                    presentation="compact_grid",
                ),
                motif_role="support",
            )
            continue
        if section_name == "secondary_list":
            append_section(
                "secondary_list",
                _build_binding_section(
                    prefix=prefix,
                    section_name="secondary_list",
                    label="Supporting context",
                    specs=take(remaining_secondary, max(blueprint.secondary_limit, len(remaining_secondary))),
                    data_bindings=data_bindings,
                    kind="list_item",
                    role="section.secondary_list",
                    presentation="stacked_list",
                ),
                motif_role="support",
            )
            continue
        if section_name == "navigation":
            nav_specs = take(navigation_queue, max(len(navigation_queue), 1))
            if not nav_specs and navigation_edges:
                nav_specs = list(navigation_edges)
            nav_binding_specs = take(remaining_primary, min(len(remaining_primary), max(len(nav_specs), 1)))
            append_section(
                "navigation",
                _build_navigation_section(
                    prefix=prefix,
                    navigation_specs=nav_specs,
                    mode=blueprint.navigation_mode,
                    binding_specs=nav_binding_specs,
                    data_bindings=data_bindings,
                ),
                focus=blueprint.emphasis == "orientation",
                motif_role="navigation",
            )
            continue
        if section_name == "status":
            append_section(
                "status",
                _build_status_section(prefix=prefix, states=states, motifs=motifs),
                motif_role="status",
            )
            continue
        if section_name == "evidence":
            append_section(
                "evidence",
                _build_evidence_section(
                    prefix=prefix,
                    evidence_specs=take(evidence_queue, blueprint.evidence_limit),
                ),
                focus=blueprint.emphasis == "evidence",
                motif_role="evidence",
            )

    nodes.extend(
        [
            SceneNode(
                node_id=root_id,
                kind="container",
                role="screen.root",
                label=title,
                children=(safe_area_id,),
                props={
                    "screen_id": brief.get("screen_id"),
                    "variant_id": variant_id,
                },
            ),
            SceneNode(
                node_id=safe_area_id,
                kind="container",
                role="layout.safe_area",
                label="Safe area",
                children=(scroll_id,),
                props={"safe_area": True},
            ),
            SceneNode(
                node_id=scroll_id,
                kind="stack",
                role="layout.scroll_stack",
                label="Scroll stack",
                children=tuple(child_section_ids),
                props={
                    "axis": "vertical",
                    "scroll": "vertical",
                    "section_count": len(child_section_ids),
                },
            ),
        ]
    )
    ordered_nodes = _sort_nodes(nodes, root_id=root_id, safe_area_id=safe_area_id, scroll_id=scroll_id)
    graph = SceneGraph(
        graph_id=f"{variant_id}::scene",
        root_id=root_id,
        layout={
            "layout_family": blueprint.layout_family,
            "density": blueprint.density,
            "emphasis": blueprint.emphasis,
            "safe_area": True,
            "scroll": "vertical",
            "section_order": [name for name in blueprint.sections if name in section_node_ids],
        },
        nodes=tuple(ordered_nodes),
        motif_applications=tuple(motif_applications),
    )
    return SceneBuildResult(
        scene_graph=graph,
        data_bindings=tuple(data_bindings),
        focus_node_ids=tuple(node_id for node_id in (focus_node_ids or [section_node_ids.get("header")]) if node_id),
        section_node_ids=section_node_ids,
    )


def _sort_nodes(nodes: Sequence[SceneNode], *, root_id: str, safe_area_id: str, scroll_id: str) -> list[SceneNode]:
    priority = {root_id: 0, safe_area_id: 1, scroll_id: 2}
    return sorted(nodes, key=lambda node: (priority.get(node.node_id, 99), node.node_id))


def _build_header_section(
    *,
    prefix: str,
    title: str,
    purpose_label: str,
    direction_name: str,
    story: str,
    motifs: Sequence[str],
) -> list[SceneNode]:
    header_id = _node_id(prefix, "header")
    title_id = _node_id(prefix, "header", "title")
    purpose_id = _node_id(prefix, "header", "purpose")
    direction_id = _node_id(prefix, "header", "direction")
    child_ids = [title_id, purpose_id, direction_id]
    nodes = [
        SceneNode(
            node_id=header_id,
            kind="container",
            role="section.header",
            label="Header",
            children=tuple(child_ids),
            props={"presentation": "top_stack"},
        ),
        SceneNode(
            node_id=title_id,
            kind="text",
            role="content.title",
            label=title,
            props={"semantic_role": "app.title"},
        ),
        SceneNode(
            node_id=purpose_id,
            kind="chip",
            role="content.purpose",
            label=purpose_label,
            props={"semantic_role": "screen.purpose"},
        ),
        SceneNode(
            node_id=direction_id,
            kind="badge",
            role="content.direction",
            label=direction_name,
            props={"semantic_role": "screen.direction"},
        ),
    ]
    if story:
        story_id = _node_id(prefix, "header", "story")
        child_ids.append(story_id)
        nodes[0] = SceneNode(
            node_id=header_id,
            kind="container",
            role="section.header",
            label="Header",
            children=tuple(child_ids),
            props={"presentation": "top_stack"},
        )
        nodes.append(
            SceneNode(
                node_id=story_id,
                kind="text",
                role="content.story",
                label=story,
                props={"semantic_role": "app.caption"},
            )
        )
    for index, motif in enumerate(motifs[:2], start=1):
        motif_id = _node_id(prefix, "header", "motif", f"{index:02d}")
        child_ids.append(motif_id)
        nodes[0] = SceneNode(
            node_id=header_id,
            kind="container",
            role="section.header",
            label="Header",
            children=tuple(child_ids),
            props={"presentation": "top_stack"},
        )
        nodes.append(
            SceneNode(
                node_id=motif_id,
                kind="chip",
                role="content.motif",
                label=_humanize_token(motif),
                props={"motif_id": motif},
            )
        )
    return nodes


def _build_binding_section(
    *,
    prefix: str,
    section_name: str,
    label: str,
    specs: Sequence[dict[str, Any]],
    data_bindings: list[dict[str, Any]],
    kind: str,
    role: str,
    presentation: str,
    summary: str | None = None,
) -> list[SceneNode]:
    if not specs and not summary:
        return []
    section_id = _node_id(prefix, section_name)
    child_ids: list[str] = []
    nodes: list[SceneNode] = []
    if specs:
        for index, spec in enumerate(specs, start=1):
            binding_id = _node_id(prefix, "binding", section_name, spec["token"], f"{index:02d}")
            node_id = _node_id(prefix, section_name, spec["token"], f"{index:02d}")
            child_ids.append(node_id)
            nodes.append(
                SceneNode(
                    node_id=node_id,
                    kind=kind,
                    role=f"{role}.item",
                    label=spec["label"],
                    binding_ids=(binding_id,),
                    state_tags=("content",),
                    props={
                        "presentation": presentation,
                        "priority": spec["priority"],
                        "source_path": spec["source_path"],
                    },
                )
            )
            data_bindings.append(
                {
                    "binding_id": binding_id,
                    "source_path": spec["source_path"],
                    "target_node_id": node_id,
                    "priority": spec["priority"],
                    "presentation": presentation,
                    "binding_label": spec["label"],
                }
            )
    if summary:
        summary_id = _node_id(prefix, section_name, "summary")
        child_ids.append(summary_id)
        nodes.append(
            SceneNode(
                node_id=summary_id,
                kind="text",
                role=f"{role}.summary",
                label=summary,
                state_tags=("content",),
                props={"semantic_role": "app.body"},
            )
        )
    nodes.insert(
        0,
        SceneNode(
            node_id=section_id,
            kind="container",
            role=role,
            label=label,
            children=tuple(child_ids),
            props={"presentation": presentation},
        ),
    )
    return nodes


def _build_action_section(*, prefix: str, section_name: str, items: Sequence[str]) -> list[SceneNode]:
    if not items:
        return []
    section_id = _node_id(prefix, section_name)
    child_ids: list[str] = []
    nodes: list[SceneNode] = []
    for index, item in enumerate(items[:3], start=1):
        node_id = _node_id(prefix, section_name, "item", f"{index:02d}")
        child_ids.append(node_id)
        nodes.append(
            SceneNode(
                node_id=node_id,
                kind="button",
                role="section.action_strip.item",
                label=item,
                state_tags=("action",),
                props={"semantic_role": "button.primary" if index == 1 else "button.secondary"},
            )
        )
    nodes.insert(
        0,
        SceneNode(
            node_id=section_id,
            kind="container",
            role="section.action_strip",
            label="Action strip",
            children=tuple(child_ids),
            props={"presentation": "horizontal_actions"},
        ),
    )
    return nodes


def _build_navigation_section(
    *,
    prefix: str,
    navigation_specs: Sequence[dict[str, str]],
    mode: str,
    binding_specs: Sequence[dict[str, Any]],
    data_bindings: list[dict[str, Any]],
) -> list[SceneNode]:
    if not navigation_specs:
        return []
    section_id = _node_id(prefix, "navigation")
    child_ids: list[str] = []
    nodes: list[SceneNode] = []
    for index, spec in enumerate(navigation_specs[:4], start=1):
        node_id = _node_id(prefix, "navigation", spec["token"], f"{index:02d}")
        binding_ids: tuple[str, ...] = ()
        props: dict[str, Any] = {
            "priority": spec["priority"],
            "target_screen_id": spec["target_screen_id"],
        }
        if index <= len(binding_specs):
            binding_spec = binding_specs[index - 1]
            binding_id = _node_id(prefix, "binding", "navigation", binding_spec["token"], f"{index:02d}")
            binding_ids = (binding_id,)
            props["source_path"] = binding_spec["source_path"]
            data_bindings.append(
                {
                    "binding_id": binding_id,
                    "source_path": binding_spec["source_path"],
                    "target_node_id": node_id,
                    "priority": binding_spec["priority"],
                    "presentation": mode,
                    "binding_label": binding_spec["label"],
                }
            )
        child_ids.append(node_id)
        nodes.append(
            SceneNode(
                node_id=node_id,
                kind="button",
                role="section.navigation.item",
                label=spec["label"],
                binding_ids=binding_ids,
                state_tags=("navigation",),
                props=props,
            )
        )
    nodes.insert(
        0,
        SceneNode(
            node_id=section_id,
            kind="tab_bar" if mode == "tabs" else "container",
            role="section.navigation",
            label="Navigation",
            children=tuple(child_ids),
            props={"presentation": mode},
        ),
    )
    return nodes


def _build_status_section(*, prefix: str, states: Sequence[str], motifs: Sequence[str]) -> list[SceneNode]:
    chips = [(_humanize_token(state), "state") for state in states[:3]]
    chips.extend((_humanize_token(motif), "motif") for motif in motifs[:2])
    if not chips:
        return []
    section_id = _node_id(prefix, "status")
    child_ids: list[str] = []
    nodes: list[SceneNode] = []
    for index, (label, source_kind) in enumerate(chips, start=1):
        node_id = _node_id(prefix, "status", source_kind, f"{index:02d}")
        child_ids.append(node_id)
        nodes.append(
            SceneNode(
                node_id=node_id,
                kind="chip",
                role="section.status.item",
                label=label,
                state_tags=("status",),
                props={"source_kind": source_kind},
            )
        )
    nodes.insert(
        0,
        SceneNode(
            node_id=section_id,
            kind="container",
            role="section.status",
            label="Status rail",
            children=tuple(child_ids),
            props={"presentation": "compact_wrap"},
        ),
    )
    return nodes


def _build_evidence_section(*, prefix: str, evidence_specs: Sequence[dict[str, str]]) -> list[SceneNode]:
    if not evidence_specs:
        return []
    section_id = _node_id(prefix, "evidence")
    child_ids: list[str] = []
    nodes: list[SceneNode] = []
    for index, spec in enumerate(evidence_specs, start=1):
        node_id = _node_id(prefix, "evidence", spec["token"], f"{index:02d}")
        child_ids.append(node_id)
        nodes.append(
            SceneNode(
                node_id=node_id,
                kind="badge",
                role="section.evidence.item",
                label=spec["label"],
                state_tags=("evidence",),
                props={"evidence_ref": spec["evidence_ref"]},
            )
        )
    nodes.insert(
        0,
        SceneNode(
            node_id=section_id,
            kind="container",
            role="section.evidence",
            label="Evidence",
            children=tuple(child_ids),
            props={"presentation": "proof_strip"},
        ),
    )
    return nodes


def _binding_specs(values: Sequence[Any], *, priority: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for index, value in enumerate(values, start=1):
        path = str(value).strip()
        if not path:
            continue
        specs.append(
            {
                "source_path": path,
                "priority": priority,
                "label": _humanize_data_path(path),
                "token": f"{_slugify(path)}-{index:02d}",
            }
        )
    return specs


def _navigation_specs(values: Sequence[Any]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, Mapping):
            continue
        target_screen_id = str(value.get("target_screen_id") or "").strip()
        if not target_screen_id:
            continue
        label = _humanize_token(target_screen_id)
        specs.append(
            {
                "target_screen_id": target_screen_id,
                "priority": str(value.get("priority") or "secondary"),
                "label": label,
                "token": f"{_slugify(target_screen_id)}-{index:02d}",
            }
        )
    return specs


def _evidence_specs(values: Sequence[Any]) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, Mapping):
            continue
        evidence_ref = str(value.get("evidence_ref") or "").strip()
        if not evidence_ref:
            continue
        specs.append(
            {
                "evidence_ref": evidence_ref,
                "label": str(value.get("summary") or value.get("kind") or "Evidence"),
                "token": f"{_slugify(evidence_ref)}-{index:02d}",
            }
        )
    return specs


def _action_items(*, jobs: Sequence[str], navigation: Sequence[dict[str, str]], source: str) -> list[str]:
    items: list[str] = []
    if source in {"jobs", "mixed"}:
        items.extend(jobs[:2])
    if source in {"navigation", "mixed"}:
        items.extend(f"Open {_humanize_token(item['target_screen_id'])}" for item in navigation[:2])
    deduped: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _humanize_data_path(value: str) -> str:
    parts = [part for part in value.split(".") if part]
    if not parts:
        return "Data"
    if len(parts) == 1:
        return _humanize_token(parts[0])
    return f"{_humanize_token(parts[0])} / {_humanize_token(parts[-1])}"


def _humanize_token(value: str) -> str:
    cleaned = value.replace("-", " ").replace("_", " ").replace(".", " ").strip()
    return " ".join(word.capitalize() for word in cleaned.split()) or "Item"


def _first(values: Sequence[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _node_id(*parts: str) -> str:
    return _slugify("__".join(part for part in parts if part))


def _slugify(value: str) -> str:
    text = value.strip().lower()
    result: list[str] = []
    previous_hyphen = False
    for char in text:
        if char.isalnum():
            result.append(char)
            previous_hyphen = False
            continue
        if not previous_hyphen:
            result.append("-")
            previous_hyphen = True
    slug = "".join(result).strip("-")
    return slug or "item"

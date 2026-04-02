from __future__ import annotations

import colorsys
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.config_loader import load_orchestrator_config
from mobile_design_orchestrator.project import (
    CANONICAL_COMPONENT_KINDS,
    DEFAULT_PLATFORMS,
    default_brief,
    default_ideas,
    default_platform_mapping,
    default_semantics,
    default_tokens,
    default_typography,
    ensure_dir,
    latest_run_report,
    load_optional_json,
    new_run_id,
    now_iso,
    preview_summary,
    read_json,
    scaffold_json,
    scaffold_markdown,
    slugify,
    validation_markdown,
    validate_output_dir,
    write_json,
    write_markdown,
)

ORCHESTRATOR_CONFIG = load_orchestrator_config()
PROPOSAL_ARCHETYPES: dict[str, dict[str, Any]] = ORCHESTRATOR_CONFIG["proposal_archetypes"]
SIGNAL_CLUSTER_DEFINITIONS: dict[str, dict[str, Any]] = ORCHESTRATOR_CONFIG["signal_clusters"]

SIGNAL_STOPWORDS = {
    "about",
    "after",
    "all",
    "and",
    "app",
    "apps",
    "are",
    "but",
    "can",
    "clear",
    "design",
    "flow",
    "for",
    "from",
    "have",
    "into",
    "its",
    "just",
    "make",
    "more",
    "not",
    "one",
    "only",
    "page",
    "screen",
    "screens",
    "should",
    "step",
    "steps",
    "that",
    "the",
    "their",
    "them",
    "this",
    "through",
    "use",
    "with",
    "your",
}

def _path_action(path: Path, existed: bool) -> dict[str, str]:
    return {"path": str(path), "action": "updated" if existed else "created"}


def _required_json(path: Path, failure_code: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{failure_code}: missing file {path}")
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{failure_code}: expected object in {path}")
    return data


def _required_markdown(path: Path, failure_code: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{failure_code}: missing file {path}")
    return path.read_text().strip()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _select_run_report(
    scrape_root: Path,
    run_id: str | None = None,
    run_report: Path | None = None,
    allow_manifest_only: bool = False,
) -> Path | None:
    metadata_dir = scrape_root / "metadata"
    if run_report is not None:
        return run_report
    if run_id:
        candidate = metadata_dir / f"run_{run_id}.json"
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"run report for run_id={run_id} was not found in {metadata_dir}")
    latest = latest_run_report(metadata_dir)
    if latest is not None:
        return latest
    if allow_manifest_only:
        return None
    raise FileNotFoundError(f"no run_*.json reports found in {metadata_dir}")


def _proposal_text_fragments(project_name: str, inspirations: dict[str, Any], ideas: dict[str, Any]) -> list[str]:
    text_fragments = [project_name]
    for source in inspirations.get("sources", []):
        text_fragments.extend(
            [
                source.get("source") or "",
                source.get("title") or "",
                source.get("source_url") or "",
            ]
        )
    for idea in ideas.get("ideas", []):
        text_fragments.extend(
            [
                idea.get("title") or "",
                idea.get("summary") or "",
                idea.get("rationale") or "",
                idea.get("pattern_category") or "",
                " ".join(idea.get("target_screens", [])),
            ]
        )
    return text_fragments


def _build_duplicate_lookup(duplicates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for group_index, group in enumerate(duplicates.get("duplicate_groups", [])):
        files = group.get("files", [])
        distance = group.get("distance")
        if not files:
            continue
        primary = files[0]
        for file_index, relative_path in enumerate(files):
            lookup[relative_path] = {
                "is_duplicate": True,
                "group_index": group_index,
                "distance": distance,
                "primary": relative_path == primary,
                "included": True,
            }
    return lookup


def _build_run_source_lookup(run_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for adapter_result in run_report.get("adapter_results", []):
        normalized_url = adapter_result.get("normalized_url") or adapter_result.get("url")
        if not normalized_url:
            continue
        lookup[normalized_url] = {
            "source": adapter_result.get("source"),
            "title": adapter_result.get("title"),
            "author": adapter_result.get("author"),
            "run_status": adapter_result.get("status"),
            "warnings": list(adapter_result.get("warnings", [])),
            "notes": list(adapter_result.get("notes", [])),
            "fetch": {
                "requested_variant": adapter_result.get("metadata", {}).get("requested_variant"),
                "effective_variant": adapter_result.get("metadata", {}).get("effective_variant"),
                "final_url": adapter_result.get("metadata", {}).get("final_url"),
            },
        }
    return lookup


def ingest_inspiration(
    output_dir: Path,
    scrape_root: Path,
    project_name: str | None = None,
    force: bool = False,
    run_id: str | None = None,
    run_report: Path | None = None,
    allow_manifest_only: bool = False,
    include_duplicates: str = "flagged",
    strict: bool = False,
    min_assets_per_source: int = 1,
    max_fallback_screenshot_ratio: float = 1.0,
    max_duplicate_ratio: float = 1.0,
    require_color_summary: bool = False,
) -> dict[str, Any]:
    manifest_path = scrape_root / "metadata" / "index.json"
    manifest = _required_json(manifest_path, "scrape_input_missing")
    if "assets" not in manifest or not isinstance(manifest["assets"], dict):
        raise ValueError(f"inspiration_manifest_invalid: assets object missing in {manifest_path}")
    if not manifest["assets"]:
        raise ValueError("insufficient_inputs: scrape manifest contains no assets")

    selected_run_path = _select_run_report(
        scrape_root=scrape_root,
        run_id=run_id,
        run_report=run_report,
        allow_manifest_only=allow_manifest_only,
    )
    run_data = read_json(selected_run_path) if selected_run_path else {}
    color_summary_path = scrape_root / "color_summary.json"
    color_summary = load_optional_json(color_summary_path)
    duplicates_path = scrape_root / "duplicates.json"
    duplicates = load_optional_json(duplicates_path) or {}
    if require_color_summary and color_summary is None:
        raise ValueError(f"scrape_input_missing: required color summary missing at {color_summary_path}")

    duplicate_lookup = _build_duplicate_lookup(duplicates)
    source_lookup = _build_run_source_lookup(run_data)
    status_counts: Counter[str] = Counter()
    warnings: list[str] = []
    errors: list[str] = []

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_key": None,
            "source": None,
            "source_url": None,
            "normalized_url": None,
            "title": None,
            "author": None,
            "run_status": None,
            "asset_count": 0,
            "included_asset_count": 0,
            "fallback_screenshot_count": 0,
            "warnings": [],
            "notes": [],
            "fetch": {},
            "assets": [],
        }
    )

    for local_path, asset in manifest["assets"].items():
        source_url = asset.get("source_url") or "unknown"
        source_info = source_lookup.get(source_url, {})
        source_key = f"{source_info.get('source') or 'unknown'}::{source_url}"

        raw_local_path = asset.get("local_path") or local_path
        asset_path = Path(raw_local_path)
        if not asset_path.is_absolute():
            if str(asset_path).startswith(str(scrape_root)):
                asset_path = Path(str(asset_path))
            else:
                asset_path = scrape_root / asset_path
        relative_path = _relative_path(asset_path, scrape_root)
        exists = asset_path.exists()

        duplicate = dict(
            duplicate_lookup.get(
                relative_path,
                {
                    "is_duplicate": False,
                    "group_index": None,
                    "distance": None,
                    "primary": True,
                    "included": True,
                },
            )
        )
        if include_duplicates == "unique" and duplicate["is_duplicate"] and not duplicate["primary"]:
            duplicate["included"] = False

        group = grouped[source_url]
        group["source_key"] = source_key
        group["source"] = group["source"] or source_info.get("source")
        group["source_url"] = source_url
        group["normalized_url"] = source_url
        group["title"] = group["title"] or source_info.get("title")
        group["author"] = group["author"] or source_info.get("author")
        group["run_status"] = group["run_status"] or source_info.get("run_status") or asset.get("status")
        group["fetch"] = group["fetch"] or source_info.get("fetch") or {}
        group["warnings"] = sorted(set(group["warnings"] + source_info.get("warnings", [])))
        group["notes"] = sorted(set(group["notes"] + source_info.get("notes", [])))
        group["asset_count"] += 1
        if duplicate["included"]:
            group["included_asset_count"] += 1
        if asset.get("fallback_screenshot"):
            group["fallback_screenshot_count"] += 1

        if not exists:
            warning = f"missing asset file for {relative_path}"
            group["warnings"].append(warning)
            warnings.append(warning)
            if strict:
                errors.append(warning)

        asset_status = asset.get("status") or group["run_status"] or "downloaded"
        status_counts[asset_status] += 1
        group["assets"].append(
            {
                "asset_id": f"sha256:{asset.get('sha256')}" if asset.get("sha256") else relative_path,
                "local_path": str(asset_path),
                "relative_path": relative_path,
                "exists": exists,
                "kind": asset.get("kind"),
                "mime_type": asset.get("mime_type"),
                "file_size": asset.get("file_size"),
                "width": asset.get("width"),
                "height": asset.get("height"),
                "sha256": asset.get("sha256"),
                "canonical_url": asset.get("canonical_url"),
                "source_url": source_url,
                "status": asset_status,
                "fallback_screenshot": asset.get("fallback_screenshot", False),
                "warnings": list(asset.get("warnings", [])),
                "duplicate": duplicate,
                "palette": {
                    "available": (asset_path.parent / "palette.json").exists(),
                    "path": str(asset_path.parent / "palette.json") if (asset_path.parent / "palette.json").exists() else None,
                },
                "metadata": asset.get("metadata", {}),
            }
        )

    for source_url, source_info in source_lookup.items():
        if source_url in grouped:
            continue
        group = grouped[source_url]
        group["source_key"] = f"{source_info.get('source') or 'unknown'}::{source_url}"
        group["source"] = source_info.get("source")
        group["source_url"] = source_url
        group["normalized_url"] = source_url
        group["title"] = source_info.get("title")
        group["author"] = source_info.get("author")
        group["run_status"] = source_info.get("run_status")
        group["warnings"] = list(source_info.get("warnings", []))
        group["notes"] = list(source_info.get("notes", []))
        group["fetch"] = source_info.get("fetch", {})

    source_entries = sorted(grouped.values(), key=lambda item: (item["source"] or "", item["source_url"] or ""))
    fallback_count = sum(item["fallback_screenshot_count"] for item in source_entries)
    duplicate_group_count = len(duplicates.get("duplicate_groups", []))
    asset_count = sum(item["asset_count"] for item in source_entries)
    included_asset_count = sum(item["included_asset_count"] for item in source_entries)
    excluded_duplicate_asset_count = asset_count - included_asset_count

    for entry in source_entries:
        if entry["asset_count"] < min_assets_per_source:
            msg = f"source {entry['source_url']} has only {entry['asset_count']} assets"
            warnings.append(msg)
            entry["warnings"].append(msg)
            if strict:
                errors.append(msg)

    if asset_count:
        fallback_ratio = fallback_count / asset_count
        duplicate_ratio = excluded_duplicate_asset_count / asset_count
        if fallback_ratio > max_fallback_screenshot_ratio:
            msg = f"fallback screenshot ratio {fallback_ratio:.2f} exceeds threshold {max_fallback_screenshot_ratio:.2f}"
            warnings.append(msg)
            if strict:
                errors.append(msg)
        if duplicate_ratio > max_duplicate_ratio:
            msg = f"duplicate ratio {duplicate_ratio:.2f} exceeds threshold {max_duplicate_ratio:.2f}"
            warnings.append(msg)
            if strict:
                errors.append(msg)

    status = "failed" if errors else ("completed_with_warnings" if warnings else "completed")
    selected_run = {
        "run_id": run_data.get("run_id"),
        "run_report": str(selected_run_path) if selected_run_path else None,
        "started_at": run_data.get("started_at"),
        "completed_at": run_data.get("completed_at"),
        "status": run_data.get("status") if run_data else "manifest_only",
    }
    inspirations = {
        "schema_version": "1.0.0",
        "status": status,
        "ingested_at": now_iso(),
        "project": project_name,
        "scrape_root": str(scrape_root),
        "selected_run": selected_run,
        "source_artifacts": {
            "manifest": str(manifest_path),
            "run_report": str(selected_run_path) if selected_run_path else None,
            "color_summary": str(color_summary_path) if color_summary is not None else None,
            "duplicates": str(duplicates_path) if duplicates else None,
        },
        "summary": {
            "source_count": len(source_entries),
            "asset_count": asset_count,
            "included_asset_count": included_asset_count,
            "excluded_duplicate_asset_count": excluded_duplicate_asset_count,
            "duplicate_group_count": duplicate_group_count,
            "fallback_screenshot_count": fallback_count,
            "status_counts": dict(status_counts),
            "dark_mode_count": color_summary.get("dark_mode_count") if color_summary else None,
            "light_mode_count": color_summary.get("light_mode_count") if color_summary else None,
            "most_common_colors": color_summary.get("most_common_colors", []) if color_summary else [],
        },
        "sources": source_entries,
        "warnings": sorted(set(warnings)),
        "errors": sorted(set(errors)),
    }
    report = {
        "status": status,
        "failure_code": None if not errors else "inspiration_manifest_invalid",
        "ingested_at": inspirations["ingested_at"],
        "scrape_root": str(scrape_root),
        "run_id": selected_run["run_id"],
        "written_artifacts": [
            str(output_dir / "inspirations" / "index.json"),
            str(output_dir / "inspirations" / "ingest_report.json"),
        ],
        "warnings": inspirations["warnings"],
        "errors": inspirations["errors"],
    }

    actions: list[dict[str, str]] = []
    inspirations_path = output_dir / "inspirations" / "index.json"
    existed = inspirations_path.exists()
    write_json(inspirations_path, inspirations)
    actions.append(_path_action(inspirations_path, existed))
    report_path = output_dir / "inspirations" / "ingest_report.json"
    existed = report_path.exists()
    write_json(report_path, report)
    actions.append(_path_action(report_path, existed))
    return {"report": report, "inspirations": inspirations, "actions": actions}


def _proposal_profile(
    project_name: str,
    inspirations: dict[str, Any],
    ideas: dict[str, Any],
    signal_clusters: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    scorecards = _proposal_scores(project_name, inspirations, ideas, signal_clusters)
    best_id = scorecards[0]["direction_id"] if scorecards else "calm_editorial"
    return best_id, PROPOSAL_ARCHETYPES[best_id], scorecards


def _proposal_scores(
    project_name: str,
    inspirations: dict[str, Any],
    ideas: dict[str, Any],
    signal_clusters: dict[str, Any],
) -> list[dict[str, Any]]:
    text_blob = " ".join(_proposal_text_fragments(project_name, inspirations, ideas)).lower()
    cluster_entries = signal_clusters.get("clusters", [])

    scorecards = []
    for profile_id, profile in PROPOSAL_ARCHETYPES.items():
        matched_keywords = sorted({keyword for keyword in profile["keywords"] if keyword in text_blob})
        cluster_matches = []
        cluster_score = 0
        for cluster in cluster_entries:
            if cluster.get("score", 0) <= 0:
                continue
            for influence in cluster.get("direction_influence", []):
                if influence.get("direction_id") != profile_id:
                    continue
                contribution = int(influence.get("contribution", 0))
                if contribution <= 0:
                    continue
                cluster_score += contribution
                cluster_matches.append(
                    {
                        "cluster_id": cluster.get("cluster_id"),
                        "cluster_label": cluster.get("label"),
                        "cluster_rank": cluster.get("rank"),
                        "cluster_score": cluster.get("score"),
                        "contribution": contribution,
                    }
                )
        cluster_matches = sorted(cluster_matches, key=lambda entry: (-entry["contribution"], entry["cluster_id"] or ""))
        scorecards.append(
            {
                "direction_id": profile_id,
                "score": cluster_score * 10 + len(matched_keywords),
                "cluster_score": cluster_score,
                "raw_keyword_score": len(matched_keywords),
                "matched_keywords": matched_keywords,
                "cluster_matches": cluster_matches,
            }
        )
    return sorted(scorecards, key=lambda item: (-item["score"], item["direction_id"]))


def _proposal_screen_targets(ideas: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for idea in ideas.get("ideas", []):
        for screen_id in idea.get("target_screens", []):
            if screen_id and screen_id not in ordered:
                ordered.append(screen_id)
    if not ordered:
        ordered = ["home", "detail"]
    if "app_shell" not in ordered:
        ordered.insert(0, "app_shell")
    return ordered


def _top_terms(values: list[str], limit: int = 8) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for value in values:
        for token in re.findall(r"[a-z0-9]+", (value or "").lower()):
            if len(token) <= 2 or token.isdigit() or token in SIGNAL_STOPWORDS:
                continue
            counts[token] += 1
    return [{"term": term, "count": count} for term, count in counts.most_common(limit)]


def _hex_to_rgb(value: str) -> tuple[float, float, float] | None:
    if not isinstance(value, str) or not re.fullmatch(r"#([A-Fa-f0-9]{6})", value):
        return None
    red = int(value[1:3], 16) / 255.0
    green = int(value[3:5], 16) / 255.0
    blue = int(value[5:7], 16) / 255.0
    return red, green, blue


def _palette_temperature(colors: list[str]) -> str:
    buckets: Counter[str] = Counter()
    for color in colors[:5]:
        rgb = _hex_to_rgb(color)
        if rgb is None:
            continue
        hue, saturation, _ = colorsys.rgb_to_hsv(*rgb)
        if saturation < 0.08:
            buckets["neutral"] += 1
        elif hue < 0.18 or hue >= 0.92:
            buckets["warm"] += 1
        elif 0.50 <= hue < 0.92:
            buckets["cool"] += 1
        else:
            buckets["neutral"] += 1
    if not buckets:
        return "neutral"
    return buckets.most_common(1)[0][0]


def _brightness_bias(light_count: int | None, dark_count: int | None) -> str:
    light = light_count or 0
    dark = dark_count or 0
    if light and light >= dark * 2:
        return "light"
    if dark and dark >= light * 2:
        return "dark"
    return "mixed"


def _build_signal_clusters(
    project_name: str,
    inspirations: dict[str, Any],
    ideas: dict[str, Any],
    screen_targets: list[str],
) -> dict[str, Any]:
    text_fragments = _proposal_text_fragments(project_name, inspirations, ideas)
    text_blob = " ".join(text_fragments).lower()
    idea_categories = {
        (idea.get("pattern_category") or "").lower()
        for idea in ideas.get("ideas", [])
        if idea.get("pattern_category")
    }

    clusters = []
    for cluster_id, definition in SIGNAL_CLUSTER_DEFINITIONS.items():
        matched_keywords = sorted({keyword for keyword in definition["keywords"] if keyword in text_blob})
        matched_categories = sorted({category for category in definition["categories"] if category in idea_categories})
        matched_screens = sorted({screen_id for screen_id in screen_targets if screen_id in definition["screens"]})
        matched_sources = []
        for source in inspirations.get("sources", []):
            source_text = " ".join(
                [
                    source.get("source") or "",
                    source.get("title") or "",
                    source.get("source_url") or "",
                ]
            ).lower()
            source_keywords = sorted({keyword for keyword in definition["keywords"] if keyword in source_text})
            if source_keywords:
                matched_sources.append(
                    {
                        "source": source.get("source"),
                        "title": source.get("title"),
                        "matched_keywords": source_keywords,
                    }
                )

        cluster_score = len(matched_keywords) + (len(matched_categories) * 2) + (len(matched_screens) * 2) + len(matched_sources)
        direction_influence = []
        for direction_id, weight in sorted(definition["direction_weights"].items()):
            contribution = cluster_score * weight
            if contribution <= 0:
                continue
            direction_influence.append(
                {
                    "direction_id": direction_id,
                    "weight": weight,
                    "contribution": contribution,
                }
            )

        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": definition["label"],
                "score": cluster_score,
                "matched_keywords": matched_keywords,
                "matched_categories": matched_categories,
                "matched_screens": matched_screens,
                "matched_sources": matched_sources,
                "direction_influence": direction_influence,
            }
        )

    clusters = sorted(clusters, key=lambda entry: (-entry["score"], entry["cluster_id"]))
    for rank, cluster in enumerate(clusters, start=1):
        cluster["rank"] = rank

    active_cluster_ids = [cluster["cluster_id"] for cluster in clusters if cluster["score"] > 0]
    dominant_cluster_id = active_cluster_ids[0] if active_cluster_ids else (clusters[0]["cluster_id"] if clusters else None)
    return {
        "cluster_count": len(clusters),
        "active_cluster_count": len(active_cluster_ids),
        "dominant_cluster_id": dominant_cluster_id,
        "active_cluster_ids": active_cluster_ids,
        "clusters": clusters,
    }


def _build_design_signals(
    project_name: str,
    inspirations: dict[str, Any],
    ideas: dict[str, Any],
    screen_targets: list[str],
    signal_clusters: dict[str, Any],
    profile: dict[str, Any],
    archetype_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    source_type_counts: Counter[str] = Counter()
    source_asset_counts: Counter[str] = Counter()
    source_titles: defaultdict[str, list[str]] = defaultdict(list)
    fallback_count = 0
    title_fragments: list[str] = []
    for source in inspirations.get("sources", []):
        source_name = source.get("source") or "unknown"
        source_type_counts[source_name] += 1
        source_asset_counts[source_name] += source.get("asset_count", 0)
        if source.get("title"):
            source_titles[source_name].append(source["title"])
            title_fragments.append(source["title"])
        fallback_count += source.get("fallback_screenshot_count", 0)

    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    target_screen_counts: Counter[str] = Counter()
    idea_fragments: list[str] = []
    for idea in ideas.get("ideas", []):
        category_counts[idea.get("pattern_category") or "uncategorized"] += 1
        status_counts[idea.get("status") or "candidate"] += 1
        for screen_id in idea.get("target_screens", []):
            if screen_id:
                target_screen_counts[screen_id] += 1
        idea_fragments.extend(
            [
                idea.get("title") or "",
                idea.get("summary") or "",
                idea.get("rationale") or "",
                idea.get("pattern_category") or "",
            ]
        )

    dominant_source = None
    if source_type_counts:
        dominant_source = sorted(source_type_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    motif_candidates = []
    for motif in profile.get("motifs", []):
        matched_screens = [screen_id for screen_id in screen_targets if screen_id in motif.get("applicable_screens", [])]
        motif_candidates.append(
            {
                "motif_id": motif.get("id"),
                "intent": motif.get("intent"),
                "matched_target_screens": matched_screens,
                "evidence": "matched target screens" if matched_screens else "fallback from selected proposal profile",
            }
        )

    source_count = inspirations.get("summary", {}).get("source_count", 0)
    idea_count = len(ideas.get("ideas", []))
    palette = inspirations.get("summary", {}).get("most_common_colors", [])
    top_score = archetype_scores[0]["score"] if archetype_scores else 0
    source_confidence = round(min(1.0, source_count / 3), 2)
    idea_confidence = round(min(1.0, idea_count / 4), 2)
    palette_confidence = round(min(1.0, len(palette[:5]) / 5), 2)
    overall_confidence = round((source_confidence + idea_confidence + palette_confidence + (1.0 if top_score > 0 else 0.4)) / 4, 2)

    return {
        "contract_version": "1.0.0",
        "project": project_name,
        "source_patterns": {
            "source_count": source_count,
            "dominant_source": dominant_source,
            "by_source": [
                {
                    "source": source_name,
                    "reference_count": count,
                    "asset_count": source_asset_counts[source_name],
                    "title_terms": _top_terms(source_titles[source_name], limit=4),
                }
                for source_name, count in sorted(source_type_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "fallback_screenshot_ratio": round(
                fallback_count / inspirations.get("summary", {}).get("asset_count", 1),
                2,
            )
            if inspirations.get("summary", {}).get("asset_count", 0)
            else 0.0,
            "duplicate_group_count": inspirations.get("summary", {}).get("duplicate_group_count", 0),
        },
        "idea_patterns": {
            "idea_count": idea_count,
            "categories": [
                {"category": category, "count": count}
                for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "statuses": [
                {"status": status, "count": count}
                for status, count in sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "target_screens": [
                {"screen_id": screen_id, "count": count}
                for screen_id, count in sorted(target_screen_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "evidence_terms": _top_terms(idea_fragments),
        },
        "screen_pressure": {
            "recommended_screens": screen_targets,
            "primary_screen": next((screen_id for screen_id in screen_targets if screen_id != "app_shell"), screen_targets[0] if screen_targets else None),
            "target_screen_counts": dict(target_screen_counts),
        },
        "color_observations": {
            "most_common_colors": palette,
            "palette_temperature": _palette_temperature(palette),
            "brightness_bias": _brightness_bias(
                inspirations.get("summary", {}).get("light_mode_count"),
                inspirations.get("summary", {}).get("dark_mode_count"),
            ),
            "light_mode_count": inspirations.get("summary", {}).get("light_mode_count"),
            "dark_mode_count": inspirations.get("summary", {}).get("dark_mode_count"),
        },
        "tone_observations": {
            "source_title_terms": _top_terms(title_fragments),
            "idea_terms": _top_terms(idea_fragments),
            "combined_terms": _top_terms([project_name, *title_fragments, *idea_fragments]),
        },
        "signal_clusters": signal_clusters,
        "motif_candidates": {
            "candidate_count": len(motif_candidates),
            "candidates": motif_candidates,
        },
        "confidence": {
            "source_signal": source_confidence,
            "idea_signal": idea_confidence,
            "palette_signal": palette_confidence,
            "overall": overall_confidence,
        },
        "archetype_scores": archetype_scores,
    }


def _direction_tradeoffs(direction_id: str) -> list[str]:
    lookup = {
        "calm_editorial": [
            "Can feel too restrained if the product needs stronger conversion energy.",
            "Needs disciplined hierarchy so softness does not turn into vagueness.",
        ],
        "utility_bold": [
            "Can become visually aggressive if accent usage is not tightly controlled.",
            "Needs stricter spacing rhythm to avoid dense dashboard behavior on mobile.",
        ],
        "playful_modular": [
            "Can feel juvenile if copy tone and imagery do not support the same posture.",
            "Modular surfaces need strong grouping rules to avoid visual noise.",
        ],
        "premium_cinematic": [
            "Can over-index on mood if legibility and task completion are not protected.",
            "Requires restraint so premium styling does not become heavy-handed on small screens.",
        ],
    }
    return lookup.get(
        direction_id,
        [
            "Needs explicit hierarchy rules to avoid generic execution.",
            "Requires downstream contract decisions to stay aligned with the selected direction.",
        ],
    )


def _build_direction_options(
    project_name: str,
    design_signals: dict[str, Any],
    archetype_scores: list[dict[str, Any]],
) -> dict[str, Any]:
    source_patterns = design_signals.get("source_patterns", {})
    idea_patterns = design_signals.get("idea_patterns", {})
    screen_pressure = design_signals.get("screen_pressure", {})
    signal_clusters = design_signals.get("signal_clusters", {})
    top_idea_terms = [entry.get("term") for entry in idea_patterns.get("evidence_terms", []) if entry.get("term")][:3]

    options = []
    for rank, scorecard in enumerate(archetype_scores, start=1):
        direction_id = scorecard["direction_id"]
        profile = PROPOSAL_ARCHETYPES[direction_id]
        options.append(
            {
                "direction_id": direction_id,
                "direction_name": profile["direction_name"],
                "score": scorecard["score"],
                "rank": rank,
                "selected": rank == 1,
                "matched_keywords": scorecard.get("matched_keywords", []),
                "evidence": {
                    "dominant_source": source_patterns.get("dominant_source"),
                    "primary_screen": screen_pressure.get("primary_screen"),
                    "dominant_cluster_id": signal_clusters.get("dominant_cluster_id"),
                    "supporting_clusters": [entry.get("cluster_id") for entry in scorecard.get("cluster_matches", [])[:2]],
                    "top_idea_terms": top_idea_terms,
                    "signal_confidence": design_signals.get("confidence", {}).get("overall"),
                    "cluster_score": scorecard.get("cluster_score", 0),
                    "matched_keyword_count": len(scorecard.get("matched_keywords", [])),
                },
                "tradeoffs": _direction_tradeoffs(direction_id),
            }
        )

    return {
        "contract_version": "1.0.0",
        "project": project_name,
        "selected_direction_id": options[0]["direction_id"] if options else None,
        "options": options,
    }


def _build_proposal_candidates(
    project_name: str,
    design_signals: dict[str, Any],
    direction_options: dict[str, Any],
    screen_targets: list[str],
) -> dict[str, Any]:
    cluster_lookup = {
        cluster.get("cluster_id"): cluster
        for cluster in design_signals.get("signal_clusters", {}).get("clusters", [])
        if isinstance(cluster, dict) and cluster.get("cluster_id")
    }
    primary_screen = design_signals.get("screen_pressure", {}).get("primary_screen") or (screen_targets[0] if screen_targets else "home")
    primary_screen_label = primary_screen.replace("_", " ")
    dominant_source = design_signals.get("source_patterns", {}).get("dominant_source") or "the current inspiration set"
    dominant_cluster_id = design_signals.get("signal_clusters", {}).get("dominant_cluster_id")
    dominant_cluster_label = cluster_lookup.get(dominant_cluster_id, {}).get("label", "the dominant product signal")
    top_idea_terms = [
        entry.get("term")
        for entry in design_signals.get("idea_patterns", {}).get("evidence_terms", [])
        if entry.get("term")
    ][:3]

    selected_direction_id = direction_options.get("selected_direction_id")
    selected_profile = PROPOSAL_ARCHETYPES.get(selected_direction_id or "", PROPOSAL_ARCHETYPES["calm_editorial"])
    candidates = []
    for option in direction_options.get("options", [])[:3]:
        direction_id = option.get("direction_id")
        if direction_id not in PROPOSAL_ARCHETYPES:
            continue
        profile = PROPOSAL_ARCHETYPES[direction_id]
        supporting_cluster_ids = option.get("evidence", {}).get("supporting_clusters", [])
        supporting_cluster_labels = [
            cluster_lookup.get(cluster_id, {}).get("label", cluster_id)
            for cluster_id in supporting_cluster_ids
            if cluster_id
        ]
        selected = direction_id == selected_direction_id
        visual_thesis = (
            f"{profile['direction_name']} should turn {primary_screen_label} into a {profile['atmosphere'][0]} mobile moment "
            f"by leaning on {profile['surface_treatment'].lower()} instead of generic app chrome."
        )
        why_this_app = (
            f"This direction fits {project_name} because the current evidence clusters around {dominant_cluster_label.lower()}, "
            f"keeps {primary_screen_label} as the leading screen pressure, and uses {dominant_source} as hierarchy input rather than a layout template."
        )
        key_strengths = [
            profile["composition_principles"][0],
            f"Use {profile['motifs'][0]['name']} to anchor {primary_screen_label} without copying the source screens.",
            f"Keep the voice in {profile['voice_name'].lower()} so the proposal still feels specific to this app.",
        ]
        selection_rationale = None
        rejection_rationale = None
        if selected:
            selection_rationale = (
                f"Selected because it best matches {dominant_cluster_label.lower()} and keeps `{primary_screen}` aligned to the most supported user task."
            )
        else:
            rejection_rationale = (
                f"Rejected for now because {selected_profile['direction_name'].lower()} tracks {dominant_cluster_label.lower()} more directly, "
                f"while {profile['direction_name'].lower()} would over-index on {profile['atmosphere'][0]} styling for the current evidence."
            )

        candidates.append(
            {
                "direction_id": direction_id,
                "direction_name": profile["direction_name"],
                "rank": option.get("rank"),
                "selected": selected,
                "score": option.get("score"),
                "visual_thesis": visual_thesis,
                "why_this_app": why_this_app,
                "key_strengths": key_strengths,
                "tradeoffs": _direction_tradeoffs(direction_id),
                "selection_rationale": selection_rationale,
                "rejection_rationale": rejection_rationale,
                "proposal_implications": {
                    "tokens": [
                        f"Carry {profile['surface_treatment'].lower()} into surface, radius, and spacing posture.",
                        f"Translate {profile['motion_posture'].lower()} into motion timing and feedback choices.",
                    ],
                    "semantics": [
                        f"Treat {profile['motifs'][0]['id']} as a first-class semantic motif.",
                        f"Let {profile['composition_principles'][0].lower()} shape button and card hierarchy rules.",
                    ],
                    "screens": [
                        f"Make `{primary_screen}` the clearest expression of this direction.",
                        f"Use {', '.join(supporting_cluster_labels) or dominant_cluster_label.lower()} to decide which supporting modules earn space first.",
                    ],
                },
                "evidence": {
                    "dominant_cluster_id": dominant_cluster_id,
                    "supporting_clusters": supporting_cluster_ids,
                    "primary_screen": primary_screen,
                    "dominant_source": dominant_source,
                    "top_idea_terms": top_idea_terms,
                },
            }
        )

    return {
        "contract_version": "1.0.0",
        "project": project_name,
        "selected_direction_id": selected_direction_id,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "non_negotiables": [
            f"Keep `{primary_screen}` aligned to {selected_profile['direction_name'].lower()} instead of mixing in off-direction chrome.",
            f"Preserve {selected_profile['surface_treatment'].lower()} and {selected_profile['motifs'][0]['name']} as the main visual anchors.",
            f"Let {dominant_cluster_label.lower()} set hierarchy before adding secondary modules.",
        ],
        "open_questions": [
            f"How far should `{primary_screen}` lean into {selected_profile['motifs'][0]['name']} before it starts to crowd the task flow?",
            f"Which secondary screen should receive the next strongest emphasis after `{primary_screen}`?",
            f"Which of {', '.join(top_idea_terms) or 'the current idea terms'} should be treated as non-negotiable copy or interaction cues?",
        ],
    }


def _build_review_packet(proposal_candidates: dict[str, Any]) -> str:
    selected_direction_id = proposal_candidates.get("selected_direction_id")
    candidate_lookup = {
        candidate.get("direction_id"): candidate
        for candidate in proposal_candidates.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("direction_id")
    }
    selected_candidate = candidate_lookup.get(selected_direction_id) or next(
        (candidate for candidate in proposal_candidates.get("candidates", []) if candidate.get("selected")),
        None,
    )

    lines = [
        "# Proposal Review Packet",
        "",
        "## Selected Direction",
    ]
    if selected_candidate:
        lines.extend(
            [
                f"- Direction: {selected_candidate['direction_name']}",
                f"- Rank: {selected_candidate['rank']}",
                f"- Thesis: {selected_candidate['visual_thesis']}",
                f"- Why selected: {selected_candidate.get('selection_rationale') or 'Top ranked deterministic candidate.'}",
            ]
        )

    lines.extend(
        [
            "",
            "## Candidate Review",
        ]
    )
    for candidate in proposal_candidates.get("candidates", []):
        status = "Selected" if candidate.get("selected") else "Rejected"
        lines.extend(
            [
                "",
                f"### {candidate['rank']}. {candidate['direction_name']} ({status})",
                f"- Score: {candidate['score']}",
                f"- Visual thesis: {candidate['visual_thesis']}",
                f"- Why this app: {candidate['why_this_app']}",
                "- Key strengths:",
            ]
        )
        lines.extend(f"  - {strength}" for strength in candidate.get("key_strengths", []))
        lines.append("- Tradeoffs:")
        lines.extend(f"  - {tradeoff}" for tradeoff in candidate.get("tradeoffs", []))
        implication_lines = candidate.get("proposal_implications", {})
        lines.append("- Proposal implications:")
        for implication_group in ("tokens", "semantics", "screens"):
            values = implication_lines.get(implication_group, [])
            if values:
                lines.append(f"  - {implication_group}: {'; '.join(values)}")
        if candidate.get("selected"):
            lines.append(f"- Selection rationale: {candidate.get('selection_rationale')}")
        else:
            lines.append(f"- Rejection rationale: {candidate.get('rejection_rationale')}")

    lines.extend(["", "## Non-Negotiables"])
    lines.extend(f"- {rule}" for rule in proposal_candidates.get("non_negotiables", []))
    lines.extend(["", "## Open Questions"])
    lines.extend(f"- {question}" for question in proposal_candidates.get("open_questions", []))
    return "\n".join(lines) + "\n"


def _proposal_bundle(output_dir: Path) -> dict[str, Any]:
    return {
        "design_direction": _required_markdown(output_dir / "proposal" / "design_direction.md", "proposal_missing"),
        "design_signals": _required_json(output_dir / "proposal" / "design_signals.json", "proposal_missing"),
        "direction_options": _required_json(output_dir / "proposal" / "direction_options.json", "proposal_missing"),
        "proposal_candidates": _required_json(output_dir / "proposal" / "proposal_candidates.json", "proposal_missing"),
        "review_packet": _required_markdown(output_dir / "proposal" / "review_packet.md", "proposal_missing"),
        "visual_language": _required_json(output_dir / "proposal" / "visual_language.json", "insufficient_inputs"),
        "typography_voice": _required_json(output_dir / "proposal" / "typography_voice.json", "insufficient_inputs"),
        "component_motifs": _required_json(output_dir / "proposal" / "component_motifs.json", "insufficient_inputs"),
        "flow_narrative": _required_markdown(output_dir / "proposal" / "flow_narrative.md", "proposal_missing"),
        "anti_patterns": _required_markdown(output_dir / "proposal" / "anti_patterns.md", "proposal_missing"),
        "source_rationale": _required_json(output_dir / "proposal" / "source_rationale.json", "insufficient_inputs"),
    }


def synthesize_proposal(output_dir: Path, project_name: str, force: bool = False) -> dict[str, Any]:
    inspirations = _required_json(output_dir / "inspirations" / "index.json", "insufficient_inputs")
    ideas = _required_json(output_dir / "ideas" / "index.json", "insufficient_inputs")
    screen_targets = _proposal_screen_targets(ideas)
    signal_clusters = _build_signal_clusters(project_name, inspirations, ideas, screen_targets)
    proposal_id, profile, archetype_scores = _proposal_profile(project_name, inspirations, ideas, signal_clusters)
    design_signals = _build_design_signals(
        project_name=project_name,
        inspirations=inspirations,
        ideas=ideas,
        screen_targets=screen_targets,
        signal_clusters=signal_clusters,
        profile=profile,
        archetype_scores=archetype_scores,
    )
    direction_options = _build_direction_options(
        project_name=project_name,
        design_signals=design_signals,
        archetype_scores=archetype_scores,
    )
    proposal_candidates = _build_proposal_candidates(
        project_name=project_name,
        design_signals=design_signals,
        direction_options=direction_options,
        screen_targets=screen_targets,
    )
    covered_sources = []
    for source in inspirations.get("sources", []):
        covered_sources.append(
            {
                "source_url": source.get("source_url"),
                "source": source.get("source"),
                "title": source.get("title"),
                "used_for": [
                    "hierarchy" if "hero" not in profile["motifs"][0]["id"] else "hero framing",
                    "tone",
                    "component rhythm",
                ],
                "reason": f"Use this source to reinforce {profile['direction_name'].lower()} without copying the original layout.",
            }
        )
    covered_ideas = []
    for idea in ideas.get("ideas", []):
        covered_ideas.append(
            {
                "idea_id": idea.get("idea_id"),
                "title": idea.get("title"),
                "translated_into": [
                    "proposal/design_direction.md",
                    "proposal/component_motifs.json",
                    "proposal/flow_narrative.md",
                ],
                "reason": idea.get("rationale") or idea.get("summary") or "Used to keep the proposal grounded in reviewed inspiration.",
            }
        )

    recommended_screens = []
    for screen_id in screen_targets:
        matching_motifs = [
            motif["id"]
            for motif in profile["motifs"]
            if screen_id in motif.get("applicable_screens", [])
        ]
        recommended_screens.append(
            {
                "screen_id": screen_id,
                "story": f"{screen_id.replace('_', ' ').title()} should express {profile['direction_name'].lower()} with {', '.join(matching_motifs) or 'clear hierarchy'}.",
                "primary_motifs": matching_motifs,
            }
        )

    visual_language = {
        "contract_version": "1.0.0",
        "project": project_name,
        "direction_id": proposal_id,
        "direction_name": profile["direction_name"],
        "summary": profile["summary"],
        "atmosphere": profile["atmosphere"],
        "composition_principles": profile["composition_principles"],
        "color_signal": profile["color_signal"],
        "surface_treatment": profile["surface_treatment"],
        "motion_posture": profile["motion_posture"],
    }
    typography_voice = {
        "contract_version": "1.0.0",
        "project": project_name,
        "direction_id": proposal_id,
        "direction_name": profile["direction_name"],
        "voice_name": profile["voice_name"],
        "font_family": profile["font_family"],
        "fallbacks": profile["fallbacks"],
        "headline_tone": profile["headline_tone"],
        "body_tone": profile["body_tone"],
        "usage_principles": profile["usage_principles"],
        "scale_adjustments": profile["scale_adjustments"],
        "tracking": profile["tracking"],
        "headline_weight": profile["headline_weight"],
        "title_weight": profile["title_weight"],
        "body_weight": profile["body_weight"],
    }
    component_motifs = {
        "contract_version": "1.0.0",
        "project": project_name,
        "direction_id": proposal_id,
        "direction_name": profile["direction_name"],
        "motifs": profile["motifs"],
    }
    source_rationale = {
        "contract_version": "1.0.0",
        "project": project_name,
        "direction_id": proposal_id,
        "direction_name": profile["direction_name"],
        "decision_summary": profile["decision_summary"],
        "direction_principles": profile["composition_principles"],
        "source_coverage": {
            "source_count": inspirations.get("summary", {}).get("source_count", 0),
            "covered_source_count": len(covered_sources),
            "covered_sources": covered_sources,
        },
        "idea_coverage": {
            "idea_count": len(ideas.get("ideas", [])),
            "covered_idea_count": len(covered_ideas),
            "covered_ideas": covered_ideas,
        },
        "recommended_screens": recommended_screens,
        "signal_summary": {
            "dominant_source": design_signals["source_patterns"].get("dominant_source"),
            "primary_screen": design_signals["screen_pressure"].get("primary_screen"),
            "top_idea_terms": design_signals["idea_patterns"].get("evidence_terms", [])[:3],
        },
    }

    design_direction = f"""# {profile["direction_name"]}

## Position

{profile["summary"]}

## Visual language

- Atmosphere: {", ".join(profile["atmosphere"])}
- Surface treatment: {profile["surface_treatment"]}
- Motion posture: {profile["motion_posture"]}

## Composition rules

""" + "\n".join(f"- {rule}" for rule in profile["composition_principles"]) + "\n"

    flow_narrative = f"""# Flow Narrative

{profile["flow_prompt"]}

## Recommended screen emphasis

""" + "\n".join(
        f"- `{screen['screen_id']}`: {screen['story']}" for screen in recommended_screens
    ) + "\n"

    anti_patterns = """# Anti-Patterns

Keep these out of the synthesized contract and screens:

""" + "\n".join(f"- {rule}" for rule in profile["anti_patterns"]) + "\n"
    review_packet = _build_review_packet(proposal_candidates)

    actions: list[dict[str, str]] = []
    artifact_writes = [
        (output_dir / "proposal" / "design_direction.md", design_direction, "markdown"),
        (output_dir / "proposal" / "design_signals.json", design_signals, "json"),
        (output_dir / "proposal" / "direction_options.json", direction_options, "json"),
        (output_dir / "proposal" / "proposal_candidates.json", proposal_candidates, "json"),
        (output_dir / "proposal" / "review_packet.md", review_packet, "markdown"),
        (output_dir / "proposal" / "visual_language.json", visual_language, "json"),
        (output_dir / "proposal" / "typography_voice.json", typography_voice, "json"),
        (output_dir / "proposal" / "component_motifs.json", component_motifs, "json"),
        (output_dir / "proposal" / "flow_narrative.md", flow_narrative, "markdown"),
        (output_dir / "proposal" / "anti_patterns.md", anti_patterns, "markdown"),
        (output_dir / "proposal" / "source_rationale.json", source_rationale, "json"),
    ]
    for path, payload, kind in artifact_writes:
        existed = path.exists()
        if existed and not force:
            actions.append({"path": str(path), "action": "skipped"})
            continue
        if kind == "json":
            write_json(path, payload)
        else:
            write_markdown(path, payload)
        actions.append(_path_action(path, existed))

    return {
        "status": "completed",
        "direction_id": proposal_id,
        "direction_name": profile["direction_name"],
        "actions": actions,
    }


def _purpose_for_screen(screen_id: str) -> str:
    lookup = {
        "app_shell": "global_navigation",
        "home": "primary_overview",
        "onboarding": "user_introduction",
        "detail": "contextual_detail",
        "profile": "account_preferences",
        "progress": "habit_progress",
        "paywall": "subscription_conversion",
    }
    return lookup.get(screen_id, "mobile_flow_step")


def _default_screen_ids(ideas: dict[str, Any], proposal_bundle: dict[str, Any] | None = None) -> list[str]:
    rationale = (proposal_bundle or {}).get("source_rationale", {})
    recommended = [
        entry.get("screen_id")
        for entry in rationale.get("recommended_screens", [])
        if isinstance(entry, dict) and entry.get("screen_id")
    ]
    ordered = []
    for screen_id in recommended:
        if screen_id not in ordered:
            ordered.append(screen_id)

    explicit = []
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
        if {"detail", "content", "card"} & categories:
            ordered.append("detail")
    if not ordered:
        ordered = ["home", "detail"]
    if "app_shell" not in ordered:
        ordered.insert(0, "app_shell")
    return ordered


SCREEN_STRUCTURE_PROFILES: dict[str, dict[str, dict[str, Any]]] = ORCHESTRATOR_CONFIG["screen_structure_profiles"]

def _screen_structure_profile(screen_id: str, proposal_bundle: dict[str, Any]) -> dict[str, Any]:
    direction_id = proposal_bundle.get("visual_language", {}).get("direction_id", "calm_editorial")
    direction_profile = SCREEN_STRUCTURE_PROFILES.get(direction_id, SCREEN_STRUCTURE_PROFILES["calm_editorial"])
    merged = dict(direction_profile.get("default", {}))
    merged.update(direction_profile.get(screen_id, {}))
    return merged


def _cta_label(screen_id: str, proposal_bundle: dict[str, Any]) -> str:
    direction_id = proposal_bundle.get("visual_language", {}).get("direction_id")
    labels = {
        "calm_editorial": {
            "onboarding": "Continue",
            "detail": "Keep going",
            "paywall": "Try premium",
        },
        "utility_bold": {
            "onboarding": "Set up",
            "detail": "Review",
            "paywall": "Upgrade now",
        },
        "playful_modular": {
            "onboarding": "Let's go",
            "detail": "Keep going",
            "paywall": "Unlock more",
        },
        "premium_cinematic": {
            "onboarding": "Enter",
            "detail": "Explore",
            "paywall": "Start membership",
        },
    }
    return labels.get(direction_id, {}).get(screen_id, "Continue")


def _screen_copy(
    screen_id: str,
    screen_ideas: list[dict[str, Any]],
    proposal_bundle: dict[str, Any],
    screen_guidance: dict[str, Any] | None,
    structure: dict[str, Any],
) -> tuple[str, str, str]:
    direction_name = proposal_bundle.get("visual_language", {}).get("direction_name", "Mobile design direction")
    title = direction_name
    body = "Refine this screen from the current proposal and canonical semantics."
    if screen_ideas:
        title = screen_ideas[0]["title"]
        body = screen_ideas[0].get("summary") or body
    elif screen_guidance:
        title = screen_guidance.get("story", title)
        body = (
            f"Carry {direction_name.lower()} through this screen with a {structure['layout_strategy'].replace('_', ' ')} "
            f"layout and {structure['chrome_density']} chrome."
        )

    if screen_id == "app_shell":
        title = "App shell and navigation"
        body = (
            f"Define persistent navigation with {structure['chrome_density']} chrome so it supports "
            f"{direction_name.lower()} without leaking extra complexity."
        )

    caption = (
        f"CTA posture: {structure['cta_posture'].replace('_', ' ')}. "
        f"Card usage: {structure['card_usage'].replace('_', ' ')}."
    )
    return title, body, caption


def _screen_motif_ids(screen_id: str, proposal_bundle: dict[str, Any], screen_guidance: dict[str, Any] | None) -> list[str]:
    guided = list(screen_guidance.get("primary_motifs", [])) if isinstance(screen_guidance, dict) else []
    if guided:
        return guided

    motifs = proposal_bundle.get("component_motifs", {}).get("motifs", [])
    matched = [
        motif.get("id")
        for motif in motifs
        if isinstance(motif, dict)
        and motif.get("id")
        and screen_id in motif.get("applicable_screens", [])
    ]
    if matched:
        return matched
    if motifs and isinstance(motifs[0], dict) and motifs[0].get("id"):
        return [motifs[0]["id"]]
    return ["primary_module"]


def _status_chip_label(screen_id: str, structure: dict[str, Any]) -> str:
    lookup = {
        "inline_action_strip": {
            "onboarding": "Fast setup",
            "home": "Live overview",
            "detail": "Decision ready",
            "paywall": "Conversion focus",
        },
        "progressive_reward": {
            "onboarding": "Starter win",
            "home": "Momentum loop",
            "detail": "Level up",
            "progress": "Streak ready",
        },
        "footer_single": {
            "onboarding": "Calm next step",
            "home": "Focused flow",
            "progress": "Gentle progress",
        },
        "delayed_footer": {
            "detail": "Curated focus",
            "paywall": "Premium framing",
        },
    }
    return lookup.get(structure["cta_posture"], {}).get(screen_id, "Focused context")


def _list_items(screen_id: str, body: str, primary_motif_label: str, structure: dict[str, Any]) -> list[str]:
    if screen_id == "home":
        return [
            f"{primary_motif_label.title()} anchors the first viewport",
            "Keep the main next action adjacent to live context",
            "Segment secondary modules so scanning stays fast",
        ]
    if screen_id == "detail":
        return [
            "Lead with the highest-value detail",
            f"Use {structure['card_usage'].replace('_', ' ')} for supporting context",
            "Keep tertiary actions out of the first fold",
        ]
    if screen_id == "paywall":
        return [
            "Frame value before pricing detail",
            "Keep comparison noise out of the opening moment",
            "Use one dominant conversion action",
        ]
    return [
        body,
        f"Primary motif: {primary_motif_label}",
        f"Chrome density: {structure['chrome_density']}",
    ]


def _progress_value(screen_id: str, structure: dict[str, Any]) -> float:
    if structure["cta_posture"] == "progressive_reward":
        return 0.68
    if screen_id in {"onboarding", "progress"}:
        return 0.42
    return 0.56


def _build_component_from_slot(
    slot: str,
    screen_id: str,
    title: str,
    body: str,
    caption: str,
    primary_motif_id: str,
    secondary_motif_ids: list[str],
    proposal_bundle: dict[str, Any],
    structure: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    primary_motif_label = primary_motif_id.replace("_", " ")
    secondary_motif_label = (
        secondary_motif_ids[0].replace("_", " ")
        if secondary_motif_ids
        else f"{primary_motif_label} support"
    )

    if slot == "title_display":
        return (
            {"id": f"{screen_id}_title", "kind": "text", "semantic_role": "app.display", "content": title},
            None,
        )
    if slot == "title":
        return (
            {"id": f"{screen_id}_title", "kind": "text", "semantic_role": "app.title", "content": title},
            None,
        )
    if slot == "body":
        return (
            {"id": f"{screen_id}_body", "kind": "text", "semantic_role": "app.body", "content": body},
            None,
        )
    if slot == "caption":
        return (
            {"id": f"{screen_id}_caption", "kind": "text", "semantic_role": "app.caption", "content": caption},
            None,
        )
    if slot == "status_chip":
        return (
            {"id": f"{screen_id}_status", "kind": "chip", "label": _status_chip_label(screen_id, structure)},
            None,
        )
    if slot == "badge_row":
        return (
            {"id": f"{screen_id}_badges", "kind": "badge", "content": f"{primary_motif_label.title()} reward row"},
            {
                "component_id": f"{screen_id}_badges",
                "motif_id": primary_motif_id,
                "purpose": "status accent",
            },
        )
    if slot == "progress":
        return (
            {
                "id": f"{screen_id}_progress",
                "kind": "progress",
                "label": f"{primary_motif_label.title()} progress",
                "value": _progress_value(screen_id, structure),
            },
            {
                "component_id": f"{screen_id}_progress",
                "motif_id": primary_motif_id,
                "purpose": "progress signal",
            },
        )
    if slot == "hero_card":
        return (
            {
                "id": f"{screen_id}_hero_card",
                "kind": "card",
                "semantic_role": "card.default",
                "content": primary_motif_label.title(),
            },
            {
                "component_id": f"{screen_id}_hero_card",
                "motif_id": primary_motif_id,
                "purpose": "anchor surface",
            },
        )
    if slot == "support_card":
        support_id = secondary_motif_ids[0] if secondary_motif_ids else primary_motif_id
        return (
            {
                "id": f"{screen_id}_support_card",
                "kind": "card",
                "semantic_role": "card.default",
                "content": secondary_motif_label.title(),
            },
            {
                "component_id": f"{screen_id}_support_card",
                "motif_id": support_id,
                "purpose": "supporting surface",
            },
        )
    if slot == "list":
        return (
            {
                "id": f"{screen_id}_list",
                "kind": "list",
                "items": _list_items(screen_id, body, primary_motif_label, structure),
            },
            None,
        )
    if slot == "divider":
        return ({"id": f"{screen_id}_divider", "kind": "divider"}, None)
    if slot == "cta":
        return (
            {
                "id": f"{screen_id}_primary",
                "kind": "button",
                "semantic_role": "button.primary",
                "label": _cta_label(screen_id, proposal_bundle),
            },
            None,
        )
    if slot == "placeholder":
        return (
            {
                "id": f"{screen_id}_hero_frame",
                "kind": "placeholder_block",
                "content": f"Immersive framing for {primary_motif_label}",
            },
            {
                "component_id": f"{screen_id}_hero_frame",
                "motif_id": primary_motif_id,
                "purpose": "framing block",
            },
        )
    return (
        {"id": f"{screen_id}_{slot}", "kind": "card", "semantic_role": "card.default", "content": primary_motif_label.title()},
        {
            "component_id": f"{screen_id}_{slot}",
            "motif_id": primary_motif_id,
            "purpose": "fallback motif surface",
        },
    )


def _screen_components(
    screen_id: str,
    screen_ideas: list[dict[str, Any]],
    proposal_bundle: dict[str, Any],
    screen_guidance: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    structure = _screen_structure_profile(screen_id, proposal_bundle)
    title, body, caption = _screen_copy(screen_id, screen_ideas, proposal_bundle, screen_guidance, structure)
    motif_ids = _screen_motif_ids(screen_id, proposal_bundle, screen_guidance)
    primary_motif_id = motif_ids[0]
    secondary_motif_ids = motif_ids[1:]
    components: list[dict[str, Any]] = []
    placement: list[dict[str, Any]] = []

    for slot in structure.get("slots", []):
        component, motif_placement = _build_component_from_slot(
            slot=slot,
            screen_id=screen_id,
            title=title,
            body=body,
            caption=caption,
            primary_motif_id=primary_motif_id,
            secondary_motif_ids=secondary_motif_ids,
            proposal_bundle=proposal_bundle,
            structure=structure,
        )
        components.append(component)
        if motif_placement is not None:
            placement.append(motif_placement)

    return components, {
        "layout_strategy": structure["layout_strategy"],
        "cta_posture": structure["cta_posture"],
        "chrome_density": structure["chrome_density"],
        "card_usage": structure["card_usage"],
        "motif_application": {
            "primary_motif": primary_motif_id,
            "secondary_motifs": secondary_motif_ids,
            "placement": placement,
        },
    }


def synthesize_screens(output_dir: Path, force: bool = False) -> dict[str, Any]:
    ideas = _required_json(output_dir / "ideas" / "index.json", "insufficient_inputs")
    proposal_bundle = _proposal_bundle(output_dir)
    brief = _required_json(output_dir / "contract" / "brief.json", "insufficient_inputs")
    inspirations = load_optional_json(output_dir / "inspirations" / "index.json") or {}
    screen_ids = _default_screen_ids(ideas, proposal_bundle=proposal_bundle)
    guidance_lookup = {
        entry.get("screen_id"): entry
        for entry in proposal_bundle.get("source_rationale", {}).get("recommended_screens", [])
        if isinstance(entry, dict) and entry.get("screen_id")
    }
    screens = []

    for screen_id in screen_ids:
        screen_ideas = [
            idea
            for idea in ideas.get("ideas", [])
            if screen_id in idea.get("target_screens", []) or (screen_id == "home" and not idea.get("target_screens"))
        ]
        source_urls = []
        for idea in screen_ideas:
            source_urls.extend(idea.get("source_urls", []))
        screen_guidance = guidance_lookup.get(screen_id, {})
        components, structure = _screen_components(screen_id, screen_ideas, proposal_bundle, screen_guidance)
        screens.append(
            {
                "screen_id": screen_id,
                "route": "/" + screen_id.replace("_", "-"),
                "purpose": _purpose_for_screen(screen_id),
                "layout_strategy": structure["layout_strategy"],
                "cta_posture": structure["cta_posture"],
                "chrome_density": structure["chrome_density"],
                "card_usage": structure["card_usage"],
                "motif_application": structure["motif_application"],
                "source_idea_ids": [idea["idea_id"] for idea in screen_ideas],
                "source_urls": sorted(set(source_urls)),
                "layout": {
                    "safe_area": True,
                    "scroll": "vertical",
                    "background_role": "surface.canvas",
                    "padding_role": "screen.padding.horizontal",
                },
                "data_bindings": {},
                "proposal_alignment": {
                    "direction_id": proposal_bundle["visual_language"]["direction_id"],
                    "primary_motifs": screen_guidance.get("primary_motifs", []),
                    "story": screen_guidance.get("story"),
                },
                "components": components,
                "states": [],
            }
        )

    screens_payload = {
        "contract_version": "1.0.0",
        "allowed_component_kinds": list(CANONICAL_COMPONENT_KINDS),
        "screen_rules": [
            "Use semantic roles instead of raw visual values.",
            "Favor one-thumb primary actions.",
            *proposal_bundle["visual_language"].get("composition_principles", []),
            "Use inspirations and linked ideas as rationale, not as direct platform markup.",
        ],
        "project": brief.get("project", {}).get("name"),
        "inspiration_summary": inspirations.get("summary", {}),
        "proposal_context": {
            "direction_id": proposal_bundle["visual_language"]["direction_id"],
            "direction_name": proposal_bundle["visual_language"]["direction_name"],
            "voice_name": proposal_bundle["typography_voice"]["voice_name"],
            "screen_structure_phase": "phase_4_screen_structure",
        },
        "screens": screens,
    }
    screen_path = output_dir / "screens" / "index.json"
    existed = screen_path.exists()
    if existed and not force:
        current = read_json(screen_path)
        if current.get("screens"):
            return {
                "status": "skipped",
                "screen_count": len(current.get("screens", [])),
                "actions": [{"path": str(screen_path), "action": "skipped"}],
            }
    write_json(screen_path, screens_payload)
    return {
        "status": "completed",
        "screen_count": len(screens),
        "actions": [_path_action(screen_path, existed)],
    }


def _used_roles_from_screens(screens: dict[str, Any], semantics: dict[str, Any], usage_scope: str) -> dict[str, set[str]]:
    text_roles = set()
    component_roles = set()
    color_roles = set()
    state_roles = set()
    layout_roles = set()

    if usage_scope == "all":
        text_roles = set(semantics.get("text_roles", {}).keys())
        component_roles = set(semantics.get("component_roles", {}).keys())
        for theme in semantics.get("themes", {}).values():
            color_roles.update(theme.get("color_roles", {}).keys())
        state_roles = set(semantics.get("state_roles", {}).keys())
        layout_roles = {"scroll.vertical", "stack.vertical", "stack.horizontal"}
        return {
            "text_roles": text_roles,
            "component_roles": component_roles,
            "color_roles": color_roles,
            "state_roles": state_roles,
            "layout_roles": layout_roles,
        }

    for screen in screens.get("screens", []):
        layout = screen.get("layout", {})
        if layout.get("scroll") == "vertical":
            layout_roles.add("scroll.vertical")
        if layout.get("background_role"):
            color_roles.add(layout["background_role"])
        for component in screen.get("components", []):
            kind = component.get("kind")
            role = component.get("semantic_role")
            if kind == "text" and role:
                text_roles.add(role)
            elif role:
                component_roles.add(role)
                semantics_role = semantics.get("component_roles", {}).get(role, {})
                for field in ("foreground", "background"):
                    if semantics_role.get(field):
                        color_roles.add(semantics_role[field])
                if role == "button.primary":
                    state_roles.update({"disabled.opacity", "pressed.scale"})
            if kind == "stack":
                layout_roles.add("stack.vertical")
            if kind == "list":
                layout_roles.add("stack.vertical")
            if kind == "nav_bar":
                layout_roles.add("nav.top_bar")
            if kind == "tab_bar":
                layout_roles.add("nav.tab_bar")
            if kind == "bottom_sheet":
                layout_roles.add("surface.bottom_sheet")
            if kind == "dialog":
                layout_roles.add("surface.dialog")
    return {
        "text_roles": text_roles,
        "component_roles": component_roles,
        "color_roles": color_roles,
        "state_roles": state_roles,
        "layout_roles": layout_roles,
    }


def emit_platform_mappings(
    output_dir: Path,
    platforms: list[str] | None = None,
    usage_scope: str = "used",
    gap_mode: str = "explicit",
    fail_on_gap: bool = False,
) -> dict[str, Any]:
    brief = _required_json(output_dir / "contract" / "brief.json", "insufficient_inputs")
    semantics = _required_json(output_dir / "contract" / "semantics.json", "insufficient_inputs")
    screens = _required_json(output_dir / "screens" / "index.json", "insufficient_inputs")
    proposal_bundle = _proposal_bundle(output_dir)
    requested_platforms = platforms or brief.get("platform_targets", [])
    usage = _used_roles_from_screens(screens, semantics, usage_scope)
    actions: list[dict[str, str]] = []
    emitted_files: list[str] = []
    all_gaps: list[dict[str, Any]] = []

    for platform in requested_platforms:
        base = default_platform_mapping(platform)
        existing = load_optional_json(output_dir / "platforms" / f"{platform}.json") or {}
        gaps: list[dict[str, Any]] = []

        typography_guidance = {
            key: value
            for key, value in base["typography_guidance"].items()
            if usage_scope == "all" or key in usage["text_roles"]
        }
        for role_name in usage["text_roles"]:
            if role_name not in typography_guidance:
                gap = {
                    "id": f"{platform}.typography.{role_name}",
                    "kind": "text_role",
                    "role": role_name,
                    "platform": platform,
                    "status": "unmapped",
                    "reason": "No platform typography guidance exists yet.",
                    "blocking": True,
                }
                gaps.append(gap)
                if gap_mode == "stub":
                    typography_guidance[role_name] = ""

        visual_guidance = {
            key: value
            for key, value in base["visual_guidance"].items()
            if usage_scope == "all" or key in usage["color_roles"]
        }
        for role_name in usage["color_roles"]:
            if role_name not in visual_guidance:
                gap = {
                    "id": f"{platform}.visual.{role_name}",
                    "kind": "semantic_role",
                    "role": role_name,
                    "platform": platform,
                    "status": "unmapped",
                    "reason": "No platform visual guidance exists yet.",
                    "blocking": True,
                }
                gaps.append(gap)
                if gap_mode == "stub":
                    visual_guidance[role_name] = ""

        component_guidance = {
            key: value
            for key, value in base["component_guidance"].items()
            if usage_scope == "all" or key in usage["component_roles"]
        }
        for role_name in usage["component_roles"]:
            if role_name not in component_guidance:
                gap = {
                    "id": f"{platform}.component.{role_name}",
                    "kind": "component_role",
                    "role": role_name,
                    "platform": platform,
                    "status": "unmapped",
                    "reason": "No platform component guidance exists yet.",
                    "blocking": True,
                }
                gaps.append(gap)
                if gap_mode == "stub":
                    component_guidance[role_name] = ""

        layout_guidance = {
            key: value
            for key, value in base["layout_guidance"].items()
            if usage_scope == "all" or key in usage["layout_roles"]
        }
        for layout_name in usage["layout_roles"]:
            if layout_name not in layout_guidance:
                gap = {
                    "id": f"{platform}.layout.{layout_name}",
                    "kind": "layout_role",
                    "role": layout_name,
                    "platform": platform,
                    "status": "unmapped",
                    "reason": "No platform layout guidance exists yet.",
                    "blocking": False,
                }
                gaps.append(gap)
                if gap_mode == "stub":
                    layout_guidance[layout_name] = ""

        interaction_guidance = {
            key: value
            for key, value in base["interaction_guidance"].items()
            if usage_scope == "all" or key in usage["state_roles"]
        }
        for role_name in usage["state_roles"]:
            if role_name not in interaction_guidance:
                gap = {
                    "id": f"{platform}.interaction.{role_name}",
                    "kind": "state_role",
                    "role": role_name,
                    "platform": platform,
                    "status": "unmapped",
                    "reason": "No platform interaction guidance exists yet.",
                    "blocking": False,
                }
                gaps.append(gap)
                if gap_mode == "stub":
                    interaction_guidance[role_name] = ""

        existing_gaps = existing.get("gaps", [])
        if gap_mode == "explicit" and existing_gaps:
            existing_lookup = {
                item.get("id"): item
                for item in existing_gaps
                if isinstance(item, dict) and item.get("id")
            }
            for gap in gaps:
                if gap["id"] in existing_lookup and existing_lookup[gap["id"]].get("reason"):
                    gap["reason"] = existing_lookup[gap["id"]]["reason"]

        mapping = {
            "platform": platform,
            "contract_version": brief.get("contract_version", "1.0.0"),
            "guidance_scope": usage_scope,
            "usage_summary": {
                "text_roles": sorted(usage["text_roles"]),
                "component_roles": sorted(usage["component_roles"]),
                "color_roles": sorted(usage["color_roles"]),
                "state_roles": sorted(usage["state_roles"]),
                "layout_roles": sorted(usage["layout_roles"]),
            },
            "proposal_context": {
                "direction_id": proposal_bundle["visual_language"]["direction_id"],
                "direction_name": proposal_bundle["visual_language"]["direction_name"],
            },
            "design_intent": {
                "summary": f"{proposal_bundle['visual_language']['direction_name']}: {base['design_intent']['summary']}",
                "principles": list(
                    dict.fromkeys(
                        proposal_bundle["visual_language"].get("composition_principles", [])[:2]
                        + base["design_intent"].get("principles", [])
                    )
                ),
            },
            "typography_guidance": typography_guidance,
            "visual_guidance": visual_guidance,
            "component_guidance": component_guidance,
            "layout_guidance": layout_guidance,
            "interaction_guidance": interaction_guidance,
            "asset_guidance": {
                "source_of_truth": (
                    f"Preserve the proposal direction `{proposal_bundle['visual_language']['direction_name']}` through the canonical contract. "
                    + base["asset_guidance"]["source_of_truth"]
                ),
                "production_asset_note": base["asset_guidance"]["production_asset_note"],
            },
            "implementation_notes": base["implementation_notes"]
            + [
                f"Typography voice: {proposal_bundle['typography_voice']['voice_name']}.",
                f"Keep the proposal motion posture intact: {proposal_bundle['visual_language']['motion_posture']}",
            ],
            "gaps": [] if gap_mode == "omit" else gaps,
        }

        platform_path = output_dir / "platforms" / f"{platform}.json"
        existed = platform_path.exists()
        write_json(platform_path, mapping)
        actions.append(_path_action(platform_path, existed))
        emitted_files.append(str(platform_path))
        all_gaps.extend(gaps)

    blocking_gaps = [gap for gap in all_gaps if gap.get("blocking")]
    status = "platform_mapping_incomplete" if blocking_gaps else "completed"
    if fail_on_gap and blocking_gaps:
        status = "failed"
    return {
        "status": status,
        "platforms": emitted_files,
        "usage_summary": {key: sorted(value) for key, value in usage.items()},
        "gaps": all_gaps,
        "actions": actions,
    }


def refresh_realization_plan(output_dir: Path, project_name: str | None = None) -> dict[str, Any]:
    inspirations = load_optional_json(output_dir / "inspirations" / "index.json") or {}
    ideas = load_optional_json(output_dir / "ideas" / "index.json") or {}
    proposal_visual = load_optional_json(output_dir / "proposal" / "visual_language.json") or {}
    proposal_signals = load_optional_json(output_dir / "proposal" / "design_signals.json") or {}
    proposal_options = load_optional_json(output_dir / "proposal" / "direction_options.json") or {}
    proposal_candidates = load_optional_json(output_dir / "proposal" / "proposal_candidates.json") or {}
    proposal_typography = load_optional_json(output_dir / "proposal" / "typography_voice.json") or {}
    proposal_motifs = load_optional_json(output_dir / "proposal" / "component_motifs.json") or {}
    proposal_rationale = load_optional_json(output_dir / "proposal" / "source_rationale.json") or {}
    brief = load_optional_json(output_dir / "contract" / "brief.json") or {}
    screens = load_optional_json(output_dir / "screens" / "index.json") or {}
    validation = load_optional_json(output_dir / "validation" / "report.json") or {}
    platforms = brief.get("platform_targets", list(DEFAULT_PLATFORMS))

    source_ready = inspirations.get("summary", {}).get("asset_count", 0) > 0
    idea_ready = len(ideas.get("ideas", [])) > 0
    proposal_ready = all(
        (
            proposal_signals.get("source_patterns"),
            proposal_options.get("selected_direction_id"),
            proposal_candidates.get("selected_direction_id"),
            proposal_visual.get("direction_id"),
            proposal_typography.get("voice_name"),
            proposal_motifs.get("motifs"),
            proposal_rationale.get("source_coverage"),
        )
    )
    contract_ready = all((output_dir / relative).exists() for relative in ("contract/brief.json", "contract/tokens.json", "contract/typography.json", "contract/semantics.json"))
    screen_count = len(screens.get("screens", []))
    platform_files = [output_dir / "platforms" / f"{platform}.json" for platform in platforms]
    platform_ready = all(path.exists() for path in platform_files)
    validation_status = validation.get("status")

    phases = [
        {
            "id": "intake",
            "name": "Inspiration intake",
            "status": "completed" if source_ready else "blocked",
            "deliverables": ["inspirations/index.json"],
            "evidence": {"asset_count": inspirations.get("summary", {}).get("asset_count", 0)},
        },
        {
            "id": "ideas",
            "name": "Idea capture",
            "status": "completed" if idea_ready else "in_progress",
            "deliverables": ["ideas/index.json"],
            "evidence": {"idea_count": len(ideas.get("ideas", []))},
        },
        {
            "id": "proposal",
            "name": "Opinionated design proposal",
            "status": "completed" if proposal_ready else "in_progress",
            "deliverables": [
                "proposal/design_direction.md",
                "proposal/design_signals.json",
                "proposal/direction_options.json",
                "proposal/proposal_candidates.json",
                "proposal/review_packet.md",
                "proposal/visual_language.json",
                "proposal/typography_voice.json",
                "proposal/component_motifs.json",
                "proposal/flow_narrative.md",
                "proposal/anti_patterns.md",
                "proposal/source_rationale.json",
            ],
            "evidence": {
                "direction_id": proposal_visual.get("direction_id"),
                "confidence": proposal_signals.get("confidence", {}).get("overall"),
                "selected_direction_id": proposal_options.get("selected_direction_id"),
                "candidate_count": proposal_candidates.get("candidate_count"),
            },
        },
        {
            "id": "contract",
            "name": "Canonical contract",
            "status": "completed" if contract_ready else "blocked",
            "deliverables": [
                "contract/brief.json",
                "contract/tokens.json",
                "contract/typography.json",
                "contract/semantics.json",
            ],
            "evidence": {"platform_targets": platforms},
        },
        {
            "id": "screens",
            "name": "Screen synthesis",
            "status": "completed" if screen_count > 0 else "in_progress",
            "deliverables": ["screens/index.json"],
            "evidence": {"screen_count": screen_count},
        },
        {
            "id": "platforms",
            "name": "Platform guidance",
            "status": "completed" if platform_ready else "blocked",
            "deliverables": [f"platforms/{platform}.json" for platform in platforms],
            "evidence": {"platform_count": len(platforms)},
        },
        {
            "id": "validation",
            "name": "Validation and review",
            "status": validation_status or "ready",
            "deliverables": ["validation/report.json"],
            "evidence": {"validation_status": validation_status},
        },
    ]

    next_actions = []
    blockers = []
    if not source_ready:
        blockers.append("Run inspiration intake from a valid design-scraper output.")
    if not idea_ready:
        next_actions.append("Capture idea cards linked to inspiration URLs or assets.")
    if not proposal_ready:
        next_actions.append("Generate an opinionated proposal before refining the contract.")
    if screen_count == 0:
        next_actions.append("Run screen synthesis and refine the generated mobile-first screens.")
    if validation_status in {"warning", "failed"}:
        next_actions.append("Resolve validation findings before implementation handoff.")
    if validation_status == "passed" and screen_count > 0:
        next_actions.append("Use the validated contract as the source of truth for Flutter, SwiftUI, and Compose implementation.")

    overall_status = "ready_for_implementation" if validation_status == "passed" and proposal_ready and screen_count > 0 else "in_progress"
    plan = {
        "project": project_name or brief.get("project", {}).get("name") or output_dir.name,
        "updated_at": now_iso(),
        "status": overall_status,
        "principle": "Canonical contract before platform code.",
        "phases": phases,
        "blockers": blockers,
        "next_actions": next_actions,
    }
    plan_path = output_dir / "realization" / "plan.json"
    existed = plan_path.exists()
    write_json(plan_path, plan)
    return {"status": "completed", "plan": plan, "actions": [_path_action(plan_path, existed)]}


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
    for relative_dir in ("inspirations", "ideas", "proposal", "contract", "screens", "platforms", "metadata", "realization", "preview", "validation"):
        ensure_dir(output_dir / relative_dir)

    project_slug = slugify(project_name)
    validation_report = None

    try:
        if "ingest" in phases:
            if scrape_root is None:
                raise ValueError("scrape_input_missing: --scrape-root is required for the ingest phase")
            ingest_result = ingest_inspiration(
                output_dir=output_dir,
                scrape_root=scrape_root,
                project_name=project_name,
                force=force,
            )
            actions.extend(ingest_result["actions"])

        if "ideas" in phases:
            scaffold_json(output_dir / "ideas" / "index.json", default_ideas(project_slug), actions, force=force)

        inspirations = load_optional_json(output_dir / "inspirations" / "index.json")
        if "proposal" in phases:
            proposal_result = synthesize_proposal(output_dir=output_dir, project_name=project_name, force=force)
            actions.extend(proposal_result["actions"])

        if "contract" in phases:
            proposal_bundle = _proposal_bundle(output_dir)
            scaffold_json(
                output_dir / "contract" / "brief.json",
                default_brief(
                    project_name,
                    project_slug,
                    platforms,
                    inspirations.get("summary") if inspirations else None,
                    product_summary,
                    proposal_bundle=proposal_bundle,
                ),
                actions,
                force=force,
            )
            scaffold_json(output_dir / "contract" / "tokens.json", default_tokens(proposal_bundle=proposal_bundle), actions, force=force)
            scaffold_json(output_dir / "contract" / "typography.json", default_typography(proposal_bundle=proposal_bundle), actions, force=force)
            scaffold_json(output_dir / "contract" / "semantics.json", default_semantics(proposal_bundle=proposal_bundle), actions, force=force)

        if "screens" in phases:
            screen_result = synthesize_screens(output_dir=output_dir, force=force)
            actions.extend(screen_result["actions"])

        if "platforms" in phases:
            mapping_result = emit_platform_mappings(output_dir=output_dir, platforms=platforms)
            actions.extend(mapping_result["actions"])

        if "plan" in phases:
            plan_result = refresh_realization_plan(output_dir=output_dir, project_name=project_name)
            actions.extend(plan_result["actions"])

        inspirations = load_optional_json(output_dir / "inspirations" / "index.json")
        preview_path = output_dir / "preview" / "summary.md"
        existed = preview_path.exists()
        write_markdown(preview_path, preview_summary(project_name, output_dir, platforms, inspirations.get("summary") if inspirations else None))
        actions.append(_path_action(preview_path, existed))

        if "validate" in phases:
            validation_report = validate_output_dir(output_dir, required_platforms=platforms)
            report_path = output_dir / "validation" / "report.json"
            existed = report_path.exists()
            write_json(report_path, validation_report)
            actions.append(_path_action(report_path, existed))
            markdown_path = output_dir / "validation" / "report.md"
            existed = markdown_path.exists()
            write_markdown(markdown_path, validation_markdown(validation_report))
            actions.append(_path_action(markdown_path, existed))
            if "plan" in phases:
                plan_result = refresh_realization_plan(output_dir=output_dir, project_name=project_name)
                actions.extend(plan_result["actions"])

        status = "completed" if not validation_report or validation_report["status"] != "failed" else "failed"
    except Exception as exc:
        status = "failed"
        message = str(exc)
        code = "pipeline_failed"
        if ": " in message:
            prefix, remainder = message.split(": ", 1)
            if prefix and all(ch.islower() or ch == "_" for ch in prefix):
                code = prefix
                message = remainder
        validation_report = {"status": "failed", "errors": [{"code": code, "message": message}], "warnings": [], "checks": {}}
        report_path = output_dir / "validation" / "report.json"
        report_existed = report_path.exists()
        write_json(report_path, validation_report)
        markdown_path = output_dir / "validation" / "report.md"
        markdown_existed = markdown_path.exists()
        write_markdown(markdown_path, validation_markdown(validation_report))
        actions.append(_path_action(report_path, report_existed))
        actions.append(_path_action(markdown_path, markdown_existed))

    completed_at = now_iso()
    run_report = {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
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
                "proposal": {
                    "design_direction": "proposal/design_direction.md",
                    "design_signals": "proposal/design_signals.json",
                    "direction_options": "proposal/direction_options.json",
                    "proposal_candidates": "proposal/proposal_candidates.json",
                    "review_packet": "proposal/review_packet.md",
                    "visual_language": "proposal/visual_language.json",
                    "typography_voice": "proposal/typography_voice.json",
                    "component_motifs": "proposal/component_motifs.json",
                    "flow_narrative": "proposal/flow_narrative.md",
                    "anti_patterns": "proposal/anti_patterns.md",
                    "source_rationale": "proposal/source_rationale.json",
                },
                "brief": "contract/brief.json",
                "tokens": "contract/tokens.json",
                "typography": "contract/typography.json",
                "semantics": "contract/semantics.json",
                "screens": "screens/index.json",
                "platforms": [f"platforms/{platform}.json" for platform in platforms],
                "plan": "realization/plan.json",
                "preview": "preview/summary.md",
                "validation": "validation/report.json",
            },
        },
    )
    return run_report

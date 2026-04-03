from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from mobile_design_orchestrator.analysis_types import ANALYSIS_SCHEMA_VERSION, artifact_envelope, lineage_for_asset, stable_fingerprint
from mobile_design_orchestrator.project import ensure_dir, load_optional_json, now_iso, read_json, write_json
from mobile_design_orchestrator.v2_runtime import build_artifact_version_metadata

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow is optional.
    Image = None

PURPOSE_KEYWORDS = {
    "onboarding": ("welcome", "intro", "onboard", "coach", "setup", "start"),
    "dashboard": ("dashboard", "today", "home", "summary", "stats", "progress", "metrics"),
    "detail": ("detail", "session", "program", "entry", "item", "article", "meal"),
    "form": ("form", "input", "entry", "log", "search", "scan", "edit", "add"),
    "profile": ("profile", "account", "settings", "membership", "plan"),
    "navigation": ("tab", "menu", "browse", "discover", "library", "feed"),
}

COMPONENT_KEYWORDS = {
    "nav_bar": ("nav", "navigation", "tab", "menu"),
    "button": ("button", "cta", "continue", "start", "next", "save"),
    "list": ("list", "feed", "library", "history"),
    "card": ("card", "summary", "tile", "widget"),
    "progress": ("progress", "ring", "gauge", "meter", "stats"),
    "text_field": ("search", "field", "input", "log", "scan"),
}


def _asset_text(source: dict[str, Any], asset: dict[str, Any]) -> str:
    fragments: list[str] = [
        source.get("source") or "",
        source.get("title") or "",
        source.get("author") or "",
        source.get("source_url") or "",
        asset.get("canonical_url") or "",
        asset.get("relative_path") or "",
        asset.get("mime_type") or "",
        asset.get("kind") or "",
    ]
    metadata = asset.get("metadata") or {}
    if isinstance(metadata, dict):
        fragments.extend(f"{key}:{value}" for key, value in sorted(metadata.items()))
    return " ".join(fragment for fragment in fragments if fragment).lower()


def _load_dimensions(asset: dict[str, Any]) -> tuple[int | None, int | None]:
    width = asset.get("width")
    height = asset.get("height")
    if width and height:
        return int(width), int(height)
    local_path = asset.get("local_path")
    if not local_path or Image is None:
        return None, None
    try:
        with Image.open(local_path) as image:
            return image.size
    except Exception:
        return None, None


def _infer_purpose(text: str, width: int | None, height: int | None) -> str:
    for purpose, keywords in PURPOSE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return purpose
    if width and height and height >= width * 1.5:
        return "dashboard"
    return "reference"


def _infer_component_tags(text: str, purpose: str) -> list[str]:
    tags = {purpose}
    for component, keywords in COMPONENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.add(component)
    if purpose in {"dashboard", "detail"}:
        tags.add("card")
    if purpose == "navigation":
        tags.add("nav_bar")
    if purpose == "form":
        tags.add("text_field")
        tags.add("button")
    return sorted(tags)


def _layout_regions(asset_id: str, width: int | None, height: int | None, purpose: str) -> list[dict[str, Any]]:
    if not width or not height:
        return [
            {
                "region_id": f"{asset_id}:canvas",
                "kind": "canvas",
                "bbox_normalized": [0.0, 0.0, 1.0, 1.0],
                "confidence": 0.2,
                "derived_from": "missing_dimensions",
            }
        ]

    body_top = 0.18 if purpose in {"dashboard", "detail"} else 0.22
    footer_top = 0.84 if height >= width * 1.5 else 0.9
    return [
        {
            "region_id": f"{asset_id}:header",
            "kind": "header_region",
            "bbox_normalized": [0.0, 0.0, 1.0, round(body_top, 2)],
            "confidence": 0.45,
            "derived_from": "aspect_ratio_heuristic",
        },
        {
            "region_id": f"{asset_id}:body",
            "kind": "body_region",
            "bbox_normalized": [0.0, round(body_top, 2), 1.0, round(footer_top, 2)],
            "confidence": 0.45,
            "derived_from": "aspect_ratio_heuristic",
        },
        {
            "region_id": f"{asset_id}:footer",
            "kind": "footer_region",
            "bbox_normalized": [0.0, round(footer_top, 2), 1.0, 1.0],
            "confidence": 0.35,
            "derived_from": "aspect_ratio_heuristic",
        },
    ]


def analyze_inspirations(
    inspirations: dict[str, Any],
    *,
    run_id: str,
    workspace_version: str = "v2",
) -> dict[str, dict[str, Any]]:
    generated_at = now_iso()
    project = inspirations.get("project") or "mobile-project"
    source_count = len(inspirations.get("sources", []))
    base_metadata = build_artifact_version_metadata(
        phase="analysis",
        run_id=run_id,
        generated_at=generated_at,
        workspace_version=workspace_version,
        schema_version=ANALYSIS_SCHEMA_VERSION,
    )
    base_metadata["source_count"] = source_count

    manifest_records: list[dict[str, Any]] = []
    ocr_records: list[dict[str, Any]] = []
    layout_records: list[dict[str, Any]] = []
    component_records: list[dict[str, Any]] = []
    embedding_records: list[dict[str, Any]] = []

    for source in inspirations.get("sources", []):
        for asset in source.get("assets", []):
            duplicate = asset.get("duplicate") or {}
            included = duplicate.get("included", True)
            if not included:
                continue
            width, height = _load_dimensions(asset)
            text = _asset_text(source, asset)
            purpose = _infer_purpose(text, width, height)
            component_tags = _infer_component_tags(text, purpose)
            lineage = lineage_for_asset(source, asset)
            aspect_ratio = round(height / width, 3) if width and height else None
            manifest_records.append(
                {
                    **lineage,
                    "kind": asset.get("kind"),
                    "mime_type": asset.get("mime_type"),
                    "width": width,
                    "height": height,
                    "aspect_ratio": aspect_ratio,
                    "purpose_guess": purpose,
                    "component_tags": component_tags,
                    "duplicate": duplicate,
                    "fallback_screenshot": asset.get("fallback_screenshot", False),
                    "warnings": list(asset.get("warnings", [])),
                }
            )
            ocr_records.append(
                {
                    **lineage,
                    "status": "not_run",
                    "engine": None,
                    "text_blocks": [],
                    "line_count": 0,
                    "confidence": None,
                    "notes": ["OCR not yet implemented in the deterministic analysis baseline."],
                }
            )
            layout_records.append(
                {
                    **lineage,
                    "purpose_guess": purpose,
                    "regions": _layout_regions(asset.get("asset_id") or "asset", width, height, purpose),
                }
            )
            component_records.append(
                {
                    **lineage,
                    "purpose_guess": purpose,
                    "component_tags": component_tags,
                    "rationale": f"Derived from purpose={purpose} and keyword heuristics.",
                }
            )
            embedding_records.append(
                {
                    **lineage,
                    "embedding_status": "not_run",
                    "embedding_model": None,
                    "fingerprint_sha256": stable_fingerprint(
                        source.get("source_url"),
                        asset.get("asset_id"),
                        purpose,
                        ",".join(component_tags),
                    ),
                    "token_basis": stable_fingerprint(text)[:16],
                }
            )

    return {
        "screen_manifest": artifact_envelope(
            project=project,
            artifact_type="screen_manifest",
            generated_at=generated_at,
            records=manifest_records,
            metadata={**base_metadata, "component_tag_counts": dict(Counter(tag for record in manifest_records for tag in record.get("component_tags", [])))},
        ),
        "ocr": artifact_envelope(
            project=project,
            artifact_type="ocr",
            generated_at=generated_at,
            records=ocr_records,
            metadata={**base_metadata, "engine": None},
        ),
        "layout_regions": artifact_envelope(
            project=project,
            artifact_type="layout_regions",
            generated_at=generated_at,
            records=layout_records,
            metadata=base_metadata,
        ),
        "component_tags": artifact_envelope(
            project=project,
            artifact_type="component_tags",
            generated_at=generated_at,
            records=component_records,
            metadata=base_metadata,
        ),
        "screen_embeddings": artifact_envelope(
            project=project,
            artifact_type="screen_embeddings",
            generated_at=generated_at,
            records=embedding_records,
            metadata={**base_metadata, "embedding_status": "not_run"},
        ),
    }


def write_analysis_artifacts(
    output_dir: Path,
    *,
    run_id: str,
    workspace_version: str = "v2",
) -> dict[str, Any]:
    inspirations_path = output_dir / "inspirations" / "index.json"
    if not inspirations_path.exists():
        raise FileNotFoundError(f"analysis_input_missing: missing file {inspirations_path}")
    inspirations = read_json(inspirations_path)
    if not isinstance(inspirations, dict):
        raise ValueError(f"analysis_input_invalid: expected object in {inspirations_path}")

    ensure_dir(output_dir / "analysis")
    bundle = analyze_inspirations(inspirations, run_id=run_id, workspace_version=workspace_version)
    actions: list[dict[str, str]] = []
    for artifact_name, data in bundle.items():
        path = output_dir / "analysis" / f"{artifact_name}.json"
        existed = path.exists()
        write_json(path, data)
        actions.append({"path": str(path), "action": "updated" if existed else "created"})
    return {
        "actions": actions,
        "artifact_count": len(bundle),
        "record_count": sum(item.get("record_count", 0) for item in bundle.values()),
        "artifacts": {name: f"analysis/{name}.json" for name in bundle},
    }

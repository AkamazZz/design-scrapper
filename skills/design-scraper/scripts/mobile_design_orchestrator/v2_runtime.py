from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

V2_PHASE_ORDER = ("analysis", "ideas", "proposal", "screen_briefs", "screen_variants", "critic")

V2_PHASE_LABELS = {
    "analysis": "Analysis",
    "ideas": "Ideas",
    "proposal": "Proposal",
    "screen_briefs": "Screen Briefs",
    "screen_variants": "Screen Variants",
    "critic": "Critic",
}

V2_PHASE_FLAGS = {
    "analysis": "DESIGN_SCRAPER_V2_ENABLE_ANALYSIS",
    "ideas": "DESIGN_SCRAPER_V2_ENABLE_IDEAS",
    "proposal": "DESIGN_SCRAPER_V2_ENABLE_PROPOSAL",
    "screen_briefs": "DESIGN_SCRAPER_V2_ENABLE_SCREEN_BRIEFS",
    "screen_variants": "DESIGN_SCRAPER_V2_ENABLE_SCREEN_VARIANTS",
    "critic": "DESIGN_SCRAPER_V2_ENABLE_CRITIC",
}

V2_PHASE_ARTIFACT_FAMILIES = {
    "analysis": ("analysis",),
    "ideas": ("ideas",),
    "proposal": ("proposal",),
    "screen_briefs": ("screen_briefs",),
    "screen_variants": ("screen_variants", "screens"),
    "critic": ("review", "validation"),
}


def normalize_v2_phase(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "screen_brief": "screen_briefs",
        "screen_variant": "screen_variants",
        "variants": "screen_variants",
        "briefs": "screen_briefs",
        "review": "critic",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in V2_PHASE_ORDER:
        raise ValueError(f"unknown_v2_phase: {value}")
    return normalized


def parse_flag_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def parse_v2_phase_flags(
    raw: Mapping[str, object] | Iterable[str] | str | None = None,
    env: Mapping[str, str] | None = None,
    default_enabled: bool = False,
) -> dict[str, bool]:
    flags = {phase: default_enabled for phase in V2_PHASE_ORDER}
    if isinstance(raw, Mapping):
        for key, value in raw.items():
            try:
                flags[normalize_v2_phase(key)] = parse_flag_bool(value, flags.get(normalize_v2_phase(key), default_enabled))
            except ValueError:
                continue
    elif isinstance(raw, str):
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                flags[normalize_v2_phase(token)] = True
            except ValueError:
                continue
    elif raw is not None:
        for item in raw:
            try:
                flags[normalize_v2_phase(str(item))] = True
            except ValueError:
                continue

    env = env or os.environ
    for phase, env_key in V2_PHASE_FLAGS.items():
        if env_key in env:
            flags[phase] = parse_flag_bool(env.get(env_key), flags[phase])
    return flags


def enabled_v2_phases(flags: Mapping[str, bool]) -> tuple[str, ...]:
    return tuple(phase for phase in V2_PHASE_ORDER if flags.get(phase))


def resolve_workspace_version(existing_version: str | None = None, flags: Mapping[str, bool] | None = None) -> str:
    if existing_version in {"v1", "v2"}:
        if existing_version == "v2":
            return "v2"
        if flags and any(flags.get(phase, False) for phase in V2_PHASE_ORDER):
            return "v2"
        return existing_version
    if flags and any(flags.get(phase, False) for phase in V2_PHASE_ORDER):
        return "v2"
    return "v1"


def build_artifact_version_metadata(
    *,
    phase: str,
    run_id: str,
    generated_at: str,
    workspace_version: str,
    schema_version: str = "2.0.0",
    producer: str = "design-scraper-v2",
    producer_version: str = "0.1.0",
    status: str = "completed",
    artifact_version: str = "1",
) -> dict[str, Any]:
    return {
        "phase": normalize_v2_phase(phase),
        "schema_version": schema_version,
        "producer": producer,
        "producer_version": producer_version,
        "artifact_version": artifact_version,
        "generated_at": generated_at,
        "run_id": run_id,
        "workspace_version": workspace_version,
        "status": status,
    }


def make_phase_winner(
    phase: str,
    *,
    enabled: bool,
    winning_path: str,
    details: Mapping[str, Any] | None = None,
    artifacts: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_v2_phase(phase)
    return {
        "enabled": enabled,
        "flag": V2_PHASE_FLAGS[normalized],
        "winning_path": winning_path,
        "fallbacks": [],
        "artifacts": list(artifacts or ()),
        "details": dict(details or {}),
    }


def make_phase_fallback(
    phase: str,
    *,
    enabled: bool,
    winning_path: str,
    reason: str,
    fallback_target: str,
    details: Mapping[str, Any] | None = None,
    artifacts: Iterable[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_v2_phase(phase)
    return {
        "enabled": enabled,
        "flag": V2_PHASE_FLAGS[normalized],
        "winning_path": winning_path,
        "fallbacks": [
            {
                "reason": reason,
                "fallback_target": fallback_target,
                "details": dict(details or {}),
            }
        ],
        "artifacts": list(artifacts or ()),
        "details": dict(details or {}),
    }


def empty_phase_records(flags: Mapping[str, bool] | None = None) -> dict[str, dict[str, Any]]:
    flags = flags or {}
    return {
        phase: {
            "enabled": bool(flags.get(phase, False)),
            "flag": V2_PHASE_FLAGS[phase],
            "winning_path": None,
            "fallbacks": [],
            "artifacts": [],
            "details": {},
        }
        for phase in V2_PHASE_ORDER
    }


def build_workspace_version_metadata(
    *,
    workspace_version: str,
    flags: Mapping[str, bool] | None = None,
    phase_records: Mapping[str, Mapping[str, Any]] | None = None,
    producer_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    flags = flags or {}
    phase_records = phase_records or {}
    producer_versions = producer_versions or {}
    return {
        "workspace_version": resolve_workspace_version(workspace_version, flags),
        "enabled_flags": {phase: bool(flags.get(phase, False)) for phase in V2_PHASE_ORDER},
        "enabled_phases": list(enabled_v2_phases(flags)),
        "phase_records": {phase: dict(phase_records.get(phase, {})) for phase in V2_PHASE_ORDER},
        "producer_versions": dict(producer_versions),
    }

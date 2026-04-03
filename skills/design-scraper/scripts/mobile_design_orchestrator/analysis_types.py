from __future__ import annotations

import hashlib
from typing import Any

ANALYSIS_SCHEMA_VERSION = "2.0.0"


def stable_fingerprint(*parts: object) -> str:
    normalized = "||".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def artifact_envelope(
    *,
    project: str,
    artifact_type: str,
    generated_at: str,
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "project": project,
        "artifact_type": artifact_type,
        "generated_at": generated_at,
        "record_count": len(records),
        "metadata": metadata,
        "records": records,
    }


def lineage_for_asset(source: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_key": source.get("source_key"),
        "source_url": source.get("source_url"),
        "asset_id": asset.get("asset_id"),
        "relative_path": asset.get("relative_path"),
        "local_path": asset.get("local_path"),
    }

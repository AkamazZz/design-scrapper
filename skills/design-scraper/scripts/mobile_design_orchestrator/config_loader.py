from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "orchestrator_policies.v1.json"
REQUIRED_TOP_LEVEL_KEYS = (
    "config_version",
    "proposal_archetypes",
    "signal_clusters",
    "screen_structure_profiles",
    "screen_effect_profiles",
    "validation_policies",
)


@lru_cache(maxsize=1)
def load_orchestrator_config() -> dict[str, Any]:
    data = json.loads(CONFIG_PATH.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {CONFIG_PATH}")
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in data]
    if missing:
        raise ValueError(f"missing config keys in {CONFIG_PATH}: {', '.join(missing)}")
    return data

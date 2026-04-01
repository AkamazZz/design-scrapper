from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RunSummary


def _default_manifest() -> dict[str, Any]:
    return {
        "version": 1,
        "downloaded_urls": {},
        "content_hashes": {},
        "assets": {},
        "runs": [],
    }


class ManifestStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = _default_manifest()

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
        else:
            self.data = _default_manifest()
        return self.data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")

    def record_asset(self, asset: dict[str, Any]) -> None:
        canonical_url = asset["canonical_url"]
        local_path = asset["local_path"]
        self.data["downloaded_urls"][canonical_url] = local_path
        if asset.get("sha256"):
            self.data["content_hashes"][asset["sha256"]] = local_path
        self.data["assets"][local_path] = asset

    def append_run(self, summary: RunSummary) -> None:
        self.data["runs"].append(summary.to_dict())


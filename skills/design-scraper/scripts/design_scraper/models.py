from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class AssetRecord:
    source_url: str
    canonical_url: str
    local_path: str
    kind: str
    status: str = "pending"
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    file_size: int | None = None
    fallback_screenshot: bool = False
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScrapeResult:
    source: str
    url: str
    normalized_url: str
    title: str | None = None
    author: str | None = None
    status: str = "pending"
    assets: list[AssetRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["assets"] = [asset.to_dict() for asset in self.assets]
        return payload


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    completed_at: str | None
    output_dir: str
    project: str | None
    tags: list[str]
    urls: list[str]
    adapter_results: list[ScrapeResult] = field(default_factory=list)
    post_processing: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_dir": self.output_dir,
            "project": self.project,
            "tags": self.tags,
            "urls": self.urls,
            "adapter_results": [result.to_dict() for result in self.adapter_results],
            "post_processing": self.post_processing,
        }


@dataclass
class OutputLayout:
    root: Path
    raw_dir: Path
    normalized_dir: Path
    metadata_dir: Path
    preview_path: Path
    manifest_path: Path
    run_report_path: Path


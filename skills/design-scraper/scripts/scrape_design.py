#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from design_scraper.adapters import build_default_registry
from design_scraper.adapters.base import ScrapeContext
from design_scraper.downloads import DownloadManager
from design_scraper.fetchers import build_fetcher
from design_scraper.manifest import ManifestStore
from design_scraper.models import OutputLayout, RunSummary, utc_now_iso
from design_scraper.normalize import detect_source, normalize_url


SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated design inspiration scraper.")
    parser.add_argument("urls", nargs="+", help="Design inspiration URLs to process")
    parser.add_argument("--output-dir", default="~/design_scrapped/initial", help="Root output directory")
    parser.add_argument("--project", help="Optional project subdirectory")
    parser.add_argument("--tag", action="append", default=[], dest="tags", help="Optional tag to store in metadata")
    parser.add_argument(
        "--fetch-variant",
        default="playwright",
        choices=["playwright", "crawl4ai", "http"],
        help="HTML acquisition backend. Playwright is the default; crawl4ai is the alternate backend; http is an explicit fallback/debug option.",
    )
    parser.add_argument("--dedupe-threshold", type=int, default=25, help="Perceptual dedupe threshold")
    parser.add_argument("--skip-post-process", action="store_true", help="Skip colors, dedupe, and preview generation")
    return parser.parse_args()


def build_layout(output_root: str, project: str | None, run_id: str) -> OutputLayout:
    root = Path(output_root).expanduser()
    if project:
        root = root / project
    metadata_dir = root / "metadata"
    return OutputLayout(
        root=root,
        raw_dir=root / "raw",
        normalized_dir=root / "normalized",
        metadata_dir=metadata_dir,
        preview_path=root / "preview.html",
        manifest_path=metadata_dir / "index.json",
        run_report_path=metadata_dir / f"run_{run_id}.json",
    )


def ensure_layout(layout: OutputLayout) -> None:
    for path in (layout.root, layout.raw_dir, layout.normalized_dir, layout.metadata_dir):
        path.mkdir(parents=True, exist_ok=True)


def run_post_processing(layout: OutputLayout, threshold: int) -> list[dict[str, str | int]]:
    commands = [
        ["python3", str(SCRIPT_DIR / "extract_colors.py"), str(layout.root)],
        ["python3", str(SCRIPT_DIR / "dedup.py"), str(layout.root), str(threshold)],
        ["python3", str(SCRIPT_DIR / "preview_grid.py"), str(layout.root)],
    ]
    results = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True)
        results.append(
            {
                "command": " ".join(command),
                "exit_code": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            }
        )
    return results


def main() -> int:
    args = parse_args()
    run_id = uuid.uuid4().hex[:12]
    layout = build_layout(args.output_dir, args.project, run_id)
    ensure_layout(layout)

    manifest = ManifestStore(layout.manifest_path)
    manifest.load()

    summary = RunSummary(
        run_id=run_id,
        started_at=utc_now_iso(),
        completed_at=None,
        output_dir=str(layout.root),
        project=args.project,
        tags=args.tags,
        urls=args.urls,
    )
    summary.post_processing.append({"requested_fetch_variant": args.fetch_variant})

    context = ScrapeContext(
        layout=layout,
        project=args.project,
        tags=args.tags,
        run_id=run_id,
        downloader=DownloadManager(),
        fetcher=build_fetcher(args.fetch_variant),
    )
    registry = build_default_registry()

    for original_url in args.urls:
        normalized_url = normalize_url(original_url)
        source = detect_source(normalized_url)
        adapter = registry.select(source, normalized_url)
        if adapter is None:
            from design_scraper.models import ScrapeResult

            result = ScrapeResult(
                source=source or "unknown",
                url=original_url,
                normalized_url=normalized_url,
                status="unsupported_source",
                warnings=["No adapter matched this URL."],
            )
        else:
            result = adapter.scrape(normalized_url, context)
            result.url = original_url
            result.normalized_url = normalized_url
        summary.adapter_results.append(result)
        for asset in result.assets:
            manifest.record_asset(asset.to_dict())

    if not args.skip_post_process:
        summary.post_processing = run_post_processing(layout, args.dedupe_threshold)

    summary.completed_at = utc_now_iso()
    manifest.append_run(summary)
    manifest.save()
    layout.run_report_path.write_text(json.dumps(summary.to_dict(), indent=2) + "\n")

    print(json.dumps(summary.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

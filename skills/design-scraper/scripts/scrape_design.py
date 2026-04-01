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
PLUGIN_ROOT = SCRIPT_DIR.parents[2]


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    env = _load_dotenv(PLUGIN_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Automated design inspiration scraper.")
    parser.add_argument("urls", nargs="+", help="Design inspiration URLs to process")
    parser.add_argument(
        "--output-dir",
        default=env.get("DEFAULT_OUTPUT_DIR", "~/design_scrapped/initial"),
        help="Root output directory",
    )
    parser.add_argument("--project", help="Optional project subdirectory")
    parser.add_argument("--tag", action="append", default=[], dest="tags", help="Optional tag to store in metadata")
    parser.add_argument(
        "--fetch-variant",
        default=env.get("FETCH_VARIANT", "playwright"),
        choices=["playwright", "crawl4ai", "http"],
        help="HTML acquisition backend. Playwright is the default; crawl4ai is the alternate backend; http is an explicit fallback/debug option.",
    )
    parser.add_argument(
        "--playwright-user-data-dir",
        default=env.get("PLAYWRIGHT_USER_DATA_DIR"),
        help="Optional persistent Playwright profile directory for session reuse. Keep it outside the repo and restricted to your user.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        default=_env_bool(env.get("PLAYWRIGHT_HEADED"), default=False),
        help="Launch Playwright in headed mode. Use this for first-time manual login flows.",
    )
    parser.add_argument(
        "--dedupe-threshold",
        type=int,
        default=int(env.get("DEDUPE_THRESHOLD", "25")),
        help="Perceptual dedupe threshold",
    )
    parser.add_argument(
        "--skip-post-process",
        action="store_true",
        default=_env_bool(env.get("SKIP_POST_PROCESS"), default=False),
        help="Skip colors, dedupe, and preview generation",
    )
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


def summarize_run_status(summary: RunSummary) -> int:
    adapter_failures = [
        result for result in summary.adapter_results if result.status in {"fetch_failed", "download_failed", "auth_required"}
    ]
    post_process_failures = [
        step for step in summary.post_processing if isinstance(step, dict) and step.get("exit_code", 0) not in (0, None)
    ]

    if post_process_failures:
        summary.status = "partial_success"
        summary.warnings.append("One or more post-processing steps failed.")
        return 2
    if adapter_failures and len(adapter_failures) == len(summary.adapter_results):
        summary.status = "failed"
        summary.warnings.append("All source scrapes failed.")
        return 1
    if adapter_failures:
        summary.status = "partial_success"
        summary.warnings.append("Some source scrapes failed.")
        return 0

    summary.status = "completed"
    return 0


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
        status="running",
        output_dir=str(layout.root),
        project=args.project,
        tags=args.tags,
        urls=args.urls,
    )
    summary.post_processing.append({"requested_fetch_variant": args.fetch_variant})
    if args.playwright_user_data_dir:
        summary.post_processing.append(
            {"playwright_user_data_dir": str(Path(args.playwright_user_data_dir).expanduser())}
        )
    if args.headed:
        summary.post_processing.append({"headed": True})

    fetcher = build_fetcher(
        args.fetch_variant,
        playwright_user_data_dir=args.playwright_user_data_dir,
        playwright_headed=args.headed,
    )
    context = ScrapeContext(
        layout=layout,
        project=args.project,
        tags=args.tags,
        run_id=run_id,
        downloader=DownloadManager(),
        fetcher=fetcher,
    )
    if hasattr(fetcher, "profile_warnings"):
        summary.warnings.extend(fetcher.profile_warnings())
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
        summary.post_processing.extend(run_post_processing(layout, args.dedupe_threshold))

    summary.completed_at = utc_now_iso()
    exit_code = summarize_run_status(summary)
    manifest.append_run(summary)
    manifest.save()
    layout.run_report_path.write_text(json.dumps(summary.to_dict(), indent=2) + "\n")

    print(json.dumps(summary.to_dict(), indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

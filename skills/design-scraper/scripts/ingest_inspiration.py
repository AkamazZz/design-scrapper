#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.pipeline import ingest_inspiration


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize design-scraper outputs into orchestrator inspiration data.")
    parser.add_argument("--scrape-root", required=True, help="Root directory produced by design-scraper")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument("--project", help="Optional project name to store in the inspiration index")
    parser.add_argument("--run-id", help="Optional scraper run id to ingest")
    parser.add_argument("--run-report", help="Optional explicit run_*.json path")
    parser.add_argument("--allow-manifest-only", action="store_true", help="Allow ingesting without a run_*.json report")
    parser.add_argument("--include-duplicates", choices=["all", "unique", "flagged"], default="flagged")
    parser.add_argument("--strict", action="store_true", help="Fail on missing optional artifacts or missing asset files")
    parser.add_argument("--min-assets-per-source", type=int, default=1)
    parser.add_argument("--max-fallback-screenshot-ratio", type=float, default=1.0)
    parser.add_argument("--max-duplicate-ratio", type=float, default=1.0)
    parser.add_argument("--require-color-summary", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = ingest_inspiration(
        output_dir=Path(args.output_dir),
        scrape_root=Path(args.scrape_root),
        project_name=args.project,
        force=args.force,
        run_id=args.run_id,
        run_report=Path(args.run_report) if args.run_report else None,
        allow_manifest_only=args.allow_manifest_only,
        include_duplicates=args.include_duplicates,
        strict=args.strict,
        min_assets_per_source=args.min_assets_per_source,
        max_fallback_screenshot_ratio=args.max_fallback_screenshot_ratio,
        max_duplicate_ratio=args.max_duplicate_ratio,
        require_color_summary=args.require_color_summary,
    )
    report = result["report"]
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"run_id={report.get('run_id')}")
        print(f"warnings={len(report['warnings'])}")
        print(f"errors={len(report['errors'])}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.pipeline import run_pipeline
from mobile_design_orchestrator.project import DEFAULT_PLATFORMS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize and validate a mobile design orchestration workspace with an explicit proposal phase.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one or more orchestration phases")
    run_parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    run_parser.add_argument("--project", required=True, help="Project name")
    run_parser.add_argument("--scrape-root", help="Existing design-scraper output root")
    run_parser.add_argument(
        "--phase",
        action="append",
        choices=["ingest", "ideas", "proposal", "contract", "screens", "platforms", "plan", "validate"],
        help="Phase to run. Repeat for multiple phases. Defaults to the full scaffold flow.",
    )
    run_parser.add_argument(
        "--platform",
        action="append",
        choices=list(DEFAULT_PLATFORMS),
        help="Target platform. Repeat for multiple targets. Defaults to Flutter, SwiftUI, and Compose.",
    )
    run_parser.add_argument("--product-summary", help="Optional product summary to seed the brief")
    run_parser.add_argument("--force", action="store_true", help="Overwrite scaffold files instead of leaving existing content intact")
    run_parser.add_argument("--json", action="store_true", help="Print the run report as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    phases = args.phase or ["ingest", "ideas", "proposal", "contract", "screens", "platforms", "plan", "validate"]
    platforms = args.platform or list(DEFAULT_PLATFORMS)
    scrape_root = Path(args.scrape_root) if args.scrape_root else None
    report = run_pipeline(
        output_dir=Path(args.output_dir),
        project_name=args.project,
        platforms=platforms,
        phases=phases,
        scrape_root=scrape_root,
        force=args.force,
        product_summary=args.product_summary,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"run_id={report['run_id']}")
        print(f"status={report['status']}")
        print(f"output_dir={report['output_dir']}")
        print(f"phases={','.join(report['phases'])}")
        if report.get("validation_status"):
            print(f"validation={report['validation_status']}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

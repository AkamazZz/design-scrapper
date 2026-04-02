#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.project import DEFAULT_PLATFORMS, validation_markdown, validate_output_dir, write_json, write_markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a mobile design orchestration workspace, including proposal coverage.")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument(
        "--require-platform",
        action="append",
        choices=list(DEFAULT_PLATFORMS),
        help="Require mappings for the listed platforms. Defaults to the platforms declared in the brief.",
    )
    parser.add_argument("--json", action="store_true", help="Print the validation report as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    report = validate_output_dir(output_dir, required_platforms=args.require_platform)
    write_json(output_dir / "validation" / "report.json", report)
    write_markdown(output_dir / "validation" / "report.md", validation_markdown(report))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"errors={len(report['errors'])}")
        print(f"warnings={len(report['warnings'])}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

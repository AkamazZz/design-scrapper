#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.pipeline import emit_platform_mappings
from mobile_design_orchestrator.project import DEFAULT_PLATFORMS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh platform mappings from the current canonical contract and screen usage.")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument("--platform", action="append", choices=list(DEFAULT_PLATFORMS), help="Target platform")
    parser.add_argument("--usage-scope", choices=["used", "all"], default="used")
    parser.add_argument("--gap-mode", choices=["explicit", "stub", "omit"], default="explicit")
    parser.add_argument("--fail-on-gap", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = emit_platform_mappings(
        output_dir=Path(args.output_dir),
        platforms=args.platform,
        usage_scope=args.usage_scope,
        gap_mode=args.gap_mode,
        fail_on_gap=args.fail_on_gap,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"platforms={len(report['platforms'])}")
        print(f"gaps={len(report['gaps'])}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

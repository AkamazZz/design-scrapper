#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.pipeline import refresh_realization_plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the realization plan from current workspace artifacts.")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument("--project", help="Optional project name override")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = refresh_realization_plan(output_dir=Path(args.output_dir), project_name=args.project)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"plan={Path(args.output_dir) / 'realization' / 'plan.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

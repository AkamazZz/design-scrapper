#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.pipeline import synthesize_screens


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate starter mobile-first screens from the current proposal and contract.")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing screens/index.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = synthesize_screens(output_dir=Path(args.output_dir), force=args.force)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(f"screen_count={report['screen_count']}")
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

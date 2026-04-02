#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.project import append_idea


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append an idea card to a mobile design orchestration workspace.")
    parser.add_argument("--output-dir", required=True, help="Root output directory for the orchestration workspace")
    parser.add_argument("--title", required=True, help="Short title for the idea")
    parser.add_argument("--summary", default="", help="Short summary of the idea")
    parser.add_argument("--rationale", default="", help="Why this idea is worth carrying forward")
    parser.add_argument("--pattern-category", default="general", help="Reusable pattern category such as onboarding, card, or nav")
    parser.add_argument("--source-url", action="append", default=[], help="Source inspiration URL. Repeat for multiple links.")
    parser.add_argument("--source-asset", action="append", default=[], help="Source asset path. Repeat for multiple assets.")
    parser.add_argument("--target-screen", action="append", default=[], help="Target screen id. Repeat for multiple screens.")
    parser.add_argument("--status", default="candidate", help="Idea status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    idea = append_idea(
        output_dir=Path(args.output_dir),
        title=args.title,
        summary=args.summary,
        rationale=args.rationale,
        pattern_category=args.pattern_category,
        source_urls=args.source_url,
        source_assets=args.source_asset,
        target_screens=args.target_screen,
        status=args.status,
    )
    print(json.dumps(idea, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

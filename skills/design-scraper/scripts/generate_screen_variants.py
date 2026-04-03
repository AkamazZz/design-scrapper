#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.screen_variants import generate_screen_variants


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate persisted screen variants from frozen screen briefs.")
    parser.add_argument("--output-dir", required=True, help="Root orchestrator workspace directory")
    parser.add_argument("--run-id", default="manual", help="Run identifier for artifact metadata")
    parser.add_argument("--workspace-version", default="v2", help="Workspace version label")
    parser.add_argument(
        "--max-variants-per-screen",
        type=int,
        default=3,
        help="Maximum number of variants to persist for each screen",
    )
    parser.add_argument(
        "--screen-id",
        action="append",
        default=None,
        help="Optional screen id filter. Repeat to generate multiple screens.",
    )
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = generate_screen_variants(
        Path(args.output_dir),
        run_id=args.run_id,
        workspace_version=args.workspace_version,
        max_variants_per_screen=args.max_variants_per_screen,
        screen_ids=args.screen_id,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"screen_count={result['screen_count']}")
        print(f"variant_count={result['variant_count']}")
        print(f"screen_ids={','.join(result['screen_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

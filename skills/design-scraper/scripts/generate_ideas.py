#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mobile_design_orchestrator.idea_generation import write_automated_idea_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic idea artifacts for an orchestrator workspace.")
    parser.add_argument("--output-dir", required=True, help="Root orchestrator workspace directory")
    parser.add_argument("--run-id", default="manual", help="Run identifier for artifact metadata")
    parser.add_argument("--workspace-version", default="v2", help="Workspace version label")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = write_automated_idea_artifacts(Path(args.output_dir), run_id=args.run_id, workspace_version=args.workspace_version)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"generated_count={result['generated_count']}")
        print(f"new_count={result['new_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

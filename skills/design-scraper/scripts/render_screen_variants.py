from __future__ import annotations

import argparse
from pathlib import Path

from mobile_design_orchestrator.critic import build_scores_artifact, score_variants
from mobile_design_orchestrator.project import now_iso, write_json, write_markdown
from mobile_design_orchestrator.review import (
    build_review_summary_artifact,
    infer_project_slug,
    load_review_variants,
    render_review_summary_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render lightweight review previews and heuristic scores from screen_variants JSON artifacts."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Workspace root containing screen_variants/, or the screen_variants directory itself.",
    )
    parser.add_argument(
        "--input-dir",
        help="Explicit screen_variants directory. Overrides the positional root.",
    )
    parser.add_argument(
        "--review-dir",
        help="Explicit output directory for review artifacts. Defaults to <workspace>/review.",
    )
    parser.add_argument(
        "--project",
        help="Project slug override. Defaults to the workspace directory name.",
    )
    parser.add_argument(
        "--run-id",
        default="manual",
        help="Run identifier to embed in artifact metadata.",
    )
    parser.add_argument(
        "--workspace-version",
        default="v2",
        help="Workspace version metadata to embed in artifacts.",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print the rendered markdown summary after writing files.",
    )
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    root = Path(args.root).resolve()
    if args.input_dir:
        input_dir = Path(args.input_dir).resolve()
    elif root.name == "screen_variants":
        input_dir = root
    else:
        input_dir = root / "screen_variants"

    if args.review_dir:
        review_dir = Path(args.review_dir).resolve()
    else:
        workspace_root = input_dir.parent if input_dir.name == "screen_variants" else root
        review_dir = workspace_root / "review"
    return input_dir, review_dir


def main() -> int:
    args = parse_args()
    input_dir, review_dir = resolve_paths(args)
    generated_at = now_iso()
    project = infer_project_slug(input_dir, args.project)
    variants = load_review_variants(input_dir)
    scores = score_variants(variants)

    scores_artifact = build_scores_artifact(
        scores,
        project=project,
        source_dir=str(input_dir),
        generated_at=generated_at,
        run_id=args.run_id,
        workspace_version=args.workspace_version,
    )
    summary_artifact = build_review_summary_artifact(
        variants,
        scores,
        project=project,
        source_dir=input_dir,
        generated_at=generated_at,
        run_id=args.run_id,
        workspace_version=args.workspace_version,
    )
    summary_markdown = render_review_summary_markdown(summary_artifact)

    scores_path = review_dir / "scores.json"
    summary_path = review_dir / "summary.md"
    write_json(scores_path, scores_artifact)
    write_markdown(summary_path, summary_markdown)

    print(f"Rendered {len(variants)} variants into {scores_path} and {summary_path}")
    if args.print_summary:
        print()
        print(summary_markdown.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
SCRAPER="$SCRIPT_DIR/skills/design-scraper/scripts/scrape_design.py"
PROFILE_DIR="${HOME}/.design-scraper/profile"

usage() {
  cat <<'EOF'
Usage:
  plugins/design-scraper/run_scrape.sh <url> [<url> ...] [-- scraper-args...]

Defaults:
  --playwright-user-data-dir ~/.design-scraper/profile
  --headed

Examples:
  plugins/design-scraper/run_scrape.sh "https://mobbin.com/..."
  plugins/design-scraper/run_scrape.sh "https://mobbin.com/..." -- --skip-post-process
  plugins/design-scraper/run_scrape.sh "https://mobbin.com/..." "https://dribbble.com/..." -- --project headspace
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

typeset -a urls extra_args
parsing_urls=1

for arg in "$@"; do
  if [[ "$arg" == "--" && $parsing_urls -eq 1 ]]; then
    parsing_urls=0
    continue
  fi

  if [[ $parsing_urls -eq 1 ]]; then
    urls+=("$arg")
  else
    extra_args+=("$arg")
  fi
done

if [[ ${#urls[@]} -eq 0 ]]; then
  echo "At least one URL is required." >&2
  usage
  exit 1
fi

mkdir -p "$PROFILE_DIR"

python3 "$SCRAPER" \
  "${urls[@]}" \
  --playwright-user-data-dir "$PROFILE_DIR" \
  --headed \
  "${extra_args[@]}"

#!/usr/bin/env bash
# Apply GitHub repo description + homepage + topics from scripts/satellite-map.yaml.
# Uses GH_PAT / GITHUB_TOKEN (same as publish_all_repos) — no gh CLI required.
#
# Usage:
#   ./scripts/apply_github_metadata.sh                    # all satellites
#   ./scripts/apply_github_metadata.sh argus helios       # selected ids
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ONLY=("$@")

echo "=== apply_github_metadata (satellite-map.yaml → GitHub API) ==="

if ((${#ONLY[@]})); then
  python3 "$ROOT/scripts/sync_github_repo_descriptions.py" "${ONLY[@]}"
  python3 "$ROOT/scripts/sync_github_repo_topics.py" "${ONLY[@]}"
else
  python3 "$ROOT/scripts/sync_github_repo_descriptions.py"
  python3 "$ROOT/scripts/sync_github_repo_topics.py"
fi

echo "✅ metadata sync done"

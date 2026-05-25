#!/usr/bin/env bash
# Push one satellite subtree to its own remote (inverse of publish_aicom_factory.sh).
#
# Usage:
#   ./scripts/publish_satellite.sh aimarket-hub
#   ./scripts/publish_satellite.sh alien-monitor
#   ./scripts/publish_satellite.sh pulse-terminal --branch main
#   ./scripts/publish_satellite.sh --list
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SAT_ID=""
REMOTE=""
BRANCH="${SATELLITE_BRANCH:-main}"
DRY_RUN=0

usage() {
  cat <<'EOF'
publish_satellite.sh — export one satellite from monorepo to its GitHub repo

  ./scripts/publish_satellite.sh <satellite-id> [--branch main] [--dry-run]
  ./scripts/publish_satellite.sh --list

Satellite ids: see scripts/satellite-map.yaml
  e.g. aimarket-hub, acex, pulse-terminal, alien-monitor, aicom-wiki

All exports delegate to scripts/mirror_satellites.sh (layout transforms, mirror banner).
EOF
}

list_satellites() {
  python3 - <<'PY'
import yaml
from pathlib import Path
m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
for s in m.get("satellites", []):
    opt = " (optional)" if s.get("optional") else ""
    print(f"  {s['id']:20} → {s.get('org', m.get('org',''))}/{s['repo']}{opt}")
PY
}

validate_satellite() {
  python3 - "$1" <<'PY'
import sys, yaml
from pathlib import Path
sid = sys.argv[1]
m = yaml.safe_load(Path("scripts/satellite-map.yaml").read_text())
for s in m.get("satellites", []):
    if s["id"] == sid:
        if s.get("id") == "aicom":
            print("error: use publish_aicom_factory.sh or publish_all_repos.sh --factory-only", file=sys.stderr)
            raise SystemExit(1)
        raise SystemExit(0)
print(f"unknown satellite: {sid}", file=sys.stderr)
raise SystemExit(1)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) list_satellites; exit 0 ;;
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown: $1" >&2; exit 1 ;;
    *) SAT_ID="$1"; shift ;;
  esac
done

[[ -n "$SAT_ID" ]] || { usage; exit 1; }

validate_satellite "$SAT_ID"

if [[ -n "$REMOTE" ]]; then
  echo "note: --remote is ignored; mirror_satellites uses org/repo from satellite-map.yaml" >&2
fi

MIRROR_ARGS=(--satellite "$SAT_ID")
[[ "$DRY_RUN" -eq 1 ]] && MIRROR_ARGS+=(--dry-run)
[[ -n "$BRANCH" ]] && MIRROR_ARGS+=(--branch "$BRANCH")

exec bash "$ROOT/scripts/mirror_satellites.sh" "${MIRROR_ARGS[@]}"

#!/usr/bin/env bash
# Push one satellite subtree to its own remote (inverse of publish_aicom_factory.sh),
# through scripts/mirror_satellites.sh and its guards.
#
# Usage:
#   ./scripts/publish_satellite.sh aimarket-hub
#   ./scripts/publish_satellite.sh pulse-terminal --dry-run
#   ./scripts/publish_satellite.sh --list
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SAT_ID=""
REMOTE=""
BRANCH="${SATELLITE_BRANCH:-main}"
DRY_RUN=0
BRANCH_SET=""

usage() {
  cat <<'EOF'
publish_satellite.sh — export one satellite from monorepo to its GitHub repo

  ./scripts/publish_satellite.sh <satellite-id> [--branch main] [--dry-run]
  ./scripts/publish_satellite.sh --list

Satellite ids: see scripts/satellite-map.yaml (e.g. aimarket-hub, acex, pulse-terminal)
EOF
}

list_satellites() {
  AICOM_ROOT="$ROOT" python3 - <<'PY'
import os, sys, yaml
from pathlib import Path
_map_path = Path(os.environ["AICOM_ROOT"]) / "scripts" / "satellite-map.yaml"
if not _map_path.is_file():
    sys.exit(f"satellite-map.yaml not found at {_map_path}")
m = yaml.safe_load(_map_path.read_text(encoding="utf-8"))
for s in m.get("satellites", []):
    opt = " (optional)" if s.get("optional") else ""
    print(f"  {s['id']:20} → {s.get('org', m.get('org',''))}/{s['repo']}{opt}")
PY
}

resolve_satellite() {
  AICOM_ROOT="$ROOT" python3 - "$1" <<'PY'
import os, sys, yaml
from pathlib import Path
sid = sys.argv[1]
_map_path = Path(os.environ["AICOM_ROOT"]) / "scripts" / "satellite-map.yaml"
if not _map_path.is_file():
    sys.exit(f"satellite-map.yaml not found at {_map_path}")
m = yaml.safe_load(_map_path.read_text(encoding="utf-8"))
for s in m.get("satellites", []):
    if s["id"] == sid:
        paths = s.get("paths") or []
        layout = s.get("export_layout") or {}
        print(s.get("repo", sid))
        print(layout.get("root_from") or paths[0] if paths else "")
        raise SystemExit(0)
print(f"unknown satellite: {sid}", file=sys.stderr)
raise SystemExit(1)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) list_satellites; exit 0 ;;
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; BRANCH_SET=1; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown: $1" >&2; exit 1 ;;
    *) SAT_ID="$1"; shift ;;
  esac
done

[[ -n "$SAT_ID" ]] || { usage; exit 1; }

# One door to a satellite's public repo. This script used to rsync with its own exclude
# list — no per-satellite exclude_paths, no github_published check — and push from that.
# The canonical mirror carries those guards, so every satellite goes through it, and the
# remote is the one the map names, not one typed here.
if [[ -n "$REMOTE" ]]; then
  echo "error: --remote is not taken — the remote comes from scripts/satellite-map.yaml" >&2
  echo "  (org via SATELLITE_GITHUB_ORG)." >&2
  exit 2
fi

if [[ "$SAT_ID" == "course" || "$SAT_ID" == course-* ]]; then
  SAT_ID="aimarket-courses"
fi

{ read -r REPO_NAME; read -r SRC_PATH; } < <(resolve_satellite "$SAT_ID")
if [[ -z "$SRC_PATH" || "$SRC_PATH" == "." ]]; then
  echo "error: satellite '$SAT_ID' has no monorepo export path (paths: [] in satellite-map.yaml)." >&2
  echo "  Do not publish standalone siblings from the monorepo — maintain them in their own checkout." >&2
  exit 2
fi

args=(--satellite "$SAT_ID")
[[ -n "$BRANCH_SET" ]] && args+=(--branch "$BRANCH")
[[ "$DRY_RUN" -eq 1 ]] && args+=(--dry-run)
exec bash "$ROOT/scripts/mirror_satellites.sh" "${args[@]}"

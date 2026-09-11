#!/usr/bin/env bash
# Push one satellite subtree to its own remote (inverse of publish_aicom_factory.sh).
#
# Usage:
#   ./scripts/publish_satellite.sh aimarket-hub
#   ./scripts/publish_satellite.sh pulse-terminal --remote git@github.com:alexar76/pulse-terminal.git
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

  ./scripts/publish_satellite.sh <satellite-id> [--remote URL] [--branch main]
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
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown: $1" >&2; exit 1 ;;
    *) SAT_ID="$1"; shift ;;
  esac
done

[[ -n "$SAT_ID" ]] || { usage; exit 1; }

if [[ "$SAT_ID" == "course" ]]; then
  SAT_ID="aimarket-courses"
fi

{ read -r REPO_NAME; read -r SRC_PATH; } < <(resolve_satellite "$SAT_ID")
if [[ -z "$SRC_PATH" || "$SRC_PATH" == "." ]]; then
  echo "error: satellite '$SAT_ID' has no monorepo export path (paths: [] in satellite-map.yaml)." >&2
  echo "  Do not publish standalone siblings from the monorepo — maintain them in their own checkout." >&2
  exit 2
fi
ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
REMOTE="${REMOTE:-git@${SATELLITE_GITHUB_HOST:-github.com}:${ORG}/${REPO_NAME}.git}"

# Normalize export source — complex layouts delegate to mirror_satellites.sh
if [[ "$SAT_ID" == "aimarket-desktop" ]]; then
  echo "→ aimarket-desktop requires layout transform — delegating to mirror_satellites.sh"
  exec bash "$ROOT/scripts/mirror_satellites.sh" --satellite aimarket-desktop "$@"
  exit $?
fi
if [[ "$SAT_ID" == "aimarket-plugins" ]]; then
  echo "→ aimarket-plugins requires multi-source layout — delegating to mirror_satellites.sh"
  exec bash "$ROOT/scripts/mirror_satellites.sh" --satellite aimarket-plugins "$@"
  exit $?
fi
if [[ "$SAT_ID" == "aimarket-courses" || "$SAT_ID" == course* ]]; then
  echo "→ ${SAT_ID} requires course monorepo layout — delegating to mirror_satellites.sh"
  exec bash "$ROOT/scripts/mirror_satellites.sh" --satellite aimarket-courses "$@"
  exit $?
fi
if [[ "$SAT_ID" == "aicom-wiki" || "$SAT_ID" == "argus-wiki" ]]; then
  echo "→ ${SAT_ID} requires wiki page filter — delegating to mirror_satellites.sh"
  exec bash "$ROOT/scripts/mirror_satellites.sh" --satellite "$SAT_ID" "$@"
  exit $?
fi
if [[ "$SAT_ID" == "oracles" ]]; then
  echo "→ oracles requires Gitea strip + GitHub CI — delegating to mirror_satellites.sh"
  exec bash "$ROOT/scripts/mirror_satellites.sh" --satellite oracles "$@"
  exit $?
fi

SRC="$ROOT/$SRC_PATH"
[[ -d "$SRC" ]] || { echo "error: source missing: $SRC" >&2; exit 2; }

echo "Satellite: $SAT_ID"
echo "Source:    $SRC"
echo "Remote:    $REMOTE"

if [[ "$DRY_RUN" -eq 1 ]]; then
  exit 0
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

git clone --depth 1 --branch "$BRANCH" "$REMOTE" "$WORKDIR/clone" 2>/dev/null || {
  git clone --depth 1 "$REMOTE" "$WORKDIR/clone"
  (cd "$WORKDIR/clone" && git checkout -B "$BRANCH")
}

LOCAL_EXCLUDES=()
while IFS= read -r line; do LOCAL_EXCLUDES+=("$line"); done < <(python3 "$ROOT/scripts/aicom_publish_config.py" list-local-excludes)

RSYNC_EX=( -a --delete
  --exclude .git
  --exclude node_modules
  --exclude __pycache__
  --exclude .venv
  --exclude build
  --exclude dist
  --exclude ':memory:'
  --exclude ':memory:-wal'
  --exclude ':memory:-shm'
  --exclude '*.sqlite3'
  --exclude '*.sqlite3-wal'
  --exclude '*.sqlite3-shm'
)
for p in "${LOCAL_EXCLUDES[@]}"; do
  RSYNC_EX+=(--exclude "$p")
done

rsync "${RSYNC_EX[@]}" "$SRC/" "$WORKDIR/clone/"

for p in "${LOCAL_EXCLUDES[@]}"; do
  [[ -e "$WORKDIR/clone/$p" ]] && rm -rf "$WORKDIR/clone/$p"
done

bash "$ROOT/scripts/purge_mirror_runtime_artifacts.sh" "$WORKDIR/clone"
bash "$ROOT/scripts/verify_mirror_secrets.sh" "$WORKDIR/clone"

cd "$WORKDIR/clone"
git add -A
git diff --cached --quiet && git diff --quiet && { echo "No changes"; exit 0; }
git commit -m "chore(satellite): sync $SAT_ID from aicom monorepo"
git push origin "HEAD:$BRANCH"
echo "OK pushed $SAT_ID → $REMOTE"

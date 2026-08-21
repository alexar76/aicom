#!/usr/bin/env bash
# =============================================================================
# publish_ghcr_packages.sh — workflow_dispatch publish-ghcr.yml for satellites
# that publish container images to ghcr.io/alexar76/* (GitHub Packages).
#
# Source of truth: scripts/satellite-map.yaml → registries: [ghcr:…]
# Each listed satellite must ship .github/workflows/publish-ghcr.yml
# (mirrored from the monorepo path).
#
# Usage:
#   ./scripts/publish_ghcr_packages.sh              # dispatch all
#   ./scripts/publish_ghcr_packages.sh --list        # show targets
#   ./scripts/publish_ghcr_packages.sh --dry-run
#   ./scripts/publish_ghcr_packages.sh --satellite gaia
#
# Environment:
#   GH_PAT / GITHUB_TOKEN     required for dispatch (needs repo + workflow scope)
#   SATELLITE_GITHUB_ORG      default: alexar76
#   SATELLITE_BRANCH          default: main
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export AICOM_ROOT="$ROOT"

ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
BRANCH="${SATELLITE_BRANCH:-main}"
DRY_RUN=0
LIST_ONLY=0
SINGLE=""

usage() {
  cat <<'EOF'
publish_ghcr_packages.sh — dispatch GHCR publish workflows on GitHub satellites

  (default)           workflow_dispatch publish-ghcr.yml for every ghcr:* satellite
  --list              Print repo → image targets (no network)
  --dry-run           Print what would be dispatched
  --satellite ID      Only that satellite id (must have registries: ghcr:…)
  -h, --help          This help

Packages page: https://github.com/alexar76?tab=packages
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) LIST_ONLY=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --satellite) SINGLE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage; exit 1 ;;
    *) SINGLE="$1"; shift ;;
  esac
done

# Emit lines: sat_id|repo|images(comma)|workflow_path_in_monorepo
_list_ghcr_targets() {
  python3 - <<'PY'
import os, sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required", file=sys.stderr)
    raise SystemExit(1)

root = Path(os.environ.get("AICOM_ROOT") or Path.cwd())
m = yaml.safe_load((root / "scripts/satellite-map.yaml").read_text(encoding="utf-8")) or {}
single = os.environ.get("GHCR_SINGLE", "").strip()

for s in m.get("satellites") or []:
    sid = str(s.get("id") or "")
    if single and sid != single:
        continue
    regs = s.get("registries") or []
    images = []
    for r in regs:
        r = str(r)
        if r.startswith("ghcr:"):
            images.append(r.split(":", 1)[1])
    if not images:
        continue
    repo = str(s.get("repo") or sid)
    layout = s.get("export_layout") or {}
    root_from = str(layout.get("root_from") or ((s.get("paths") or [sid])[0]))
    wf = root / root_from / ".github/workflows/publish-ghcr.yml"
    # Factory optional satellite may live at repo root.
    if not wf.is_file() and root_from in (".", ""):
        wf = root / ".github/workflows/publish-ghcr.yml"
    status = "ok" if wf.is_file() else "missing-workflow"
    print(f"{sid}|{repo}|{','.join(images)}|{wf.relative_to(root)}|{status}")
PY
}

export GHCR_SINGLE="$SINGLE"

echo "=== GHCR package publish (workflow_dispatch) ==="
echo "Org: ${ORG}  branch: ${BRANCH}"
echo ""

targets=()
while IFS= read -r line; do
  [[ -n "$line" ]] && targets+=("$line")
done < <(_list_ghcr_targets)

if ((${#targets[@]} == 0)); then
  if [[ -n "$SINGLE" ]]; then
    echo "error: satellite '$SINGLE' has no ghcr:* registry in satellite-map.yaml" >&2
    exit 1
  fi
  echo "No ghcr:* targets in satellite-map.yaml"
  exit 0
fi

errors=0
dispatched=0
for line in "${targets[@]}"; do
  IFS='|' read -r sid repo images wf_rel status <<<"$line"
  echo "━━━ ${sid} → ${ORG}/${repo} ━━━"
  echo "  images:   ${images//,/ }"
  echo "  workflow: ${wf_rel} (${status})"

  if [[ "$LIST_ONLY" -eq 1 ]]; then
    continue
  fi

  if [[ "$status" != "ok" ]]; then
    echo "  · skip — no publish-ghcr.yml in monorepo (optional / not wired yet)"
    continue
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  [dry-run] would dispatch publish-ghcr.yml on ${ORG}/${repo}@${BRANCH}"
    continue
  fi

  if python3 "$ROOT/scripts/dispatch_github_workflow.py" "$repo" publish-ghcr.yml "$BRANCH"; then
    dispatched=$((dispatched + 1))
  else
    errors=$((errors + 1))
  fi
done

echo ""
if [[ "$LIST_ONLY" -eq 1 || "$DRY_RUN" -eq 1 ]]; then
  echo "Done (list/dry-run)."
  exit 0
fi

if [[ "$errors" -eq 0 ]]; then
  echo "OK dispatched ${dispatched} GHCR workflow(s)."
  echo "Watch: https://github.com/${ORG}?tab=packages"
  echo "Actions per repo: https://github.com/${ORG}/<repo>/actions/workflows/publish-ghcr.yml"
  exit 0
fi

echo "WARN finished with ${errors} error(s) (${dispatched} dispatched)."
exit 1

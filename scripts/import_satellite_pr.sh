#!/usr/bin/env bash
# ============================================================================
# Reverse-import: bring merged PRs from a LIVE satellite back into the monorepo.
# ============================================================================
# For `history: live` satellites, contributors open PRs on GitHub. Once merged,
# those commits live on the satellite's main but NOT in the monorepo — the
# canonical source. Before the next outbound sync (mirror_satellites.sh) can run,
# the change must land in the monorepo, or the sync's rsync-overwrite would
# revert it (and its divergence guard will refuse to run until you do this).
#
# This script is READ-ONLY toward GitHub and NON-DESTRUCTIVE toward the monorepo:
# it clones the satellite, computes the delta since the last monorepo-sync commit
# (i.e. the merged PRs), strips the mirror-injected artifacts (governance, badge
# tooling, banner), and writes a reviewable PATCH. YOU review, apply, and commit.
# It never pushes and never auto-edits your working tree.
#
#   ./scripts/import_satellite_pr.sh metis
#
# Then (the patch carries monorepo paths, so it applies at the monorepo root):
#   git apply --3way /tmp/aicom-import/metis.patch   # review first!
#   git commit -m "metis: import PR #NN from GitHub" -- metis
#   ALLOW_DIVERGENCE=1 ./scripts/publish_all_repos.sh --satellite metis   # re-sync
# ============================================================================
set -euo pipefail

SAT_ID="${1:-}"
[[ -n "$SAT_ID" ]] || { echo "usage: $0 <satellite-id>   (e.g. metis)"; exit 2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORG="${SATELLITE_GITHUB_ORG:-alexar76}"
HOST="${SATELLITE_GITHUB_HOST:-github.com}"
BRANCH="${SATELLITE_BRANCH:-main}"
OUTDIR="${IMPORT_OUTDIR:-/tmp/aicom-import}"
SYNC_SUBJECT_PREFIX="chore(satellite): sync"

# ── Resolve repo, history mode and the satellite → monorepo path map ─────────
# Most satellites publish one monorepo folder at their root; some fold several
# folders together (desktop apps/, plugins/, attested-memory apps/, a vendored
# oracles/core). satellite_import_paths.py prints the map, most specific first.
MAP_OUT="$(python3 "$ROOT/scripts/satellite_import_paths.py" "$SAT_ID")" || {
  echo "✗ '$SAT_ID' not found in scripts/satellite-map.yaml"; exit 1; }
IFS='|' read -r REPO MODE <<<"$(printf '%s\n' "$MAP_OUT" | head -1)"
MAP_LINES="$(printf '%s\n' "$MAP_OUT" | tail -n +2)"
MONO_PATH="$(printf '%s\n' "$MAP_LINES" | awk -F'|' '$1==""{print $2}')"

if [[ "$MODE" != "live" ]]; then
  echo "✗ '$SAT_ID' is history: ${MODE}, not 'live'. Reverse-import only applies to live satellites."
  echo "  (mirror satellites are read-only — PRs there are overwritten, so there is nothing to import.)"
  exit 1
fi
[[ -d "$ROOT/$MONO_PATH" ]] || { echo "✗ monorepo path missing: $MONO_PATH"; exit 1; }

# ── Clone the satellite (read-only; token only if provided, for private repos) ─
TOKEN="${GH_PAT:-${GITHUB_TOKEN:-}}"
if [[ -n "${SATELLITE_CLONE_URL:-}" ]]; then
  URL="$SATELLITE_CLONE_URL"   # tests and offline review of a local clone
elif [[ -n "$TOKEN" ]]; then
  URL="https://x-access-token:${TOKEN}@${HOST}/${ORG}/${REPO}.git"
else
  URL="https://${HOST}/${ORG}/${REPO}.git"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
echo "▶ Cloning ${ORG}/${REPO} (${BRANCH}) …"
git clone --quiet --branch "$BRANCH" "$URL" "$WORK/sat" || {
  echo "✗ clone failed (private repo? set GH_PAT). URL host: ${HOST}/${ORG}/${REPO}"
  exit 1
}

# ── Find the last monorepo-sync commit → everything after it is external work ─
cd "$WORK/sat"
BASE="$(git log --format='%H%x09%s' | awk -F'\t' -v p="$SYNC_SUBJECT_PREFIX" 'index($2,p)==1{print $1; exit}')"

if [[ -z "$BASE" ]]; then
  echo "⚠ No '${SYNC_SUBJECT_PREFIX} …' commit found in history — cannot locate a sync baseline."
  echo "  This repo may not have been synced in live mode yet. Nothing imported."
  exit 0
fi
if [[ "$BASE" == "$(git rev-parse HEAD)" ]]; then
  echo "✓ Satellite tip IS the last monorepo-sync commit — no external PRs to import."
  exit 0
fi

echo ""
echo "External commits since last sync ($(git rev-parse --short "$BASE")):"
git log --format='  %h  %an  %s' "${BASE}..HEAD"
echo ""

# ── Emit a reviewable patch, minus mirror-injected artifacts ─────────────────
# One `git diff` per mapping, so each file carries its MONOREPO path and the patch
# applies at the monorepo root. A file under a more specific prefix is left to
# that prefix's diff. Renames are split into delete + add so a file that moved
# between two mapped folders still lands on both sides.
GENERATED=(
  ':(exclude)LICENSE' ':(exclude)SECURITY.md' ':(exclude)CONTRIBUTING.md'
  ':(exclude)CODE_OF_CONDUCT.md' ':(exclude)CONTRIBUTORS.md'
  ':(exclude).github' ':(exclude)docs/badges'
  ':(exclude)scripts/ci_static_badge.sh' ':(exclude)scripts/generate_static_badge.py'
  ':(exclude)scripts/satellite-map.yaml'
)
mkdir -p "$OUTDIR"
PATCH="$OUTDIR/${SAT_ID}.patch"
: > "$PATCH"
SEEN_PREFIXES=()
while IFS='|' read -r prefix target; do
  excludes=()
  for p in "${SEEN_PREFIXES[@]+"${SEEN_PREFIXES[@]}"}"; do excludes+=(":(exclude)$p"); done
  if [[ -z "$prefix" ]]; then
    git diff --binary --no-renames --src-prefix="a/${target:+$target/}" --dst-prefix="b/${target:+$target/}" \
      "${BASE}..HEAD" -- . "${GENERATED[@]}" "${excludes[@]+"${excludes[@]}"}" >> "$PATCH" || true
  else
    git diff --binary --no-renames --relative="$prefix" \
      --src-prefix="a/${target:+$target/}" --dst-prefix="b/${target:+$target/}" \
      "${BASE}..HEAD" -- "$prefix" "${excludes[@]+"${excludes[@]}"}" >> "$PATCH" || true
    SEEN_PREFIXES+=("$prefix")
  fi
done <<<"$MAP_LINES"

SKIPPED="$(git diff --name-only --no-renames "${BASE}..HEAD" -- \
  LICENSE SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md CONTRIBUTORS.md .github docs/badges \
  scripts/ci_static_badge.sh scripts/generate_static_badge.py scripts/satellite-map.yaml)"
if [[ -n "$SKIPPED" ]]; then
  echo "· Left out (written by the mirror on every sync — port by hand if the PR meant them):"
  printf '    %s\n' $SKIPPED
fi

if [[ ! -s "$PATCH" ]]; then
  echo "✓ External commits touch only mirror-injected files (governance/badges) — nothing to import into the monorepo."
  exit 0
fi

echo "✅ Wrote reviewable patch: $PATCH ($(wc -l < "$PATCH") lines)"
echo "   Paths in it are monorepo paths:"
grep '^diff --git ' "$PATCH" | awk '{print "     " substr($4, 3)}' | sort -u
echo ""
echo "Next (all local — nothing is pushed):"
echo "  1. Review:  \$EDITOR $PATCH   (drop any README mirror-banner hunk if present)"
echo "  2. Apply:   git -C \"$ROOT\" apply --3way \"$PATCH\""
echo "  3. Commit:  git -C \"$ROOT\" commit -m \"$SAT_ID: import PR from GitHub\" -- <the paths above>"
echo "  4. Re-sync: ALLOW_DIVERGENCE=1 ./scripts/publish_all_repos.sh --satellite $SAT_ID   (you run the push)"

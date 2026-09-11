#!/usr/bin/env bash
# =============================================================================
# Drop stale per-deploy image tags, keeping the running one and one rollback.
# =============================================================================
# Every rsync-and-rebuild deploy on the factory host mints a new tag and nothing
# ever removes the old one. Measured 2026-08-27: 36 images / 48.4 GB on a 77 GB
# disk, of which 22.6 GB was unreferenced — including seven
# `modelmarket-hub:prod-20260826-{zkdemo,zkdemo2..5,chrome,chrome2,chrome3}`
# tags from a single afternoon of debugging. With 11 GB free, a factory rebuild
# (13.1 GB image) then failed at `[base 19/21]` — the `chown -R` step whose own
# Dockerfile comment says it "exhausts disk on build" — and failed silently
# enough that it looked like it was still running. Freeing space fixed it; not
# accumulating in the first place is the actual fix.
#
# SAFETY, because this deletes things on a production host:
#   * dry run unless --yes;
#   * never touches an image referenced by ANY container, running or stopped
#     (that is what a rollback target is);
#   * keeps the newest KEEP tags per repository (default 2: current + rollback);
#   * only looks at repositories named on the allow-list, so it can never
#     wander into base images or something it was not asked about;
#   * `docker rmi` without -f, so a still-referenced layer refuses rather than
#     breaking whatever holds it.
#
# Usage:
#   ./scripts/prune_stale_deploy_images.sh                    # dry run, all repos
#   ./scripts/prune_stale_deploy_images.sh --yes              # actually remove
#   ./scripts/prune_stale_deploy_images.sh --keep 3 --yes
#   ./scripts/prune_stale_deploy_images.sh --repo ai-factory --yes
#   REMOTE=my-vps ./scripts/prune_stale_deploy_images.sh --yes # run over ssh
#
# Run it after a deploy is VERIFIED, never before — the tag you are about to
# delete is the one you would roll back to if the new one is broken.
# =============================================================================
set -euo pipefail

KEEP=2
APPLY=0
REPOS=(ai-factory modelmarket-hub alien-monitor pulse-terminal themis)
ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) APPLY=1; shift ;;
    --keep) KEEP="${2:?--keep needs a number}"; shift 2 ;;
    --repo) ONLY="${2:?--repo needs a name}"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ "$KEEP" =~ ^[0-9]+$ ]] || { echo "--keep must be a number" >&2; exit 1; }
(( KEEP >= 1 )) || { echo "--keep must be at least 1 — keeping zero tags leaves no rollback" >&2; exit 1; }

# The whole body runs either locally or over ssh, so the logic exists once.
run() {
  if [[ -n "${REMOTE:-}" ]]; then ssh -o BatchMode=yes "$REMOTE" "$1"; else bash -c "$1"; fi
}

[[ -n "$ONLY" ]] && REPOS=("$ONLY")

# Images any container points at. Includes stopped containers on purpose: a stopped
# `*-prev` container IS the rollback mechanism on this host.
IN_USE="$(run 'docker ps -a --format "{{.Image}}" | sort -u')"

planned=()

# Only PER-DEPLOY tags are in scope. `:local`, `:latest` and hand-made tags are somebody's dev
# artifact or a deliberate marker, and a script called "prune stale deploy images" has no
# business deciding their fate. The first dry run classified `alien-monitor:local` as removable
# and `pulse-terminal:local` as a rollback candidate purely by timestamp order — both wrong in
# the same way: it was reasoning about tags it was never asked about.
DEPLOY_TAG_RE='^prod-'

for repo in "${REPOS[@]}"; do
  # Newest first. CreatedAt sorts lexically as an ISO-ish timestamp from docker.
  # A `while read` over a here-string rather than `mapfile`: this script is normally driven
  # from the laptop over ssh, and macOS ships bash 3.2, where mapfile does not exist. A
  # here-string also keeps the loop in THIS shell, so the `kept` counter survives — a pipe
  # would run it in a subshell and silently keep nothing.
  tags="$(run "docker images '$repo' --format '{{.CreatedAt}}|{{.Repository}}:{{.Tag}}|{{.Size}}' | sort -r" || true)"
  [ -n "$tags" ] || continue

  kept=0
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    ref="$(cut -d'|' -f2 <<<"$line")"
    size="$(cut -d'|' -f3 <<<"$line")"
    [[ "$ref" == *":<none>" ]] && continue
    tag="${ref##*:}"
    if ! [[ "$tag" =~ $DEPLOY_TAG_RE ]]; then
      printf '  skip (not a deploy tag) %-37s %8s\n' "$ref" "$size"
      continue
    fi

    if grep -qxF "$ref" <<<"$IN_USE"; then
      printf '  keep (in use)   %-46s %8s\n' "$ref" "$size"
      continue
    fi
    if (( kept < KEEP )); then
      kept=$((kept + 1))
      printf '  keep (rollback) %-46s %8s\n' "$ref" "$size"
      continue
    fi
    printf '  REMOVE          %-46s %8s\n' "$ref" "$size"
    planned+=("$ref")
  done <<< "$tags"
done

if (( ${#planned[@]} == 0 )); then
  echo
  echo "Nothing to remove — every tag is either in use or within the newest $KEEP."
  exit 0
fi

echo
if (( APPLY == 0 )); then
  echo "Dry run. ${#planned[@]} image(s) would be removed. Re-run with --yes."
  exit 0
fi

echo "Removing ${#planned[@]} image(s)…"
for ref in "${planned[@]}"; do
  # No -f: if something still references a layer, refusing is the correct outcome.
  run "docker rmi '$ref'" || echo "  (refused, left in place: $ref)"
done

echo
run 'df -h / | tail -1'

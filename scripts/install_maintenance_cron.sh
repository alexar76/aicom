#!/usr/bin/env bash
# Install the host-maintenance cron jobs that keep disks from filling.
#
#   ./scripts/install_maintenance_cron.sh --remote root@HOST [--dry-run]
#   ./scripts/install_maintenance_cron.sh                      # install on THIS host
#
# Why this exists: both reapers were written on 2026-09-11 (cd5e10149) and one of them was
# then copied to /usr/local/bin by hand and given a crontab line by hand. Nothing in the
# repo recorded either, so the protection existed only in one host's crontab — a rebuild,
# or a second host, silently loses it, and `grep -r prune_anvil_state` finds no installer.
# Both jobs are idempotent, so re-running this is safe and is how you verify.
#
# What gets installed (tagged, so re-runs REPLACE rather than append):
#   */15 * * * *  prune-anvil-state.sh   # aicom-prune-anvil
#                 Anvil writes a full state dump into ~/.foundry/anvil/tmp/anvil-state-*
#                 on every dump and never reaps it. Five of those reached 35 GB on the
#                 oracle host and filled the disk; nginx then truncated responses, which
#                 is how a demo chain took down unrelated public pages.
#   30 4 * * 0    gitea-dind-prune.sh    # aicom-prune-gitea-dind
#                 act_runner builds CI jobs inside gitea-runner-dind, a nested Docker
#                 daemon with its own /var/lib/docker. Its images are throwaway and stay
#                 until something prunes them; one leftover reached 1.5 GB.
#   15 5 * * *    prune-stale-deploy-images.sh --yes   # aicom-prune-images
#                 Every rsync-and-rebuild deploy mints a tag and nothing removed the old
#                 one. On 2026-09-11 that was 21 unreferenced alien-monitor images at
#                 1.66 GB each — 25 GB on a 77 GB disk — and a monitor rebuild died with
#                 "no space left on device". The script never touches an image any
#                 container references and keeps the newest two per repository.
#
# Only hosts that actually run the relevant container need the job, and each script
# already no-ops when its container is absent — so installing both everywhere is safe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE=""
DRY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote) REMOTE="${2:?--remote needs USER@HOST}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# (source path, installed name, schedule, cron tag)
JOBS=(
  "scripts/prune_anvil_state.sh|prune-anvil-state.sh|*/15 * * * *|aicom-prune-anvil"
  "scripts/gitea_dind_prune.sh|gitea-dind-prune.sh|30 4 * * 0|aicom-prune-gitea-dind"
  "scripts/prune_stale_deploy_images.sh|prune-stale-deploy-images.sh --yes|15 5 * * *|aicom-prune-images"
)

for job in "${JOBS[@]}"; do
  IFS='|' read -r src name sched tag <<<"$job"
  [[ -f "$ROOT/$src" ]] || { echo "missing source: $src" >&2; exit 1; }
done

# The installer body runs identically locally and over ssh. Written to a temp file and
# fed to bash so the quoting survives one ssh hop.
build_script() {
  echo 'set -euo pipefail'
  for job in "${JOBS[@]}"; do
    IFS='|' read -r src name sched tag <<<"$job"
    # `name` may carry flags (e.g. "foo.sh --yes"); the FILE is the first word.
    file="${name%% *}"
    printf 'install -m 0755 /tmp/%s /usr/local/bin/%s\n' "$file" "$file"
    # Drop ANY existing line for this script — tagged by us, or the untagged one a human
    # added by hand (admin-vps had exactly that for the anvil reaper) — then append the
    # current, tagged line. Filtering on the tag alone left the hand-written duplicate in
    # place and the job fired twice every quarter hour.
    printf 'crontab -l 2>/dev/null | grep -vF "/usr/local/bin/%s" > /tmp/crontab.next || true\n' "$file"
    printf 'printf "%%s /usr/local/bin/%s >/dev/null 2>&1 # %s\\n" "%s" >> /tmp/crontab.next\n' "$name" "$tag" "$sched"
    printf 'crontab /tmp/crontab.next && rm -f /tmp/crontab.next\n'
  done
  echo 'echo "--- installed ---"'
  for job in "${JOBS[@]}"; do
    IFS='|' read -r src name sched tag <<<"$job"
    printf 'ls -l /usr/local/bin/%s\n' "${name%% *}"
  done
  echo 'echo "--- crontab (aicom maintenance) ---"'
  echo 'crontab -l | grep "# aicom-prune" || echo "NONE — install failed"'
}

if (( DRY )); then
  echo "=== would copy ==="
  for job in "${JOBS[@]}"; do
    IFS='|' read -r src name sched tag <<<"$job"
    echo "  $src -> /usr/local/bin/$name   ($sched  # $tag)"
  done
  echo "=== would run on ${REMOTE:-this host} ==="
  build_script
  exit 0
fi

if [[ -n "$REMOTE" ]]; then
  for job in "${JOBS[@]}"; do
    IFS='|' read -r src name sched tag <<<"$job"
    scp -q -o BatchMode=yes "$ROOT/$src" "$REMOTE:/tmp/${name%% *}"
  done
  build_script | ssh -o BatchMode=yes "$REMOTE" "bash -s"
else
  for job in "${JOBS[@]}"; do
    IFS='|' read -r src name sched tag <<<"$job"
    cp "$ROOT/$src" "/tmp/${name%% *}"
  done
  build_script | bash -s
fi

#!/usr/bin/env bash
# Oracle host disk cleanup — safe defaults for this box.
#
# Main target: runaway Anvil state (ailottery-chain-1 grew to ~60 GB once).
# Keeps stopped containers, tagged images and volumes for rollback; prunes rebuildable cache and dangling images only.
#
# Install: /etc/cron.d/oracle-disk-cleanup (daily 04:30)
# Manual:  /root/scripts/disk-cleanup.sh [--dry-run]
# Log:     /var/log/disk-cleanup.log

set -euo pipefail

LOG=/var/log/disk-cleanup.log
LOCK=/run/disk-cleanup.lock
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

# Reset demo Anvil chain when writable layer exceeds this (bytes).
ANVIL_MAX_BYTES=$((5 * 1024 * 1024 * 1024))   # 5 GiB
LOTTERY_DIR=/root/lottery
CHAIN_NAME=ailottery-chain-1

log() {
  echo "[$(date -Is)] $*" | tee -a "$LOG"
}

run() {
  if [[ "$DRY_RUN" == 1 ]]; then
    log "DRY-RUN: $*"
  else
    log "RUN: $*"
    "$@"
  fi
}

df_line() {
  df -h / | awk 'NR==2 {print $3 " used / " $2 " total, " $4 " free (" $5 ")"}'
}

human_to_bytes() {
  local s=$1 num unit
  [[ -n "$s" ]] || { echo 0; return; }
  num=$(echo "$s" | sed -E 's/^([0-9.]+).*/\1/')
  unit=$(echo "$s" | sed -E 's/^[0-9.]+([A-Za-z]+).*/\1/')
  case "$unit" in
    B|"") awk "BEGIN{printf \"%d\", $num}" ;;
    kB|KB|K) awk "BEGIN{printf \"%d\", $num * 1024}" ;;
    MB|M) awk "BEGIN{printf \"%d\", $num * 1024 * 1024}" ;;
    GB|G) awk "BEGIN{printf \"%d\", $num * 1024 * 1024 * 1024}" ;;
    TB|T) awk "BEGIN{printf \"%d\", $num * 1024 * 1024 * 1024 * 1024}" ;;
    *) echo 0 ;;
  esac
}

container_rw_bytes() {
  local name=$1 raw human
  raw=$(docker inspect -f '{{.SizeRw}}' "$name" 2>/dev/null || true)
  if [[ "$raw" =~ ^[0-9]+$ ]]; then
    echo "$raw"
    return
  fi
  human=$(docker ps -s --filter "name=^${name}$" --format '{{.Size}}' 2>/dev/null | awk '{print $1}')
  human_to_bytes "$human"
}

anvil_containerd_bytes() {
  local base=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots
  [[ -d "$base" ]] || { echo 0; return; }
  du -sb "$base"/*/fs/root/.foundry/anvil/tmp 2>/dev/null \
    | awk '{s+=$1} END {print s+0}'
}

reset_lottery_chain() {
  # Disk pressure must never destroy a persistent chain or rebuild services.
  log "ATTENTION: $1; chain retained, investigate storage without resetting it"
}

exec 9>"$LOCK"
if ! flock -n 9; then
  log "already running — exit"
  exit 0
fi

log "=== disk-cleanup start (dry_run=$DRY_RUN) ==="
log "before: $(df_line)"

# --- 1. Anvil bloat (the usual culprit) ---------------------------------
if docker ps -q -f name="^${CHAIN_NAME}$" | grep -q .; then
  rw=$(container_rw_bytes "$CHAIN_NAME")
  ctrd=$(anvil_containerd_bytes)
  log "anvil chain SizeRw=${rw}B containerd_anvil_tmp=${ctrd}B (limit=${ANVIL_MAX_BYTES}B)"
  if [[ "$rw" -gt "$ANVIL_MAX_BYTES" ]] || [[ "$ctrd" -gt "$ANVIL_MAX_BYTES" ]]; then
    reset_lottery_chain "writable layer or anvil tmp over ${ANVIL_MAX_BYTES} bytes"
  fi
else
  log "anvil chain not running — skip size check"
fi

# --- 2. Orphan lottery deploy containers --------------------------------
for c in $(docker ps -aq -f name=dreamy_diffie 2>/dev/null); do
  run docker rm -f "$c"
done
for c in $(docker ps -aq -f name=ailottery-deploy-1 -f status=exited 2>/dev/null); do
  run docker rm -f "$c"
done

# --- 3. Docker hygiene --------------------------------------------------
# Stopped containers include verified rollback targets; preserve them.
run docker image prune -f
# Build cache older than 7 days (keeps recent layers for fast rebuilds).
run docker builder prune -f --filter until=168h

# Weekly reminder: tagged images and volumes require explicit retention review.
if [[ "$(date +%u)" == "7" ]]; then
  log "Retaining tagged images and volumes, including security rollback artifacts"
fi

# --- 4. System logs & package caches ------------------------------------
run journalctl --vacuum-size=100M
run apt-get clean -y 2>/dev/null || true
command -v npm >/dev/null && run npm cache clean --force 2>/dev/null || true
run rm -rf /root/.cache/pip /root/.cache/go-build 2>/dev/null || true

log "after:  $(df_line)"
log "=== disk-cleanup done ==="

#!/usr/bin/env bash
# Reclaim host resources before ecosystem / monitor redeploy.
#
# With network_mode: host, alien-monitor's Anvil/Solana survive container restarts
# unless stopped gracefully — they accumulate and eat RAM.
#
# Usage:
#   ./scripts/ecosystem_process_cleanup.sh              # chain + monitor ports (safe default)
#   ./scripts/ecosystem_process_cleanup.sh --disk       # also run disk_cleanup.sh
#   ./scripts/ecosystem_process_cleanup.sh --cursor-mcp # kill duplicate Cursor MCP filesystem servers
#   ./scripts/ecosystem_process_cleanup.sh --cursor     # cursor orphan server-main + MCP (see cleanup_cursor_leaks.sh)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DISK=0
KILL_CURSOR_MCP=0
KILL_CURSOR=0

for arg in "$@"; do
  case "$arg" in
    --disk) RUN_DISK=1 ;;
    --cursor-mcp) KILL_CURSOR_MCP=1 ;;
    --cursor) KILL_CURSOR=1; KILL_CURSOR_MCP=1 ;;
    -h|--help)
      sed -n '1,12p' "$0" | tail -n +2
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

_free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

_kill_pattern() {
  local pattern="$1"
  pkill -f "$pattern" 2>/dev/null || true
}

echo "=== ecosystem process cleanup ==="
df -h / | tail -1

# Stop monitor stack first so in-container chains get SIGTERM when possible.
if [[ -f "$ROOT/alien-monitor/docker-compose.prod.yml" ]]; then
  (cd "$ROOT/alien-monitor" && docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null) || true
  sleep 2
fi

# Host-network chain orphans (UNI mode).
echo "freeing UNI chain ports 8545 (anvil) and 8899 (solana)..."
_free_port 8545
_free_port 8899
_kill_pattern "anvil --host 127.0.0.1 --port 8545"
_kill_pattern "solana-test-validator --reset --quiet --rpc-port 8899"

# Monitor / Pulse dev processes on host.
for port in 9100 5173 5199; do
  _free_port "$port"
done
_kill_pattern "alien-monitor/backend/main.py"

# Duplicate MCP filesystem servers (Cursor/Argus leak) — opt-in only.
if [[ "$KILL_CURSOR" -eq 1 ]] && [[ -x "$ROOT/scripts/cleanup_cursor_leaks.sh" ]]; then
  "$ROOT/scripts/cleanup_cursor_leaks.sh" || true
elif [[ "$KILL_CURSOR_MCP" -eq 1 ]]; then
  mapfile -t _mcp_pids < <(pgrep -f '@modelcontextprotocol/server-filesystem' 2>/dev/null || true)
  if ((${#_mcp_pids[@]} > 2)); then
    echo "killing ${#_mcp_pids[@]} MCP filesystem processes (keeping newest 2)..."
    sorted=($(printf '%s\n' "${_mcp_pids[@]}" | sort -n))
    for ((i = 0; i < ${#sorted[@]} - 2; i++)); do
      kill "${sorted[$i]}" 2>/dev/null || true
    done
    sleep 1
  fi
fi

if [[ "$RUN_DISK" -eq 1 ]] && [[ -x "$ROOT/scripts/disk_cleanup.sh" ]]; then
  echo "running disk_cleanup.sh..."
  "$ROOT/scripts/disk_cleanup.sh" || true
fi

echo "after cleanup:"
df -h / | tail -1
_sol_pids=$(pgrep -f 'solana-test-validator --reset' 2>/dev/null | sort -u | wc -l || echo 0)
_anvil_pids=$(pgrep -f 'anvil --host 127.0.0.1 --port 8545' 2>/dev/null | sort -u | wc -l || echo 0)
echo "chain processes: anvil=${_anvil_pids} solana=${_sol_pids} (distinct PIDs; htop may show threads as duplicate rows)"
echo "=== done ==="

#!/usr/bin/env bash
# Reclaim RAM from leaked Cursor Remote SSH / MCP processes on the HOST.
#
# These are NOT managed by docker compose or deploy_ecosystem.sh — that is why
# "перезапуск сервера" (Factory/Monitor redeploy) does not touch them.
#
# Usage:
#   ./scripts/cleanup_cursor_leaks.sh              # duplicate server-main + MCP only
#   ./scripts/cleanup_cursor_leaks.sh --mcp      # MCP filesystem leaks only
#   ./scripts/cleanup_cursor_leaks.sh --all      # kill entire cursor-server (disconnects IDE!)
set -euo pipefail

MODE="${1:-}"

_count_cursor_nodes() {
  pgrep -f '/root/.cursor-server/.*/node' 2>/dev/null | sort -u | wc -l || echo 0
}

_kill_mcp_filesystem_leaks() {
  mapfile -t _mcp_pids < <(pgrep -f '@modelcontextprotocol/server-filesystem' 2>/dev/null || true)
  if ((${#_mcp_pids[@]} <= 2)); then
    echo "MCP filesystem: ${_mcp_pids[*]:-none} (ok)"
    return 0
  fi
  echo "killing ${#_mcp_pids[@]} MCP filesystem processes (keeping newest 2)..."
  sorted=($(printf '%s\n' "${_mcp_pids[@]}" | sort -n))
  for ((i = 0; i < ${#sorted[@]} - 2; i++)); do
    kill "${sorted[$i]}" 2>/dev/null || true
  done
}

_kill_orphan_cursor_servers() {
  mapfile -t _mains < <(pgrep -f 'cursor-server/.*/out/server-main.js' 2>/dev/null | sort -n || true)
  if ((${#_mains[@]} <= 1)); then
    echo "cursor server-main: ${#_mains[@]} instance (ok)"
    return 0
  fi
  echo "killing ${#_mains[@]} cursor server-main — keeping newest PID ${_mains[-1]}..."
  for ((i = 0; i < ${#_mains[@]} - 1; i++)); do
    kill "${_mains[$i]}" 2>/dev/null || true
  done
  sleep 2
}

_kill_all_cursor_server() {
  echo "WARN: killing ALL cursor-server processes — Cursor IDE will disconnect!"
  pkill -f '/root/.cursor-server/' 2>/dev/null || true
  sleep 2
}

echo "=== cursor leak cleanup (before: $(_count_cursor_nodes) node PIDs) ==="
free -h | tail -1

case "$MODE" in
  --mcp) _kill_mcp_filesystem_leaks ;;
  --all) _kill_all_cursor_server; _kill_mcp_filesystem_leaks ;;
  --help|-h)
    sed -n '1,12p' "$0" | tail -n +2
    exit 0
    ;;
  ""|--orphans)
    _kill_orphan_cursor_servers
    _kill_mcp_filesystem_leaks
    ;;
  *) echo "Unknown option: $MODE" >&2; exit 1 ;;
esac

echo "after: $(_count_cursor_nodes) cursor node PIDs"
free -h | tail -1
echo "=== done ==="

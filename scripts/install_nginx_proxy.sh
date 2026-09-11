#!/usr/bin/env bash
# Wire ecosystem nginx snippets into a VPS site (magic-ai-factory.com or custom).
#
# Usage:
#   sudo ./scripts/install_nginx_proxy.sh
#   NGINX_SITE=/etc/nginx/sites-available/example.com sudo ./scripts/install_nginx_proxy.sh --dry-run
#
# Requires: nginx, snippets under deploy/nginx/snippets/*.conf
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNIPPET_DIR="$ROOT/deploy/nginx/snippets"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
DRY_RUN=0

usage() {
  cat <<'EOF'
install_nginx_proxy.sh — include Monitor / Pulse / ARGUS snippets in an nginx vhost

Options:
  --dry-run     Print planned changes only
  --site PATH   Target nginx site file (default: /etc/nginx/sites-enabled/magic-ai-factory.com)
  -h, --help    This help

Snippets (included in order when present):
  alien-monitor.conf   → /monitor/  → 127.0.0.1:9100
  pulse-terminal.conf  → /pulse/    → 127.0.0.1:5199
  grafana.conf         → /grafana/  → 127.0.0.1:9082
  prometheus.conf      → /prometheus/ → 127.0.0.1:9090 (basic auth)
  argus-arena.conf     → /arena/    → ARGUS arena upstream
  argus-install.conf   → install helper paths

Inside the server { } block you still need upstream routes for Factory (:9080/:9081),
Hub (:9083), Mesh (:8090) — see docs/deploy-ecosystem-runbook.md.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --site) NGINX_SITE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

MARK_BEGIN="# BEGIN aicom-ecosystem-snippets (managed by install_nginx_proxy.sh)"
MARK_END="# END aicom-ecosystem-snippets"

if [[ ! -f "$NGINX_SITE" ]]; then
  echo "ERROR: nginx site not found: $NGINX_SITE" >&2
  echo "Create a server { } block first, then re-run." >&2
  exit 1
fi

SNIPPETS=()
for name in alien-monitor.conf pulse-terminal.conf grafana.conf prometheus.conf argus-arena.conf argus-install.conf; do
  [[ -f "$SNIPPET_DIR/$name" ]] && SNIPPETS+=("$SNIPPET_DIR/$name")
done

if [[ ${#SNIPPETS[@]} -eq 0 ]]; then
  echo "ERROR: no snippets in $SNIPPET_DIR" >&2
  exit 1
fi

TMP="$(mktemp)"
{
  echo "$MARK_BEGIN"
  for f in "${SNIPPETS[@]}"; do
    echo "# --- $(basename "$f") ---"
    cat "$f"
    echo ""
  done
  echo "$MARK_END"
} > "$TMP"

if grep -qF "$MARK_BEGIN" "$NGINX_SITE"; then
  echo "Snippets block already present in $NGINX_SITE — refreshing..."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would replace block between markers in $NGINX_SITE"
    cat "$TMP"
    rm -f "$TMP"
    exit 0
  fi
  python3 - "$NGINX_SITE" "$TMP" "$MARK_BEGIN" "$MARK_END" <<'PY'
import sys
from pathlib import Path

site, block, begin, end = sys.argv[1:5]
text = Path(site).read_text(encoding="utf-8")
replacement = Path(block).read_text(encoding="utf-8").rstrip() + "\n"
start = text.find(begin)
end_i = text.find(end)
if start < 0 or end_i < 0:
    raise SystemExit("markers missing — edit manually")
end_i = text.find("\n", end_i)
chunk = text[:start] + replacement + (text[end_i + 1 :] if end_i >= 0 else "")
Path(site).write_text(chunk, encoding="utf-8")
PY
else
  if ! grep -q 'server[[:space:]]*{' "$NGINX_SITE"; then
    echo "ERROR: no server { } block in $NGINX_SITE" >&2
    exit 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would append before closing } of first server block in $NGINX_SITE:"
    cat "$TMP"
    rm -f "$TMP"
    exit 0
  fi
  python3 - "$NGINX_SITE" "$TMP" <<'PY'
import sys
from pathlib import Path

site, block = sys.argv[1], Path(sys.argv[2]).read_text(encoding="utf-8").rstrip() + "\n"
text = Path(site).read_text(encoding="utf-8")
idx = text.find("server")
if idx < 0:
    raise SystemExit("no server block")
depth = 0
insert_at = None
for i in range(idx, len(text)):
    if text[i] == "{":
        depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            insert_at = i
            break
if insert_at is None:
    raise SystemExit("unbalanced server block")
Path(site).write_text(text[:insert_at] + "\n" + block + text[insert_at:], encoding="utf-8")
PY
fi

rm -f "$TMP"

if command -v nginx >/dev/null 2>&1; then
  nginx -t
  if command -v systemctl >/dev/null 2>&1; then
    systemctl reload nginx
  else
    nginx -s reload
  fi
  echo "nginx reloaded — snippets active in $NGINX_SITE"
else
  echo "WARN: nginx not in PATH — validate and reload manually"
fi

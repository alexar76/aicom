#!/usr/bin/env bash
# Serve Prometheus and Grafana through nginx, so their container ports can stop being
# published to the internet.
#
# Run ON the factory host. Idempotent: re-running changes nothing once wired.
#
# Why not scripts/deploy_observability.sh: that one also rebuilds and restarts the whole
# observability stack and re-imports dashboards. This does the edge half only, which is the
# part that has to exist BEFORE the ports are closed — close them first and the operator
# loses every route to their own dashboards.
set -euo pipefail

SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
ENV_FILE="${ENV_FILE:-/root/claudecode/aicom/.env}"
SNIPPET_DIR=/etc/nginx/snippets
HTPASSWD=/etc/nginx/.htpasswd-prometheus
BACKUP="${SITE}.bak-$(date -u +%Y%m%d-%H%M%S)"

log() { printf '\n=== %s\n' "$*"; }
die() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

[[ -f "$SITE" ]] || die "no vhost at $SITE"
[[ -f "$ENV_FILE" ]] || die "no env file at $ENV_FILE"
[[ -f "$SNIPPET_DIR/prometheus.conf" && -f "$SNIPPET_DIR/grafana.conf" ]] \
  || die "copy deploy/nginx/snippets/{prometheus,grafana}.conf to $SNIPPET_DIR first"

# ── 1. the map the grafana snippet needs ────────────────────────────────────────
# $connection_upgrade is not a builtin. Without it `nginx -t` fails outright, so it has to
# be defined at http level — once, in conf.d, never per vhost.
if ! grep -rqs connection_upgrade /etc/nginx/nginx.conf /etc/nginx/conf.d/; then
  log "Defining \$connection_upgrade at http level"
  cat > /etc/nginx/conf.d/connection-upgrade.conf <<'EOF'
# Required by any location that proxies websockets (Grafana live, log tailing).
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
EOF
fi

# ── 2. basic auth for Prometheus ────────────────────────────────────────────────
# Reuses the Grafana admin password that already exists rather than minting a second
# secret: one fewer credential to store, and the two surfaces are for the same person.
if [[ ! -f "$HTPASSWD" ]]; then
  log "Writing $HTPASSWD"
  PASS="$(grep -E '^GRAFANA_ADMIN_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  [[ -n "$PASS" ]] || die "GRAFANA_ADMIN_PASSWORD is empty in $ENV_FILE"
  USER_NAME="$(grep -E '^GRAFANA_ADMIN_USER=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  # openssl rather than htpasswd(1): apache2-utils is not installed and this needs no
  # package. nginx reads APR1 hashes natively.
  printf '%s:%s\n' "${USER_NAME:-admin}" "$(openssl passwd -apr1 "$PASS")" > "$HTPASSWD"
  chmod 640 "$HTPASSWD"
  chown root:www-data "$HTPASSWD" 2>/dev/null || true
  unset PASS
fi

# ── 3. include the snippets in the TLS server block ─────────────────────────────
if grep -q "snippets/prometheus.conf" "$SITE"; then
  log "Already wired — nothing to do"
else
  log "Backing up $SITE → $BACKUP"
  cp -a "$SITE" "$BACKUP"

  # Insert right after the server_name of the first (TLS) server block, before any
  # location — a `location ^~` added later cannot shadow these, and certbot rewrites
  # happen further down the file.
  line="$(grep -n '^\s*server_name' "$SITE" | head -1 | cut -d: -f1)"
  [[ -n "$line" ]] || { cp -a "$BACKUP" "$SITE"; die "no server_name found; restored"; }
  log "Inserting includes after line $line"
  sed -i "${line}a\\
\\
    # Observability behind the edge, so the container ports need not be public.\\
    include ${SNIPPET_DIR}/prometheus.conf;\\
    include ${SNIPPET_DIR}/grafana.conf;" "$SITE"

  if ! nginx -t 2>&1; then
    log "nginx -t FAILED — restoring $BACKUP"
    cp -a "$BACKUP" "$SITE"
    nginx -t >/dev/null 2>&1 || die "restored config still fails nginx -t — investigate by hand"
    die "config rejected; nothing changed"
  fi
  systemctl reload nginx
fi

log "Verifying through the edge"
prom="$(curl -s -o /dev/null -w '%{http_code}' https://magic-ai-factory.com/prometheus/)"
graf="$(curl -s -o /dev/null -w '%{http_code}' -L https://magic-ai-factory.com/grafana/)"
echo "  /prometheus/ → $prom   (401 expected: basic auth is on)"
echo "  /grafana/    → $graf   (200 expected: Grafana's own login)"
[[ "$prom" == "401" ]] || echo "  WARN: expected 401 from /prometheus/, got $prom" >&2
[[ "$graf" == "200" ]] || echo "  WARN: expected 200 from /grafana/, got $graf" >&2

log "Edge is wired. The container ports can now be bound to loopback:"
echo "  AICOM_PORT_PROMETHEUS=127.0.0.1:9090"
echo "  AICOM_PORT_GRAFANA=127.0.0.1:9082"
echo "  …in $ENV_FILE, then: docker compose up -d prometheus grafana"

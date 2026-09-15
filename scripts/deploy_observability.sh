#!/usr/bin/env bash
# Build/restart Prometheus + Grafana, wire nginx /prometheus/ + /grafana/, import dashboards.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/magic-ai-factory.com}"
SNIPPET_GRAFANA="$ROOT/deploy/nginx/snippets/grafana.conf"
SNIPPET_PROM="$ROOT/deploy/nginx/snippets/prometheus.conf"
PUBLIC_BASE="${OBSERVABILITY_PUBLIC_URL:-https://magic-ai-factory.com}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

append_env_once() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    return 0
  fi
  printf '\n%s=%s\n' "$key" "$val" >>"$ENV_FILE"
  echo "Added $key to .env"
}

append_env_once "GRAFANA_ROOT_URL" "${PUBLIC_BASE}/grafana/"
append_env_once "PROMETHEUS_EXTERNAL_URL" "${PUBLIC_BASE}/prometheus/"
append_env_once "GRAFANA_ADMIN_USER" "admin"

if [[ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]]; then
  python3 "$ROOT/scripts/fill_production_env.py" --env-file "$ENV_FILE" >/dev/null
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "${AIFACTORY_USE_HOST_DOCKER:-}" == "1" ]]; then
  COMPOSE_FILES+=(-f docker-compose.host-docker.yml)
else
  COMPOSE_FILES+=(-f docker-compose.dind.yml)
fi

export AICOM_IMAGE_TAG="${AICOM_IMAGE_TAG:-$("$ROOT/scripts/docker_image_tag.sh")}"
echo "=== Observability deploy (tag=${AICOM_IMAGE_TAG}) ==="

docker compose "${COMPOSE_FILES[@]}" up -d --build app prometheus grafana

echo "Waiting for Prometheus + Grafana..."
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${AICOM_PORT_PROMETHEUS:-9090}/-/ready" >/dev/null 2>&1 \
    && curl -sf "http://127.0.0.1:${AICOM_PORT_GRAFANA:-9082}/api/health" >/dev/null 2>&1 \
    && break
  sleep 2
done

# Clear brute-force lock if present (Grafana SQLite on bind mount).
if [[ -f "$ROOT/data/grafana/grafana.db" ]] && command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$ROOT/data/grafana/grafana.db" "DELETE FROM login_attempt;" 2>/dev/null || true
  # Prometheus runs with --web.route-prefix=/prometheus/; datasource must include subpath.
  sqlite3 "$ROOT/data/grafana/grafana.db" \
    "UPDATE data_source SET url='http://prometheus:9090/prometheus', uid='prometheus' WHERE type='prometheus';" \
    2>/dev/null || true
fi

chmod +x "$ROOT/scripts/setup_grafana_dashboards.sh"
# Re-import dashboards after datasource uid/url fix (panels break if uid drifts).
if ! "$ROOT/scripts/setup_grafana_dashboards.sh"; then
  echo "WARN: dashboard import failed — retry after manual Grafana login" >&2
fi

docker exec aicom-grafana-1 grafana cli admin reset-admin-password "${GRAFANA_ADMIN_PASSWORD}" >/dev/null 2>&1 || true
docker restart aicom-grafana-1 >/dev/null
for _ in $(seq 1 20); do
  curl -sf "http://127.0.0.1:${AICOM_PORT_GRAFANA:-9082}/api/health" >/dev/null 2>&1 && break
  sleep 2
done

if ! "$ROOT/scripts/setup_grafana_dashboards.sh"; then
  echo "WARN: dashboard import after Grafana restart failed" >&2
fi

# Prometheus basic auth (same credentials as Grafana admin).
HTPASSWD="/etc/nginx/.htpasswd-prometheus"
if command -v htpasswd >/dev/null 2>&1; then
  sudo htpasswd -nbB "${GRAFANA_ADMIN_USER:-admin}" "${GRAFANA_ADMIN_PASSWORD}" | sudo tee "$HTPASSWD" >/dev/null
  sudo chmod 644 "$HTPASSWD"
else
  echo "WARN: htpasswd not installed — Prometheus /prometheus/ will fail auth until: apt install apache2-utils" >&2
fi

patch_nginx_snippet() {
  local needle="$1"
  local snippet_path="$2"
  if [[ ! -f "$NGINX_SITE" ]] || [[ ! -f "$snippet_path" ]]; then
    return 1
  fi
  if grep -q "$needle" "$NGINX_SITE"; then
    echo "nginx: $needle already configured"
    return 0
  fi
  sudo cp "$snippet_path" "/etc/nginx/snippets/$(basename "$snippet_path")"
  python3 - "$NGINX_SITE" "$snippet_path" "$needle" <<'PY'
import sys
from pathlib import Path

site = Path(sys.argv[1])
snippet = Path(sys.argv[2]).read_text(encoding="utf-8")
needle = sys.argv[3]
text = site.read_text(encoding="utf-8")
marker = "    location / {"
if marker not in text:
    raise SystemExit(f"Could not find insertion point in {site}")
if needle in text:
    raise SystemExit(0)
site.write_text(text.replace(marker, snippet + "\n" + marker, 1), encoding="utf-8")
print(f"Patched {site}")
PY
}

if [[ -f "$NGINX_SITE" ]]; then
  sudo cp "$SNIPPET_GRAFANA" /etc/nginx/snippets/grafana.conf
  sudo cp "$SNIPPET_PROM" /etc/nginx/snippets/prometheus.conf
  patch_nginx_snippet 'location ^~ /grafana/' "$SNIPPET_GRAFANA" || true
  patch_nginx_snippet 'location ^~ /prometheus/' "$SNIPPET_PROM" || true
  if command -v nginx >/dev/null 2>&1; then
    sudo nginx -t
    sudo systemctl reload nginx
  fi
else
  echo "NOTE: nginx site missing ($NGINX_SITE) — add snippets manually"
fi

PUBLIC_GRAF="${PUBLIC_BASE}/grafana/"
PUBLIC_PROM="${PUBLIC_BASE}/prometheus/"
GRAF_PORT="${AICOM_PORT_GRAFANA:-9082}"
PROM_PORT="${AICOM_PORT_PROMETHEUS:-9090}"

echo ""
echo "=== Verification ==="
curl -sf "http://127.0.0.1:${PROM_PORT}/-/ready" && echo "Prometheus ready (local :${PROM_PORT})"
curl -sf "http://127.0.0.1:${GRAF_PORT}/api/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print('Grafana', d.get('version','?'))"

curl -sf -u "${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD}" \
  "${PUBLIC_PROM}api/v1/query?query=up" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Public Prometheus query:', d.get('status'))"

curl -sf -o /dev/null -w "Public Grafana login page: HTTP %{http_code}\n" "${PUBLIC_GRAF}login"

echo ""
echo "Grafana:    ${PUBLIC_GRAF}  (login: ${GRAFANA_ADMIN_USER:-admin})"
echo "Prometheus: ${PUBLIC_PROM}  (same login via nginx basic auth)"
echo "Dashboard:  ${PUBLIC_GRAF}d/ai-factory-dashboard/ai-factory-overview"
echo "Explore:    ${PUBLIC_GRAF}explore  →  llm_provider_health"
